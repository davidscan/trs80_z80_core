#!/usr/bin/env python3
"""z80/asm.py -- an EDTASM-style Z80 assembler over the opcode table's inverse index.

    python3 -m z80.asm SOURCE [-o OUT] [--format {bin,cmd,cas,bas}] [--name NAME]
                       [--org ADDR] [--entry ADDR] [--list FILE] [--symbols]

No opcode knowledge lives here.  Every instruction is looked up in
`z80.table.INVERSE` (signature -> encoding), the same table the core
decodes from and the disassembler renders from, so what this assembles
is by construction what the core executes and what `z80.disasm` prints
(tests/test_asm.py pins the round trip over every signature).

SOURCE is what the period books print for the Radio Shack Editor/
Assembler and its successors:

    00100 START   LD   HL,VIDEO      ;a comment
    00110         LD   (HL),A
    00120 VIDEO   EQU  3C00H
    00130         DEFM 'HELLO'
    00140         END  START

  - A leading line number (as the editor numbered it) is optional and
    ignored.  A line whose first character is `*` or `;` is a comment.
  - The first field is a label when it is not a mnemonic or directive;
    a trailing colon is allowed and dropped.  Labels are case-insensitive
    (everything outside quotes is upper-cased, as EDTASM did).
  - Numbers: decimal; hex with a trailing H and a leading digit (0FFH);
    octal with Q or O; binary with B; a character in single quotes ('A',
    and 'AB' is 4142H).  `$` is the location counter.
  - Expressions: + - * / and .MOD. .AND. .OR. .XOR. .NOT. .SHL. .SHR.,
    with the usual precedence (unary, then * / .MOD. .SHL. .SHR., then
    + -, then .AND., then .OR. .XOR.) and parentheses for grouping.  An
    operand that is entirely parenthesized is a memory or port reference,
    as in Zilog syntax: `LD A,(BUF+1)` reads memory, `LD A,BUF+1` loads
    the address.  NOTE: the original EDTASM evaluated left to right with
    no precedence; period listings' expressions (SCREEN+708, $-1) do not
    tell the two apart, so the usual precedence is used here.
  - Directives: ORG, EQU, DEFB/DB, DEFW/DW, DEFM/DM, DEFS/DS [,fill],
    END [entry].  DEFB and DEFM both take any mix of expressions and
    quoted strings ('' inside single quotes is one quote).
  - Zilog leniencies: `SUB A,B` and `CP A,n` drop the A; `ADD B` means
    `ADD A,B`; `(IX)` means `(IX+0)`.

Two passes: the first sizes every statement and defines the labels, the
second evaluates and emits.  An EQU may refer to a later label.  A BIT,
RST or IM operand must be a constant the first pass can evaluate, since
it is part of the opcode, not an immediate.

Outputs (`-o` picks the format from the extension, `--format` overrides):
  bin  the raw image from the lowest address assembled to the highest,
       gaps between ORG blocks zero-filled;
  cmd  a TRS-80 load module: a name record, load records of at most 253
       bytes, a transfer record with the entry address;
  cas  a Model I SYSTEM tape as the byte stream a cassette held: a 256-byte
       zero leader, A5H, 55H, the six-character name, 3CH data blocks with
       a checksum, 78H and the entry address;
  bas  a BASIC listing in the magazines' shape: a DATA block with a
       checksum, a POKE loop, DEFUSR at the entry and `PRINT USR(0)` on
       line 60 for the user to replace.  One contiguous ORG block only.
With no -o the listing goes to stdout (`--list FILE` writes it as well).
The entry address is the END operand, else --entry, else the first ORG.
Errors are reported as `file:line: message`, all of them, exit status 1.
"""
import argparse
import os
import re
import sys

from .table import INVERSE

REGS = {'A', 'B', 'C', 'D', 'E', 'H', 'L', 'F', 'I', 'R',
        'IX', 'IY', 'IXH', 'IXL', 'IYH', 'IYL', 'AF', "AF'", 'BC', 'DE', 'HL', 'SP'}
CONDS = {'NZ', 'Z', 'NC', 'C', 'PO', 'PE', 'P', 'M'}
IREGS = {'HL', 'BC', 'DE', 'SP', 'IX', 'IY'}
ALU_DROP_A = {'SUB', 'AND', 'XOR', 'OR', 'CP'}
ALU_NEED_A = {'ADD', 'ADC', 'SBC'}
DIRECTIVES = {'ORG', 'EQU', 'DEFB', 'DB', 'DEFW', 'DW', 'DEFM', 'DM', 'DEFS', 'DS', 'END'}
DOT_OPS = {'AND', 'OR', 'XOR', 'NOT', 'MOD', 'SHL', 'SHR'}

# mnemonic -> [operand pattern tuples], in table order
BY_MNEMONIC = {}
for _m, _ops in INVERSE:
    BY_MNEMONIC.setdefault(_m, []).append(_ops)
MNEMONICS = set(BY_MNEMONIC)


class AsmError(Exception):
    """A source error: .lineno (1-based physical line) and the message."""

    def __init__(self, lineno, msg):
        super().__init__('%d: %s' % (lineno, msg))
        self.lineno = lineno
        self.msg = msg


class Undefined(Exception):
    def __init__(self, name):
        super().__init__(name)
        self.name = name


# ---- expressions -------------------------------------------------------------
_NUM = re.compile(r"^(?:([0-9][0-9A-F]*)H|([0-7]+)[QO]|([01]+)B|([0-9]+))$")


def number(tok):
    """The value of a numeric token, or None when it is not one."""
    m = _NUM.match(tok)
    if not m:
        return None
    h, q, b, d = m.groups()
    if h is not None:
        return int(h, 16)
    if q is not None:
        return int(q, 8)
    if b is not None:
        return int(b, 2)
    return int(d)


def tokenize(text, lineno):
    """Expression tokens: ('num', v) ('id', name) ('pc',) ('op', s)."""
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif c == "'":
            j = text.find("'", i + 1)
            if j < 0:
                raise AsmError(lineno, 'unterminated character constant')
            s = text[i + 1:j]
            if len(s) == 1:
                out.append(('num', ord(s)))
            elif len(s) == 2:
                out.append(('num', (ord(s[0]) << 8) | ord(s[1])))
            else:
                raise AsmError(lineno, 'a character constant is one or two characters: %r' % s)
            i = j + 1
        elif c == '$' and (i + 1 >= n or not (text[i + 1].isalnum() or text[i + 1] in '_$@?')):
            out.append(('pc',))
            i += 1
        elif c.isalnum() or c in '_$@?':
            j = i
            while j < n and (text[j].isalnum() or text[j] in "_$@?'"):
                j += 1
            tok = text[i:j]
            v = number(tok)
            if v is not None:
                out.append(('num', v))
            elif tok[0].isdigit():
                raise AsmError(lineno, 'bad number %r' % tok)
            else:
                out.append(('id', tok))
            i = j
        elif c == '.':
            j = text.find('.', i + 1)
            if j < 0 or text[i + 1:j] not in DOT_OPS:
                raise AsmError(lineno, 'unknown operator at %r' % text[i:i + 6])
            out.append(('op', '.' + text[i + 1:j] + '.'))
            i = j + 1
        elif c in '+-*/()':
            out.append(('op', c))
            i += 1
        else:
            raise AsmError(lineno, 'unexpected character %r' % c)
    return out


class Expr:
    """A parsed expression, evaluated against a symbol table and a PC."""

    def __init__(self, text, lineno):
        self.text = text.strip()
        self.lineno = lineno
        self.toks = tokenize(self.text, lineno)
        if not self.toks:
            raise AsmError(lineno, 'missing expression')

    def eval(self, symbols, pc):
        self._syms, self._pc, self._i = symbols, pc, 0
        v = self._or()
        if self._i != len(self.toks):
            raise AsmError(self.lineno, 'bad expression %r' % self.text)
        return v

    def _peek(self):
        return self.toks[self._i] if self._i < len(self.toks) else None

    def _take(self, *ops):
        t = self._peek()
        if t and t[0] == 'op' and t[1] in ops:
            self._i += 1
            return t[1]
        return None

    def _or(self):
        v = self._and()
        while True:
            o = self._take('.OR.', '.XOR.')
            if not o:
                return v
            w = self._and()
            v = (v | w) if o == '.OR.' else (v ^ w)

    def _and(self):
        v = self._add()
        while self._take('.AND.'):
            v &= self._add()
        return v

    def _add(self):
        v = self._mul()
        while True:
            o = self._take('+', '-')
            if not o:
                return v
            w = self._mul()
            v = v + w if o == '+' else v - w

    def _mul(self):
        v = self._unary()
        while True:
            o = self._take('*', '/', '.MOD.', '.SHL.', '.SHR.')
            if not o:
                return v
            w = self._unary()
            if o == '*':
                v *= w
            elif o == '/':
                if w == 0:
                    raise AsmError(self.lineno, 'division by zero')
                v = int(v / w)
            elif o == '.MOD.':
                if w == 0:
                    raise AsmError(self.lineno, 'division by zero')
                v %= w
            elif not 0 <= w <= 16:
                raise AsmError(self.lineno, 'shift count out of range: %d' % w)
            elif o == '.SHL.':
                v <<= w
            else:
                v >>= w

    def _unary(self):
        o = self._take('-', '+', '.NOT.')
        if o == '-':
            return -self._unary()
        if o == '+':
            return self._unary()
        if o == '.NOT.':
            return ~self._unary()
        return self._primary()

    def _primary(self):
        t = self._peek()
        if t is None:
            raise AsmError(self.lineno, 'bad expression %r' % self.text)
        self._i += 1
        if t[0] == 'num':
            return t[1]
        if t[0] == 'pc':
            return self._pc
        if t[0] == 'id':
            if t[1] not in self._syms:
                raise Undefined(t[1])
            return self._syms[t[1]]
        if t == ('op', '('):
            v = self._or()
            if not self._take(')'):
                raise AsmError(self.lineno, 'missing ) in %r' % self.text)
            return v
        raise AsmError(self.lineno, 'bad expression %r' % self.text)


# ---- source lines -----------------------------------------------------------
def split_fields(line, lineno):
    """(label, op, operand text, comment) from one source line, or None."""
    s = line.rstrip('\r\n')
    m = re.match(r'^\s*\d+\s(.*)$', s) or re.match(r'^\s*\d+$', s)
    if m:
        s = m.group(1) if m.lastindex else ''
    if not s.strip() or s[0] in '*;' or s.strip()[0] == ';':
        return None
    # cut the comment: the first ';' outside quotes
    out, q, prev = [], None, ' '
    for ch in s:
        if q:
            out.append(ch)
            if ch == q:
                q = None
        elif ch in '\'"' and not prev.isalnum():
            q = ch
            out.append(ch)
        elif ch == ';':
            break
        else:
            out.append(ch)
        prev = ch
    body = ''.join(out)
    comment = s[len(body):]
    if q:
        raise AsmError(lineno, 'unterminated string')
    # upper-case outside quotes
    up, q, prev = [], None, ' '
    for ch in body:
        if q:
            up.append(ch)
            if ch == q:
                q = None
        elif ch in '\'"' and not prev.isalnum():
            q = ch
            up.append(ch)
        else:
            up.append(ch.upper())
        prev = ch
    body = ''.join(up)
    parts = body.split(None, 1)
    if not parts:
        return None
    first = parts[0]
    rest = parts[1] if len(parts) > 1 else ''
    label = None
    if first.endswith(':') or (first not in MNEMONICS and first not in DIRECTIVES):
        label = first.rstrip(':')
        if not re.match(r'^[A-Z_@?][A-Z0-9_@?$]*$', label):
            raise AsmError(lineno, 'bad label or unknown instruction %r' % first)
        parts = rest.split(None, 1)
        if not parts:
            return (label, None, '', comment)
        first = parts[0]
        rest = parts[1] if len(parts) > 1 else ''
    if first not in MNEMONICS and first not in DIRECTIVES:
        raise AsmError(lineno, 'unknown instruction %r' % first)
    return (label, first, rest.strip(), comment)


def split_operands(text, lineno):
    """Split on commas outside quotes and parentheses; drop blanks outside quotes."""
    items, cur, q, depth, prev = [], [], None, 0, ' '
    for ch in text:
        if q:
            cur.append(ch)
            if ch == q:
                q = None
        elif ch in '\'"' and not prev.isalnum():
            q = ch
            cur.append(ch)
        elif ch == '(':
            depth += 1
            cur.append(ch)
        elif ch == ')':
            depth -= 1
            cur.append(ch)
        elif ch == ',' and depth == 0:
            items.append(''.join(cur))
            cur = []
        elif not ch.isspace():
            cur.append(ch)
        prev = ch
    if q:
        raise AsmError(lineno, 'unterminated string')
    if depth:
        raise AsmError(lineno, 'unbalanced parentheses in %r' % text)
    items.append(''.join(cur))
    if items == ['']:
        return []
    if any(i == '' for i in items):
        raise AsmError(lineno, 'empty operand in %r' % text)
    return items


def data_items(text, lineno):
    """DEFB/DEFM/DEFW items: ('str', bytes) or ('expr', Expr)."""
    out = []
    for item in split_operands(text, lineno):
        if item[0] in '\'"' and item[-1] == item[0] and len(item) >= 2 and (
                item[0] == '"' or len(item) != 3):
            s = item[1:-1]
            if item[0] == "'":
                s = s.replace("''", "'")
            out.append(('str', s.encode('latin-1')))
        else:
            out.append(('expr', Expr(item, lineno)))
    return out


# ---- operands ------------------------------------------------------------------
class Opnd:
    """One instruction operand: its candidate pattern tokens and any value."""

    def __init__(self, text, lineno, symbols, pc):
        self.text = text
        self.tokens = []            # pattern tokens this operand can stand for
        self.expr = None            # the value expression, if any
        self.kind = None            # 'reg' | 'ind' | 'idx' | 'mem' | 'expr'
        t = text
        if t in REGS or t in CONDS:
            self.kind = 'reg'
            self.tokens = [t]
            return
        if t.startswith('(') and t.endswith(')'):
            inner = t[1:-1]
            if inner in IREGS:
                self.kind = 'ind'
                self.tokens = ['(%s)' % inner]
                if inner in ('IX', 'IY'):
                    self.tokens.append('(%s+d)' % inner)   # (IX) as (IX+0)
                    self.expr = Expr('0', lineno)
                return
            if inner == 'C':
                self.kind = 'ind'
                self.tokens = ['(C)']
                return
            m = re.match(r'^(IX|IY)([+-].+)$', inner)
            if m:
                self.kind = 'idx'
                self.tokens = ['(%s+d)' % m.group(1)]
                self.expr = Expr(m.group(2), lineno)
                return
            self.kind = 'mem'
            self.tokens = ['(nn)', '(n)']
            self.expr = Expr(inner, lineno)
            return
        self.kind = 'expr'
        self.expr = Expr(t, lineno)
        self.tokens = ['n', 'nn', 'd']
        try:
            v = self.expr.eval(symbols, pc)
        except Undefined:
            return
        if 0 <= v <= 7:
            self.tokens.append(str(v))            # BIT/SET/RES bit, IM mode
        self.tokens.append('%02XH' % (v & 0xFF))  # RST vector


def choose(mnemonic, opnds, lineno):
    """The (encoding, Op) for these operands, from the inverse index."""
    for ops in BY_MNEMONIC[mnemonic]:
        if len(ops) != len(opnds):
            continue
        if all(tok in o.tokens for tok, o in zip(ops, opnds)):
            return INVERSE[(mnemonic, ops)]
    raise AsmError(lineno, 'no such instruction: %s %s'
                   % (mnemonic, ','.join(o.text for o in opnds)))


def byte_value(v, lineno, what='byte'):
    if not -256 < v < 256:
        raise AsmError(lineno, '%s out of range: %d' % (what, v))
    return v & 0xFF


def word_value(v, lineno, what='word'):
    if not -65536 < v < 65536:
        raise AsmError(lineno, '%s out of range: %d' % (what, v))
    return v & 0xFFFF


def encode(enc, entry, opnds, symbols, pc, lineno):
    """The bytes of one instruction at pc: the encoding with the
    immediates in operand order, the DD CB / FD CB displacement between
    the prefix and the last opcode byte."""
    out = bytearray(enc)
    tail = bytearray()
    for o, opnd in zip(entry.operands, opnds):
        k = o.kind
        if k in ('imm8', 'port_imm'):
            tail.append(byte_value(opnd.expr.eval(symbols, pc), lineno, 'immediate'))
        elif k in ('imm16', 'aimm16'):
            v = word_value(opnd.expr.eval(symbols, pc), lineno, 'address')
            tail += bytes((v & 0xFF, v >> 8))
        elif k == 'rel':
            target = opnd.expr.eval(symbols, pc)
            disp = target - (pc + entry.length)
            if not -128 <= disp <= 127:
                raise AsmError(lineno, 'relative jump out of range: %d bytes' % disp)
            tail.append(disp & 0xFF)
        elif k == 'idx':
            d = opnd.expr.eval(symbols, pc)
            if not -128 <= d <= 127:
                raise AsmError(lineno, 'index displacement out of range: %d' % d)
            if len(enc) == 3 and enc[1] == 0xCB:
                out = bytearray(enc[:2]) + bytes([d & 0xFF]) + bytes(enc[2:])
            else:
                tail.append(d & 0xFF)
    out += tail
    if len(out) != entry.length:
        raise AsmError(lineno, 'internal: %s emitted %d bytes, the table says %d'
                       % (entry.mnemonic, len(out), entry.length))
    return bytes(out)


# ---- the assembler -------------------------------------------------------------
class Stmt:
    __slots__ = ('lineno', 'text', 'label', 'op', 'args', 'comment', 'pc', 'size',
                 'enc', 'entry', 'opnds', 'items', 'bytes', 'value')

    def __init__(self, lineno, text, label, op, args, comment):
        self.lineno, self.text = lineno, text.rstrip('\r\n')
        self.label, self.op, self.args, self.comment = label, op, args, comment
        self.pc = self.size = 0
        self.enc = self.entry = self.opnds = self.items = self.value = None
        self.bytes = b''


class Result:
    """What assemble() returns: segments, entry, symbols, listing, errors."""

    def __init__(self):
        self.segments = []          # [(org, bytes)] in source order
        self.entry = None
        self.symbols = {}
        self.stmts = []
        self.errors = []            # [(lineno, message)]

    @property
    def ok(self):
        return not self.errors

    @property
    def size(self):
        return sum(len(b) for _, b in self.segments)

    def listing(self):
        """EDTASM-shaped: address, bytes (four a line), the source line."""
        lines = []
        for s in self.stmts:
            if s.op == 'EQU' and s.value is not None:
                lines.append('%04X  =            %s' % (s.value & 0xFFFF, s.text))
                continue
            if s.op is None and s.label is None:
                lines.append('%-19s%s' % ('', s.text))
                continue
            b = s.bytes
            head = ' '.join('%02X' % x for x in b[:4])
            lines.append('%04X  %-12s %s' % (s.pc & 0xFFFF, head, s.text))
            for i in range(4, len(b), 4):
                lines.append('%04X  %-12s' % ((s.pc + i) & 0xFFFF,
                                              ' '.join('%02X' % x for x in b[i:i + 4])))
        return '\n'.join(lines) + '\n'

    # ---- output formats ----
    def to_bin(self):
        if not self.segments:
            return b''
        lo = min(o for o, _ in self.segments)
        hi = max(o + len(b) for o, b in self.segments)
        img = bytearray(hi - lo)
        for o, b in self.segments:
            img[o - lo:o - lo + len(b)] = b
        return bytes(img)

    @staticmethod
    def _name(name):
        name = name.upper()[:6]
        if not all(32 <= ord(c) < 127 for c in name):
            raise ValueError('the program name %r is not printable ASCII: pass --name' % name)
        return name

    def to_cmd(self, name):
        name = self._name(name)
        out = bytearray([0x05, len(name)]) + name.encode('ascii')
        for org, data in self.segments:
            for i in range(0, len(data), 253):
                chunk = data[i:i + 253]
                a = org + i
                out += bytes([0x01, len(chunk) + 2, a & 0xFF, a >> 8]) + chunk
        e = self.entry & 0xFFFF
        out += bytes([0x02, 0x02, e & 0xFF, e >> 8])
        return bytes(out)

    def to_cas(self, name):
        name = self._name(name).ljust(6)
        out = bytearray(256) + bytes([0xA5, 0x55]) + name.encode('ascii')
        for org, data in self.segments:
            for i in range(0, len(data), 256):
                chunk = data[i:i + 256]
                a = org + i
                out += bytes([0x3C, len(chunk) & 0xFF, a & 0xFF, a >> 8]) + chunk
                out.append((sum(chunk) + (a & 0xFF) + (a >> 8)) & 0xFF)
        e = self.entry & 0xFFFF
        out += bytes([0x78, e & 0xFF, e >> 8])
        return bytes(out)

    def to_bas(self, name):
        if len(self.segments) != 1:
            raise ValueError('the DATA loader needs one contiguous ORG block, not %d'
                             % len(self.segments))
        org, code = self.segments[0]
        lines = ['10 REM %s -- %d BYTES AT %d (%04XH), ENTRY %d (%04XH)'
                 % (name.upper(), len(code), org, org, self.entry, self.entry),
                 '20 E=%d:C=0' % org,
                 '30 FOR I=0 TO %d:READ B:POKE E+I,B:C=C+B:NEXT' % (len(code) - 1),
                 '40 IF C<>%d THEN PRINT "BAD DATA -- CHECK THE DATA LINES":END' % sum(code),
                 '50 DEFUSR=%d' % self.entry,
                 '60 PRINT USR(0)']
        ln = 1000
        for i in range(0, len(code), 16):
            lines.append('%d DATA %s' % (ln, ','.join(str(b) for b in code[i:i + 16])))
            ln += 10
        return '\n'.join(lines) + '\n'


def assemble(text, org=None, entry=None):
    """Assemble SOURCE text.  org/entry are the fallbacks when the source
    has no ORG / no END operand.  Returns a Result; check .errors."""
    res = Result()
    symbols = res.symbols
    stmts = res.stmts
    deferred = []                   # EQUs waiting on later labels
    pc = org
    ended = False

    labels = set()                  # every label met, a deferred EQU's too

    def define(label, lineno):
        """One definition per label, however it is made: an instruction or
        data label, EQU, or the label on an ORG.  `X NOP / X EQU 5` used to
        assemble, and LD HL,X took the 5."""
        if label in labels:
            raise AsmError(lineno, 'duplicate label %s' % label)
        labels.add(label)

    # ---- pass 1: parse, size, define labels ----
    for lineno, line in enumerate(text.splitlines(), 1):
        if ended:
            break
        try:
            f = split_fields(line, lineno)
            if f is None:
                stmts.append(Stmt(lineno, line, None, None, '', ''))
                continue
            label, op, args, comment = f
            s = Stmt(lineno, line, label, op, args, comment)
            stmts.append(s)
            if op == 'EQU':
                if not label:
                    raise AsmError(lineno, 'EQU needs a label')
                define(label, lineno)
                s.items = Expr(args, lineno)
                try:
                    s.value = s.items.eval(symbols, pc if pc is not None else 0)
                    symbols[label] = s.value
                except Undefined:
                    deferred.append(s)
                s.pc = pc or 0
                continue
            if op == 'ORG':
                try:
                    pc = word_value(Expr(args, lineno).eval(symbols, pc if pc is not None else 0),
                                    lineno, 'ORG')
                except Undefined as u:
                    raise AsmError(lineno, 'ORG needs a value known here: %s undefined' % u.name)
                s.pc = pc
                if label:
                    define(label, lineno)
                    symbols[label] = pc
                continue
            if pc is None:
                if op is None and not label:
                    continue
                raise AsmError(lineno, 'no ORG before the first statement (or pass --org)')
            s.pc = pc
            if label:
                define(label, lineno)
                symbols[label] = pc
            if op is None:
                continue
            if op == 'END':
                s.items = Expr(args, lineno) if args else None
                ended = True
                continue
            if op in ('DEFB', 'DB', 'DEFM', 'DM'):
                s.items = data_items(args, lineno)
                s.size = sum(len(v) if k == 'str' else 1 for k, v in s.items)
            elif op in ('DEFW', 'DW'):
                s.items = data_items(args, lineno)
                s.size = sum(len(v) if k == 'str' else 2 for k, v in s.items)
            elif op in ('DEFS', 'DS'):
                parts = split_operands(args, lineno)
                if not 1 <= len(parts) <= 2:
                    raise AsmError(lineno, 'DEFS takes a size and an optional fill')
                try:
                    s.size = Expr(parts[0], lineno).eval(symbols, pc)
                except Undefined as u:
                    raise AsmError(lineno, 'DEFS needs a size known here: %s undefined' % u.name)
                if s.size < 0:
                    raise AsmError(lineno, 'negative DEFS size')
                s.items = Expr(parts[1], lineno) if len(parts) == 2 else None
            else:
                names = split_operands(args, lineno)
                if op in ALU_DROP_A and len(names) == 2 and names[0] == 'A':
                    names = names[1:]
                elif op in ALU_NEED_A and len(names) == 1:
                    names = ['A'] + names
                s.opnds = [Opnd(t, lineno, symbols, pc) for t in names]
                s.enc, s.entry = choose(op, s.opnds, lineno)
                s.size = s.entry.length
            if pc + s.size > 0x10000:
                # memory ends at 0FFFFH.  Unchecked, a .cmd wrapped the tail
                # to 0000H, a .bin grew past 64K, a .bas POKEd above 65535
                # and a .cas died on a byte of 256; the listing's & 0FFFFH
                # hid all of it.
                size, s.size = s.size, 0
                raise AsmError(lineno, 'the location counter runs past 0FFFFH: '
                                       '%d byte(s) at %04XH' % (size, pc))
            pc += s.size
        except AsmError as e:
            res.errors.append((e.lineno, e.msg))
        except Undefined as u:
            res.errors.append((lineno, 'undefined symbol %s' % u.name))

    # ---- deferred EQUs ----
    for _ in range(len(deferred) + 1):
        left = []
        for s in deferred:
            try:
                s.value = s.items.eval(symbols, s.pc)
                symbols[s.label] = s.value
            except Undefined:
                left.append(s)
            except AsmError as e:
                res.errors.append((e.lineno, e.msg))
        if not left:
            break
        deferred = left
    for s in deferred:
        try:
            s.items.eval(symbols, s.pc)
        except Undefined as u:
            res.errors.append((s.lineno, 'undefined symbol %s' % u.name))
        except AsmError as e:
            res.errors.append((e.lineno, e.msg))

    if res.errors:
        res.errors.sort()
        return res

    # ---- pass 2: emit ----
    seg_org, seg = None, bytearray()

    def flush():
        if seg:
            res.segments.append((seg_org, bytes(seg)))

    for s in stmts:
        op = s.op
        try:
            if op is None or op == 'EQU':
                continue
            if op == 'ORG':
                if seg_org is not None and seg_org + len(seg) == s.pc:
                    continue                # contiguous: keep the block
                flush()
                seg_org, seg = s.pc, bytearray()
                continue
            if op == 'END':
                if s.items is not None:
                    res.entry = word_value(s.items.eval(symbols, s.pc), s.lineno, 'entry')
                break
            if seg_org is None:
                seg_org = s.pc
            out = bytearray()
            if op in ('DEFB', 'DB', 'DEFM', 'DM'):
                for k, v in s.items:
                    out += v if k == 'str' else bytes([byte_value(v.eval(symbols, s.pc), s.lineno)])
            elif op in ('DEFW', 'DW'):
                for k, v in s.items:
                    if k == 'str':
                        out += v
                    else:
                        w = word_value(v.eval(symbols, s.pc), s.lineno)
                        out += bytes((w & 0xFF, w >> 8))
            elif op in ('DEFS', 'DS'):
                fill = byte_value(s.items.eval(symbols, s.pc), s.lineno, 'fill') if s.items else 0
                out += bytes([fill]) * s.size
            else:
                out += encode(s.enc, s.entry, s.opnds, symbols, s.pc, s.lineno)
            if len(out) != s.size:
                raise AsmError(s.lineno, 'internal: pass 1 sized %d bytes, pass 2 emitted %d'
                               % (s.size, len(out)))
            s.bytes = bytes(out)
            seg += out
        except AsmError as e:
            res.errors.append((e.lineno, e.msg))
        except Undefined as u:
            res.errors.append((s.lineno, 'undefined symbol %s' % u.name))
    flush()
    if res.entry is None:
        res.entry = entry if entry is not None else (res.segments[0][0] if res.segments else 0)
    res.errors.sort()
    return res


# ---- command line --------------------------------------------------------------
FORMATS = ('bin', 'cmd', 'cas', 'bas')


def parse_addr(s):
    """A command-line address: decimal, 7D00H, or 0x7D00 as z80.disasm takes it."""
    t = s.strip().upper()
    try:
        v = int(t[2:], 16) if t.startswith('0X') else number(t)
    except ValueError:
        v = None
    if v is None:
        raise argparse.ArgumentTypeError('not a number: %r (decimal, 7D00H or 0x7D00)' % s)
    if v > 0xFFFF:
        raise argparse.ArgumentTypeError('%r is past 0FFFFH' % s)
    return v


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog='python3 -m z80.asm',
        description='Assemble an EDTASM-style Z80 source over the opcode table.')
    ap.add_argument('source', help='the source file (EDTASM style; line numbers optional)')
    ap.add_argument('-o', '--output', metavar='OUT',
                    help='where the object goes; the extension picks the format')
    ap.add_argument('--format', choices=FORMATS,
                    help='bin (raw image), cmd (load module), cas (SYSTEM tape), '
                         'bas (BASIC DATA/POKE loader); default from the -o extension, else bin')
    ap.add_argument('--name', metavar='NAME',
                    help='the six-character program name in a cmd or cas file '
                         '(default: the source file name)')
    ap.add_argument('--org', type=parse_addr, metavar='ADDR',
                    help='the load address when the source has no ORG (decimal or 7D00H)')
    ap.add_argument('--entry', type=parse_addr, metavar='ADDR',
                    help='the entry address when END names none (default: the first ORG)')
    ap.add_argument('--list', metavar='FILE', dest='listing',
                    help='write the listing here (- for stdout); with no -o it goes to stdout anyway')
    ap.add_argument('--symbols', action='store_true',
                    help='print the symbol table after the listing')
    a = ap.parse_args(argv)

    try:
        with open(a.source, 'rb') as f:
            text = f.read().decode('latin-1')
    except OSError as e:
        sys.stderr.write('%s: %s\n' % (a.source, e.strerror))
        return 1
    res = assemble(text, org=a.org, entry=a.entry)
    if res.errors:
        for lineno, msg in res.errors:
            sys.stderr.write('%s:%d: %s\n' % (a.source, lineno, msg))
        sys.stderr.write('%d error(s), nothing written\n' % len(res.errors))
        return 1

    name = a.name or os.path.splitext(os.path.basename(a.source))[0]
    fmt = a.format
    if a.output and not fmt:
        ext = os.path.splitext(a.output)[1].lower().lstrip('.')
        fmt = ext if ext in FORMATS else 'bin'
    if a.output:
        try:
            if fmt == 'bin':
                data = res.to_bin()
            elif fmt == 'cmd':
                data = res.to_cmd(name)
            elif fmt == 'cas':
                data = res.to_cas(name)
            else:
                data = res.to_bas(name).encode('ascii', 'replace')
        except ValueError as e:
            sys.stderr.write('%s: %s\n' % (a.source, e))
            return 1
        try:
            with open(a.output, 'wb') as f:
                f.write(data)
        except OSError as e:
            sys.stderr.write('%s: %s\n' % (a.output, e.strerror))
            return 1
        sys.stderr.write('%s: %d bytes in %d block(s), entry %04XH -> %s (%s, %d bytes)\n'
                         % (a.source, res.size, len(res.segments), res.entry, a.output, fmt, len(data)))

    listing = res.listing()
    if a.symbols:
        listing += '\n' + ''.join('%-12s %04X\n' % (k, v & 0xFFFF)
                                  for k, v in sorted(res.symbols.items(), key=lambda kv: (kv[1], kv[0])))
    if a.listing and a.listing != '-':
        try:
            with open(a.listing, 'w', encoding='latin-1') as f:
                f.write(listing)
        except OSError as e:
            sys.stderr.write('%s: %s\n' % (a.listing, e.strerror))
            return 1
    elif a.listing == '-' or not a.output:
        sys.stdout.write(listing)
    return 0


if __name__ == '__main__':
    sys.exit(main())
