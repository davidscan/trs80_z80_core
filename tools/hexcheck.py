#!/usr/bin/env python3
"""tools/hexcheck.py -- read a scanned assembly listing back by making its
three columns check each other.

    python3 tools/hexcheck.py FILE [--out DIR] [--block N] [-v]

A period assembler printed a listing's address column, its object (hex)
column and its source column from ONE source file, so the three agree by
construction: the source assembles to the hex, and each address is the
one before it plus the bytes on that line.  OCR breaks that agreement,
and every disagreement it leaves is damage in exactly one column --
which makes the other two a check on it, and usually a repair:

    7D00 21403  00140 START  LD HL, 3COOH+64 : SOURCE
    7D03 11003C 00150        Lp DE, 3Co0H : DESTINATION
    7O06 01C003 00160        cp BC, 1024~64 :@ BYTES

Line 1: the source says 21 40 3C once `3COOH` is read in the alphabet a
hex literal is written in, so it is the object column that lost a digit.
Line 2: `Lp` is not an instruction, but those bytes disassemble as
`LD DE,3C00H`, whose text is one slip from what is printed, and whose
operand the source itself confirms.  Line 3: `cp BC,1024-64` assembles
to 01 C0 03, which is what the object column already says, so the
mnemonic is the damage -- and 7O06 must be 7D06, the address before it
plus three bytes.  Nothing here is a guess: two witnesses agree on the
bytes of every line accepted, or the line is reported instead.

WHAT IT DOES
  1. Splits every line into address / hex / line-number / source.  In the
     address, hex and line-number fields the alphabet is digits (and
     A-F), so O->0, l/I->1, S->5, G->6, Z->2, @->0 and their friends
     resolve mechanically.
  2. Chains the addresses: each line's address is the previous one plus
     its length, so a damaged address is repaired from its neighbours and
     a damaged hex field's LENGTH is known independently.
  3. Takes the labels the listing itself defines (a label's value is its
     own line's address) and assembles each source line alone at its own
     address with z80.asm.
  4. Reconciles, line by line, into one of four outcomes:
       clean       the columns agree as printed;
       repaired    one column was damaged and the other two say how -- the
                   bytes rest on two witnesses, as a clean line does;
       object      the source column was destroyed, so the bytes are a
       column      READING OF ONE COLUMN.  It is usually right and worth
       alone       having, but nothing checks it, so the report names
                   every such line and the recovered source marks it;
       unresolved  both columns are damaged past agreement.  What the hex
                   decodes to is printed for a human to judge; nothing is
                   guessed at.
  5. Re-assembles the recovered source as a whole and requires it to
     produce the reconciled bytes.  Exit status is 1 if any line is
     unresolved or that re-assembly disagrees, so a listing is never
     accepted silently.

WHAT IT DOES NOT DO
  Comments carry no bytes, so nothing can check them; they are passed
  through as scanned.  An object field damaged into a DIFFERENT VALID
  INSTRUCTION of the same length, on a line whose source is also gone,
  cannot be caught by any of this -- the columns agree on the wrong
  answer.  That is the residue, and it is why a listing printed beside
  its DATA statements is worth more than either alone.
"""
import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from z80 import asm                                             # noqa: E402
from z80 import disasm                                          # noqa: E402

HEXDIGITS = set('0123456789ABCDEF')

# OCR of a character that can only be a hex digit.  Lower case letters that
# ARE hex digits (a-f) are simply upper-cased; the rest are shapes.
HEXFIX = {
    'O': '0', 'o': '0', 'Q': '0', '@': '0', 'U': '0', 'u': '0', 'D': 'D',
    'l': '1', 'I': '1', 'i': '1', '|': '1', '!': '1', 'L': '1', '[': '1',
    'Z': '2', 'z': '2', 'J': '3', 'S': '5', 's': '5', '$': '5',
    'G': '6', 'g': '9', 'q': '9', 'T': '7', '?': '7', 'Y': '7',
    'P': 'F', 'R': '8', 'H': '4', 'M': 'M', 'N': 'M',
    '¢': 'C', '(': 'C', 'c': 'C', '{': 'C', '©': 'C',
    'x': 'X', '°': '0', '‘': '1', '“': '4',
}
# The line-number column is decimal only.  A-F are left out on purpose: they
# are hex digits, so allowing them would read an object field as a line number.
DIGFIX = {
    'O': '0', 'o': '0', 'Q': '0', '@': '0', 'U': '0', '°': '0',
    'l': '1', 'I': '1', 'i': '1', '|': '1', '!': '1', 'L': '1', '‘': '1',
    'Z': '2', 'z': '2', 'J': '3', 'S': '5', 's': '5', '$': '5',
    'G': '6', 'T': '7', '?': '7', 'R': '8', 'g': '9', 'q': '9',
}

MNEMONICS = sorted(asm.MNEMONICS | asm.DIRECTIVES)
# Characters OCR confuses for one another, for scoring a repair.  Case is
# kept: half of these pairs only look alike in one case ('c'/'e', 'B'/'8').
SHAPES = [set('O0Qo@DU'), set('1lI|!i'), set('2Zz'), set('5S$s'), set('6Gb'),
          set('8B'), set('9gq'), set('7T?'), set('CG('), set('EF'), set('BH'),
          set('PF'), set('AR'), set('MN'), set('UV'), set('nm'), set('rn'),
          set('ce'), set('tf'), set('uv'), set('il'), set('Jj)'), set('yv'),
          set('aou'), set('sS5'), set('LI1'), set('DO0'), set('Xx'), set('Zz'),
          set('IJ'), set('aJ'), set('uL'), set('pD'), set('rP'), set('4H'),
          set('4u'), set('ED'), set('CO'), set('bD'), set('tE'), set('oe')]


SHAPE_OF = {}
for _s in SHAPES:
    for _c in _s:
        SHAPE_OF.setdefault(_c.lower(), set()).update(x.lower() for x in _s)


def same_shape(a, b):
    a, b = a.lower(), b.lower()
    return a == b or b in SHAPE_OF.get(a, ())


def ocr_distance(a, b):
    """Edit distance where an OCR-plausible substitution costs half."""
    prev = [2 * j for j in range(len(b) + 1)]
    for i, ca in enumerate(a, 1):
        cur = [2 * i]
        for j, cb in enumerate(b, 1):
            sub = prev[j - 1] + (0 if ca == cb else (1 if same_shape(ca, cb) else 2))
            cur.append(min(sub, prev[j] + 2, cur[-1] + 2))
        prev = cur
    return prev[-1] / 2.0


def close_enough(scan, cand, share=0.5):
    """Is `cand` near enough to what was scanned to be the same text damaged?
    Half the characters may differ; OCR-plausible ones count as half that."""
    if not scan:
        return False
    return ocr_distance(scan, cand) <= share * max(len(scan), len(cand))


def carries_bytes(args):
    """Does this operand put a value of its own into the encoding, rather than
    only naming registers?  A mnemonic taken from the object column is checked
    by the bytes only where the answer depends on the operand the page printed."""
    return bool(re.search(r'[0-9]|[A-Z_@?][A-Z0-9_@?$]{2,}', (args or '').upper()))


def near_hex(scan, b):
    """Is the scanned object field these bytes, badly read?  The threshold
    grows with the field, but one slip in two bytes is already a lot."""
    if not scan:
        return False
    return ocr_distance(scan.upper(), b.hex().upper()) < max(1.5, 0.2 * len(scan))


def hexlit(v):
    """A hex literal the assembler will read: it must start with a digit."""
    s = '%04X' % (v & 0xFFFF)
    return (s if s[0].isdigit() else '0' + s) + 'H'


def fix_field(tok, table):
    """Map a scanned field into its alphabet, or None if a character cannot be."""
    out = []
    for ch in tok:
        u = ch.upper()
        if u in HEXDIGITS and table is HEXFIX:
            out.append(u)
        elif table is DIGFIX and ch.isdigit():
            out.append(ch)
        elif ch in table:
            out.append(table[ch])
        elif u in table:
            out.append(table[u])
        else:
            return None
    return ''.join(out)


def as_hex(tok):
    v = fix_field(tok, HEXFIX)
    return v if v and all(c in HEXDIGITS for c in v) else None


# Shapes with more than one hex digit behind them.  HEXFIX picks the commonest
# reading; these are the others, tried when the first satisfies nobody.
AMBIGUOUS = {'u': '4', 'U': '4', 'S': '35', 'G': 'C6', 'b': '6D',
             'l': '17', 'I': '17', 'i': '17', 'Z': '72', 'g': '69', 'T': '17',
             'o': 'C0D', 'O': 'C0D', 'Q': 'C0', 'D': '0', 'E': 'F8', 'F': 'E',
             '8': 'B', '0': 'D', '6': '8', 'B': '8', 'C': 'G', 'A': '4'}


def hex_readings(scan, limit=16):
    """Every way the scanned object field reads as hex, commonest first.  That
    field's alphabet is sixteen characters wide, so a shape that could be two
    of them leaves two readings, and the other two columns choose between
    them.  One character is read differently at a time: two slips in one field
    is past what the other columns can settle."""
    first = as_hex(scan)
    if first is None:
        return []
    out = [first]
    for i, ch in enumerate(scan):
        for alt in AMBIGUOUS.get(ch, '') + AMBIGUOUS.get(ch.upper(), ''):
            if alt in HEXDIGITS and alt != first[i]:
                cand = first[:i] + alt + first[i + 1:]
                if cand not in out:
                    out.append(cand)
                if len(out) >= limit:
                    return out
    return out


def as_lineno(tok):
    if not 3 <= len(tok) <= 6:
        return None
    v = fix_field(tok, DIGFIX)
    return int(v) if v and v.isdigit() else None


# ---- one line of a listing ---------------------------------------------------
class Rec:
    """One scanned listing line, and what the three columns make of it."""

    def __init__(self, n, raw):
        self.n = n                  # 1-based line number in the input file
        self.raw = raw.rstrip('\n')
        self.addr = None            # as scanned, repaired later
        self.rawhex = ''            # the object field exactly as scanned
        self.hexs = ''              # hex digits as scanned, alphabet-repaired
        self.dirty = False          # the hex field held characters that are not hex
        self.lineno = None
        self.src = ''
        self.label = self.op = self.args = self.comment = None
        self.fop = self.fargs = None     # the statement as reconciled
        self.bytes = None           # the reconciled bytes
        self.status = 'unparsed'
        self.anote = ''             # what the address chain did
        self.note = ''              # what reconciling did, this round
        self.fixed = ''             # the recovered source line


def split_operand(text):
    """(operand, comment) -- the operand field ends at the first token that
    cannot continue an expression.  OCR loses the ';' more often than not."""
    i = text.find(';')
    if i >= 0 and text[:i].count("'") % 2 == 0:
        return text[:i].strip(), text[i:]
    out, depth, quote = [], 0, False
    for tok in text.split(' '):
        if not tok:
            continue
        if out and depth == 0 and not quote and not re.search(
                r'([,+\-*/(]|\.[A-Z]+\.)$', out[-1]):
            break
        for ch in tok:
            if quote:
                quote = ch != "'"
            elif ch == "'":
                quote = True
            elif ch == '(':
                depth += 1
            elif ch == ')':
                depth = max(0, depth - 1)
        out.append(tok)
    used = 0
    for tok in out:
        used = text.index(tok, used) + len(tok)
    return text[:used], text[used:]         # the span, so a quoted space lives


def parse_line(raw, prev_lineno, prev_addr):
    """Split one scanned line into (addr, hexdigits, dirty, lineno, source).

    The editor's line number is the LAST field before the source, and it is
    the only one of the three whose alphabet is decimal, so the last token of
    the leading run that is four to six decimal characters ends the columns:
    what precedes it is the address and the object bytes, what follows is the
    source.  A line with no line number (a continuation of the bytes above it)
    leaves the address and the hex behind."""
    toks = raw.split()
    if not toks:
        return None
    last = None
    for i, t in enumerate(toks[:4]):
        if 4 <= len(t) <= 6 and as_lineno(t) is not None:
            last = i
    if last == 0:
        # Nothing before it: a line number only when the line reads as one.
        ln = as_lineno(toks[0])
        if not ((len(toks) > 1 and toks[1][:1] in ';*')
                or (prev_lineno is not None and 0 < ln - prev_lineno <= 20)):
            last = None
    lineno = as_lineno(toks[last]) if last is not None else None
    if last is None:
        # No line number: the columns run while the tokens are hex, and what
        # is left must be a statement or nothing, or this is not a listing.
        k = 0
        while k < min(5, len(toks)) and as_hex(toks[k]) is not None:
            k += 1
        cols, rest = toks[:k], toks[k:]
        if rest and rest[0].upper().rstrip(':,.') not in asm.MNEMONICS | asm.DIRECTIVES:
            return None
        src = ' '.join(rest)
    else:
        cols = toks[:last]
        src = ' '.join(toks[last + 1:])
    addr = None
    if cols and 3 <= len(cols[0]) <= 5 and as_hex(cols[0]) is not None:
        a = as_hex(cols[0])
        addr = a if len(a) == 4 else None   # a digit lost or gained: ask the chain
        cols = cols[1:]
    hexs, dirty = [], False
    for t in cols:
        h = as_hex(t)
        if h is None:
            return None
        dirty = dirty or h != t.upper()
        hexs.append(h)
    if addr is None and lineno is None:
        return None
    if lineno is None and not hexs:
        return None
    return addr, ''.join(hexs), ''.join(cols), dirty, lineno, src


# ---- blocks ------------------------------------------------------------------
def find_blocks(text, min_lines=4):
    """Runs of listing-shaped lines in a file that may be mostly prose.  A run
    ends at two lines that are not listing-shaped, or at an END statement; the
    line-number column is too badly scanned to mark a boundary with."""
    lines = text.splitlines()
    blocks, cur, prev_ln, prev_addr, gap = [], [], None, None, 0
    for n, raw in enumerate(lines, 1):
        p = parse_line(raw, prev_ln, prev_addr)
        if p is None:
            gap += 1
            if gap > 1 and cur:
                blocks.append(cur)
                cur, prev_ln, prev_addr = [], None, None
            continue
        gap = 0
        addr, hexs, rawhex, dirty, lineno, src = p
        r = Rec(n, raw)
        r.addr = int(addr, 16) if addr else None
        r.hexs, r.rawhex, r.dirty, r.lineno, r.src = hexs, rawhex, dirty, lineno, src
        cur.append(r)
        if lineno is not None:
            prev_ln = lineno
        if addr:
            prev_addr = int(addr, 16)
        if re.match(r'^\s*(END|ENO|EMD)\b', src.upper()):
            blocks.append(cur)
            cur, prev_ln, prev_addr = [], None, None
    if cur:
        blocks.append(cur)
    return [b for b in blocks if len(b) >= min_lines and sum(1 for r in b if r.hexs) >= 2]


# ---- the check ---------------------------------------------------------------
class Block:
    def __init__(self, recs, source_name='listing'):
        self.recs = recs
        self.name = source_name
        self.symbols = {}
        self.inferred = {}          # names the object code gave a value to
        self.org = None
        self.tally = {}

    def run(self, rounds=3):
        """Settle the block.  A line reconciled in one round gives the address
        chain its true length, which can resolve a neighbour in the next."""
        self.parse_sources()
        for _ in range(rounds):
            before = [(r.addr, r.bytes) for r in self.recs]
            self.chain_addresses()
            self.collect_symbols()
            self.reconcile()
            if before == [(r.addr, r.bytes) for r in self.recs]:
                break
        return self

    # -- 1. the address chain ---------------------------------------------
    def chain_addresses(self):
        """Each address is the one before it plus that line's bytes, so the
        chain repairs a scanned address and, where the hex field lost a
        character, says independently how long the line must be."""
        recs = self.recs
        lens = [self.length_of(r) for r in recs]
        fixed, pc = 0, None
        for i, r in enumerate(recs):
            if r.addr is None:
                if r.hexs and pc is not None:
                    r.addr, r.anote = pc, 'address %04X from the chain' % pc
            elif pc is not None and r.addr != pc \
                    and not self.fits_forward(recs, lens, i) \
                    and ocr_distance('%04X' % r.addr, '%04X' % pc) <= 1.5:
                r.anote = 'address %04X->%04X' % (r.addr, pc)
                r.addr = pc
                fixed += 1
            if r.addr is None:
                pc = None
            elif lens[i] is not None:
                pc = (r.addr + lens[i]) & 0xFFFF
            elif not r.hexs:
                pc = r.addr             # an ORG line moves the counter
            else:
                pc = None               # a damaged object field breaks the chain
        self.tally['addresses repaired'] = fixed

    def length_of(self, r):
        """How many bytes this line holds, as well as it is known."""
        if r.bytes is not None and r.status not in ('unresolved', 'text'):
            return len(r.bytes)
        if r.hexs and len(r.hexs) % 2 == 0:
            return len(r.hexs) // 2
        if not r.hexs and r.addr is not None:
            return 0                    # ORG, EQU, END or a comment
        return None

    @staticmethod
    def fits_forward(recs, lens, i):
        """Does the next addressed line agree with this one's address plus its
        length?  When it does, the scan of this address is right and it is the
        run before it that is broken."""
        if recs[i].addr is None or lens[i] is None:
            return False
        run = 0
        for j in range(i, len(recs)):
            if lens[j] is None:
                return False
            if j > i and recs[j].addr is not None:
                return recs[j].addr == (recs[i].addr + run) & 0xFFFF
            run += lens[j]
        return False

    # -- 2. the listing's own symbols --------------------------------------
    def parse_sources(self):
        for r in self.recs:
            r.label, r.op, r.args, r.comment = split_source(r.src)

    def collect_symbols(self):
        """A label's value is its own line's address -- the listing defines its
        own symbol table, in the column that is hardest to misread.  It is
        rebuilt from scratch each round, because the addresses move."""
        self.symbols, self.inferred = {}, {}
        for r in self.recs:
            if r.label and r.addr is not None and r.label not in self.symbols:
                self.symbols[r.label] = r.addr
        # An EQU names a value, not a place, and the listing prints that value
        # in the address column: two witnesses to the same number.
        for r in self.recs:
            if r.op not in ('EQU', 'DEFL') or not r.label:
                continue
            for args in mechanical(r.args):
                try:
                    v = asm.Expr(args, r.n).eval(self.symbols, r.addr or 0)
                except Exception:
                    continue
                if r.addr is None or v & 0xFFFF == r.addr:
                    self.symbols[r.label] = v
                    r.fargs = args
                    break
            else:
                v = self.symbols.get(r.label)
                r.fargs = hexlit(v) if v is not None else r.args
                if v is not None and r.args != r.fargs:
                    r.note = join(r.note, 'equate %r->%s from the value column'
                                  % (r.args, r.fargs))

    # -- 3/4. reconcile every line -----------------------------------------
    def reconcile(self):
        """No line is accepted on one witness.  The source column counts as a
        witness while it is read as printed (its hex literals put back into the
        hex alphabet is still as printed); once a word has to be replaced the
        repair is the hex column speaking, and the source is only a check on
        it."""
        for r in self.recs:
            r.note = ''
            if r.op in ('EQU', 'DEFL') or (r.op is None and r.label is None) \
                    or not re.match(r'^[A-Z]', r.op or ''):
                r.status, r.bytes = 'text', b''
                continue
            if self.structural(r):
                continue
            self.reconcile_one(r, self.chain_length(r))

    def structural(self, r):
        """A line that emits no object bytes says so by leaving the hex column
        empty, and an ORG's operand is the address column itself -- so these
        need no third witness, only the shape of the line."""
        if r.hexs or r.addr is None or not r.op:
            return False
        if r.op in ('ORG', 'END'):
            r.status, r.bytes = 'clean', b''
            r.fop = r.op
            r.fargs = hexlit(r.addr) if r.op == 'ORG' else ''
            return True
        for word in ('ORG', 'END'):
            if ocr_distance(r.op, word) <= 1.5:
                args = hexlit(r.addr) if word == 'ORG' else ''
                if r.op != word:
                    r.note = join(r.note, 'source %r->%r' % (fieldtext(r.op, r.args),
                                                             fieldtext(word, args)))
                r.status = 'clean' if r.op == word else 'source'
                r.bytes, r.fop, r.fargs = b'', word, args
                return True
        return False

    def reconcile_one(self, r, clen):
        reads = [h for h in hex_readings(r.rawhex) if len(h) % 2 == 0]
        wants = [bytes.fromhex(h) for h in reads]
        want = wants[0] if wants else None

        # (a) the source as printed.  It is a witness in its own right, so one
        # other column agreeing with it is enough.
        # (a) the source as printed.  It is a witness in its own right, so one
        # other column agreeing with it is enough: a reading of the object
        # field that IS these bytes, or one that is these bytes scanned badly.
        # The address chain agrees only about the LENGTH, which says nothing
        # about the content, so it carries a line only where the object field
        # is unreadable and says nothing either.
        why, printed = None, None
        for op, args, tier in source_candidates(r.op, r.args):
            if tier:
                break
            b, err, missing = assemble_one(op, args, r.addr, self.symbols)
            if b is None and missing:
                args, b = self.resolve_name(r, op, args, missing[0], wants, clen)
            if b is None:
                why = why or err
                continue
            printed = printed or b
            if not (b in wants or near_hex(r.rawhex, b)
                    or (not wants and clen == len(b))):
                continue
            self.accept(r, op, args, b, 'clean' if b == want else 'hex')
            return
        # (b) the object column speaks, one reading at a time and the plainest
        # first.  A repair that keeps the operand the page printed has to make
        # exactly those bytes, which is a real check on both columns at once; a
        # repair that takes the operand from the object column has no such
        # check, so the scanned line must still read as what it decodes to.
        for tier in (1, 2):
            for want in wants:
                if clen is not None and clen != len(want):
                    continue
                if tier == 2 and want is not wants[0]:
                    continue        # one reading only: nothing else vouches for it
                hint = from_hex(want, r.addr, self.symbols)
                for op, args, t in source_candidates(r.op, r.args, hint):
                    if t != tier:
                        continue
                    if tier == 2 and not supported(r, op, args):
                        continue
                    if tier == 1 and not carries_bytes(args) \
                            and ocr_distance(r.op or '', op) > 1.0:
                        continue    # the operand puts nothing of its own in
                    b, _, _ = assemble_one(op, args, r.addr, self.symbols)
                    if b != want:
                        continue
                    self.accept(r, op, args, b, 'source' if tier == 1 else 'hexonly')
                    if want != wants[0]:
                        r.note = join(r.note, 'object field read as %s'
                                      % want.hex().upper())
                    return
        r.status, r.bytes = 'unresolved', None
        r.note = join(r.note, why or 'the source and the hex column disagree')
        hint = from_hex(wants[0], r.addr, self.symbols) if wants else None
        if hint:
            r.note = join(r.note, 'the hex reads %r' % fieldtext(*hint))

    def accept(self, r, op, args, b, status):
        """Record the reading.  The SCANNED fields are never overwritten: a
        later round re-reads the page, not this round's repair of it, or a
        repair taken on two witnesses would come back as a clean line."""
        r.bytes, r.status, r.fop, r.fargs = b, status, op, args
        if status == 'hex':
            r.note = join(r.note, 'hex %s->%s' % (r.rawhex or '-', b.hex().upper()))
        if (op, args) != (r.op, r.args):
            r.note = join(r.note, '%s %r->%r'
                          % ('source' if status == 'source' else 'read',
                             fieldtext(r.op, r.args), fieldtext(op, args)))

    def resolve_name(self, r, op, args, name, wants, clen):
        """A name the line uses that nothing defines.  It is first read against
        the listing's own labels -- a scanned name close to a label the listing
        defines is that label, and the address the label sits at is a fact the
        source column never printed.  Only if no label is near it does the
        value come out of the object code."""
        near = sorted((ocr_distance(name, n), n) for n in self.symbols
                      if n != name and n not in self.inferred
                      and close_enough(name, n, 0.35))
        if len(near) == 1 or (len(near) > 1 and near[0][0] < near[1][0]):
            n = near[0][1]
            if not wants and near[0][0] > 1.0:
                return args, None   # nothing would check the substitution
            fixed = re.sub(r'(?<![A-Z0-9])%s(?![A-Z0-9])' % re.escape(name), n, args)
            b, _, _ = assemble_one(op, fixed, r.addr, self.symbols)
            if b is not None and (b in wants or near_hex(r.rawhex, b)
                                  or (not wants and clen == len(b))):
                r.note = join(r.note, '%s is the listing\'s %s' % (name, n))
                return fixed, b
        # No label is near it, so the object code has to say what it is worth.
        # A fitted value proves nothing by itself -- give it a free number and
        # any reading of the field can be made to work -- so the value has to
        # land somewhere the listing accounts for: a line of this very block,
        # or clear of the block altogether, where an outside routine or buffer
        # would be.  A reading that lands mid-instruction is the signature of
        # having fitted the damage, and is refused.
        for strict in (True, False):
            for want in wants:
                if clen is not None and clen != len(want):
                    continue
                b = self.infer(r, op, args, name, want, strict)
                if b is not None:
                    return args, b
        return args, None

    def plausible(self, v, target):
        """Is this a value the listing accounts for?  A branch or call must
        land on a line this listing prints -- the source named it, so the
        listing has to define it somewhere.  Anything else may point outside
        the listing, at a routine or a buffer, but not into the middle of an
        instruction of its own."""
        here = [x.addr for x in self.recs if x.addr is not None]
        if v in here:
            return True
        if target:
            return False
        spans = [x.addr for x in self.recs if x.addr is not None and x.bytes]
        return not spans or not (min(spans) <= v <= max(spans))

    def infer(self, r, op, args, name, want, strict=True):
        """A symbol the listing uses but does not define here has its value in
        the object code: assemble the line twice and read the field out of the
        hex.  The source still says what instruction this is; only the number
        comes from the object column, where the source never printed one."""
        a, _, _ = assemble_one(op, args, r.addr, dict(self.symbols, **{name: 0}))
        b, _, _ = assemble_one(op, args, r.addr, dict(self.symbols, **{name: 1}))
        if a is None or b is None or len(a) != len(want) or len(b) != len(a):
            return None
        pos = [i for i in range(len(a)) if a[i] != b[i]]
        if not pos or len(pos) > 2 or pos != list(range(pos[0], pos[0] + len(pos))):
            return None
        base = int.from_bytes(bytes(a[i] for i in pos), 'little')
        got = int.from_bytes(bytes(want[i] for i in pos), 'little')
        v = (got - base) & ((1 << (8 * len(pos))) - 1)
        out, _, _ = assemble_one(op, args, r.addr, dict(self.symbols, **{name: v}))
        if out != want:
            return None
        ins = disasm.disassemble(want, r.addr)
        branch = len(ins) == 1 and ins[0].op is not None \
            and ins[0].op.kind in ('jump', 'call') and ins[0].target == v
        if not self.plausible(v, branch and strict):
            return None
        if self.inferred.get(name, v) != v:
            r.note = join(r.note, '%s reads %04XH here and %04XH earlier'
                          % (name, v, self.inferred[name]))
            return None
        self.inferred[name] = v
        self.symbols[name] = v
        r.note = join(r.note, '%s = %s from the object code' % (name, hexlit(v)))
        return out

    def chain_length(self, r):
        """The length the address column claims for this line, or None."""
        recs = [x for x in self.recs if x.addr is not None and (x.hexs or x.op == 'ORG')]
        for i, x in enumerate(recs):
            if x is r and i + 1 < len(recs):
                d = (recs[i + 1].addr - r.addr) & 0xFFFF
                return d if 0 < d <= 8 else None
        return None

    # -- 5. the recovered source, and the proof ----------------------------
    def recovered(self):
        out = ['; recovered by hexcheck from %s' % self.name]
        defined = {r.label for r in self.recs
                   if r.label and r.status not in ('unresolved', 'text')}
        free = sorted(n for n in referenced(self.recs) if n not in defined)
        pc = None
        for r in self.recs:
            if r.status == 'unresolved':
                out.append('; UNRESOLVED %s' % r.raw.strip())
                continue
            if r.op in ('EQU', 'DEFL') and r.label:
                out.append('%-8s%-8s%s' % (r.label, 'EQU', r.fargs or r.args))
                continue
            if r.status == 'text':
                if r.src.strip():
                    out.append(';%s' % r.src.strip().lstrip(';*').rstrip())
                continue
            if r.fop == 'END':
                continue
            if r.addr is not None and r.addr != pc and r.fop != 'ORG':
                out.append('%-8s%-8s%s' % ('', 'ORG', hexlit(r.addr)))
                pc = r.addr
            if r.fop == 'ORG':
                pc = r.addr
                out.append('%-8s%-8s%s' % (r.label or '', 'ORG', hexlit(r.addr)))
                continue
            c = comment_of(r)
            if r.status == 'hexonly':
                c = (c + '  ' if c else ';') + '?? the object column alone'
            out.append(('%-8s%-8s%-16s%s'
                        % (r.label or '', r.fop, r.fargs, c)).rstrip())
            pc = (pc or 0) + len(r.bytes or b'')
        if free:
            out[1:1] = ['%-8s%-8s%-9s%s'
                        % (n, 'EQU', hexlit(self.symbols[n]) if n in self.symbols else '0',
                           ';from the object code' if n in self.inferred else
                           ';defined where this listing does not' if n in self.symbols
                           else ';UNKNOWN -- the listing never says')
                        for n in free]
        out.append('%-8s%-8s' % ('', 'END'))
        return '\n'.join(out) + '\n'

    def verify(self):
        """Assemble what we recovered and require the reconciled bytes back."""
        res = asm.assemble(self.recovered())
        if res.errors:
            return ['%d: %s' % e for e in res.errors[:5]]
        image = {}
        for org, data in res.segments:
            for k, b in enumerate(data):
                image[org + k] = b
        bad = []
        for r in self.recs:
            if not r.bytes or r.addr is None:
                continue
            got = bytes(image.get(r.addr + k, 256) for k in range(len(r.bytes)))
            if got != r.bytes:
                bad.append('%04X: recovered %s, reconciled %s'
                           % (r.addr, got.hex().upper(), r.bytes.hex().upper()))
        return bad


def comment_of(r):
    """The scanned comment, with whatever the ';' was read as taken off it.
    Nothing checks a comment -- it carries no bytes -- so it is passed through
    otherwise untouched."""
    c = re.sub(r'^[^A-Za-z0-9\s]+', '', (r.comment or '').strip())
    c = re.sub(r'^[a-z](?=[A-Z])', '', c).strip()
    return (';' + c) if c else ''


def fieldtext(op, args):
    return ('%s %s' % (op or '?', args or '')).strip()


SYMBOL = re.compile(r"(?<![A-Z0-9])[A-Z_@?][A-Z0-9_@?$]*")


def referenced(recs):
    """The names an operand field uses.  The look-behind keeps the tail of a
    hex literal (the C00H of 3C00H) from reading as a symbol."""
    names = set()
    for r in recs:
        if getattr(r, 'status', None) == 'unresolved':
            continue
        text = r.fargs if getattr(r, 'fargs', None) is not None else r.args
        for m in SYMBOL.finditer((text or '').upper()):
            n = m.group(0)
            if n not in asm.REGS and n not in asm.CONDS and asm.number(n) is None:
                names.add(n)
    return names


def split_source(src):
    """(label, op, operand, comment) from a scanned source column."""
    s = src.strip()
    if not s or s[0] in ';*':
        return None, None, None, s
    parts = s.split(None, 1)
    first, rest = parts[0], (parts[1] if len(parts) > 1 else '')
    label = None
    if first.upper().rstrip(':') not in asm.MNEMONICS | asm.DIRECTIVES and rest:
        label = re.sub(r'[^A-Z0-9_@?$]', '', first.upper().rstrip(':'))
        nxt = rest.split(None, 1)
        if nxt and nxt[0].upper() in asm.MNEMONICS | asm.DIRECTIVES:
            first, rest = nxt[0], (nxt[1] if len(nxt) > 1 else '')
        else:
            label = None
            first, rest = parts[0], (parts[1] if len(parts) > 1 else '')
    op = first.upper().rstrip(':,.')
    rest = rest.lstrip()
    if rest.startswith('='):
        rest = rest[1:].lstrip()            # OCR of the listing's column rule
    args, comment = split_operand(rest)
    return label, op, args.strip().rstrip(',.'), comment


def assemble_one(op, args, pc, symbols):
    """The bytes of one statement at pc: (bytes, error, names it needed and
    did not have).  The listing's own labels go in front of it as EQUs, so
    every line is assembled on its own and one bad line poisons no other."""
    if op is None or pc is None:
        return None, 'no instruction', []
    if op not in asm.MNEMONICS and op not in asm.DIRECTIVES:
        return None, 'not an instruction: %r' % op, []
    pre, missing = [], []
    for n in sorted(referenced([_Args(args)])):
        if n in symbols:
            pre.append('%s EQU %d' % (n, symbols[n]))
        else:
            missing.append(n)
    text = '\n'.join(pre) + '\n ORG %d\n %s %s\n' % (pc, op, args or '')
    res = asm.assemble(text)
    if res.errors:
        return None, res.errors[0][1], missing
    if not res.segments:
        return b'', None, missing
    org, data = res.segments[0]
    return (data, None, missing) if org == pc else (None, 'ORG moved', missing)


class _Args:
    def __init__(self, args):
        self.args = args


def from_hex(want, addr, symbols):
    """(op, operand) for bytes that decode as exactly one instruction, with a
    label put back where the listing names that address."""
    ins = disasm.disassemble(want, addr or 0)
    if len(ins) != 1 or ins[0].invalid or ins[0].length != len(want):
        return None
    op, _, args = ins[0].text.partition(' ')
    args = args.strip()
    if ins[0].target is not None:
        for name, v in sorted(symbols.items()):
            if v == ins[0].target:
                args = re.sub(r'(^|,)\(?[0-9][0-9A-F]*H\)?$',
                              lambda m: m.group(0).replace(
                                  re.sub(r'[()]', '', m.group(0).lstrip(',')), name), args)
                break
    return op, args


HEXTOKEN = re.compile(r'(?<![A-Z0-9])([0-9A-F%s][0-9A-F%s]*)H\b'
                      % (''.join(HEXFIX), ''.join(HEXFIX)), re.I)


NAMED = sorted(asm.REGS | asm.CONDS, key=len)


def mechanical(args, op=None):
    """The operand field read again in the alphabets it is printed in: a hex
    literal holds hex digits, a register field holds a register name, a dash
    is a dash, and an instruction that takes no operand never had one -- the
    scan swallowed the comment's semicolon.  Each of these alphabets is a
    handful of symbols wide, so reading the scan back into one of them is
    still the source column as printed, not a guess about what it meant."""
    out = [args]
    if op is not None and () in asm.BY_MNEMONIC.get(op, []) and args:
        out.append('')
    if not args:
        return out
    a = args.replace('~', '-').replace('—', '-').replace('–', '-')
    a = HEXTOKEN.sub(lambda m: (as_hex(m.group(1)) or m.group(1)) + 'H', a)
    a = re.sub(r'\s+', '', a)
    a = re.sub(r'(?<=[A-Z0-9)])[.;](?=[A-Z0-9(])', ',', a)      # the comma
    if a != args:
        out.append(a)
    if len(a) == 1 and a in HEXFIX and HEXFIX[a] in HEXDIGITS:
        out.append(HEXFIX[a])                   # a bit or mode number
    pieces = a.split(',')
    for i, p in enumerate(pieces):
        for alt in as_named(p):
            out.append(','.join(pieces[:i] + [alt] + pieces[i + 1:]))
    b = out[-1] if len(out) > 1 else a
    if b.startswith('C') and b.endswith(')') and '(' not in b:
        out.append('(' + b[1:])                 # (HL) scanned as CHL)
    return out[:8]


def as_named(piece):
    """A one- or two-character operand read as the register or condition it
    looks like.  That alphabet is two dozen names wide, so a shape that is not
    one of them and is one slip from exactly one of them is that one."""
    inner = piece[1:-1] if piece.startswith('(') and piece.endswith(')') else piece
    if len(inner) > 2 or inner in asm.REGS or inner in asm.CONDS:
        return []
    if inner.upper() in asm.REGS or inner.upper() in asm.CONDS:
        return [piece.replace(inner, inner.upper())]
    if len(inner) == 1 and HEXFIX.get(inner, '') in HEXDIGITS:
        return [piece.replace(inner, HEXFIX[inner])]    # a bit or mode number
    near = [n for n in NAMED
            if len(n) == len(inner) and ocr_distance(inner, n) <= 1.0]
    return [piece.replace(inner, near[0])] if len(near) == 1 else []


def source_candidates(op, args, hint=None):
    """(op, operand, tier) worth assembling, keeping the most of what the page
    says first.  The tier says how much of the reading is still the source's:

        0  both fields as printed, read back into their own alphabets
        1  the OPERAND as printed, the mnemonic from the object column
        2  the operand from the object column -- the source only vouches
           for it, because bytes that came out of the hex must match it
    """
    seen = set()

    def give(o, a, tier):
        if o and (o, a) not in seen:
            seen.add((o, a))
            return [(o, a, tier)]
        return []

    out = []
    for a in mechanical(args, op):
        out += give(op, a, 0)
    if hint is None:
        return out
    hop, hargs = hint
    for a in mechanical(args, hop):
        out += give(hop, a, 1)
    if op:
        for m in MNEMONICS:
            if ocr_distance(op, m) <= 1.0:
                for a in mechanical(args, m):
                    out += give(m, a, 1)
    out += give(op, hargs, 2)
    out += give(hop, hargs, 2)
    return out


def norm(s):
    return re.sub(r'\s+', '', (s or '').upper())


def supported(r, op, args):
    """Does the scanned source still say this, allowing for the scan?  One of
    its two fields must survive the repair unchanged, or the whole line must
    still read as a damaged copy of it."""
    if r.args and norm(args) in {norm(a) for a in mechanical(r.args, op)}:
        return True                 # the operand is as printed; the hex names the instruction
    if r.op and norm(op) == norm(r.op):
        return True                 # the mnemonic is as printed; the hex holds the value
    return close_enough(fieldtext(r.op, r.args), fieldtext(op, args))


def join(note, more):
    return (note + '; ' + more).strip('; ') if note else more


# ---- report ------------------------------------------------------------------
ORDER = ['clean', 'hex', 'source', 'hexonly', 'text', 'unresolved']
LABEL = {'clean': 'clean',
         'hex': 'repaired the hex from the source',
         'source': 'repaired the source from the hex',
         'hexonly': 'READ FROM THE OBJECT COLUMN ALONE',
         'text': 'no object bytes',
         'unresolved': 'UNRESOLVED'}


def report(block, verbose, out=sys.stdout):
    counts = {k: 0 for k in ORDER}
    for r in block.recs:
        counts[r.status] = counts.get(r.status, 0) + 1
    out.write('%s: %d lines, %d bytes\n'
              % (block.name, len(block.recs),
                 sum(len(r.bytes or b'') for r in block.recs)))
    for k in ORDER:
        if counts[k]:
            out.write('  %-34s %4d\n' % (LABEL[k], counts[k]))
    for k, v in sorted(block.tally.items()):
        if v:
            out.write('  %-34s %4d\n' % (k, v))
    for r in block.recs:
        note = join(r.anote, r.note)
        if r.status in ('unresolved', 'hexonly') or (verbose and note):
            out.write('  %s %-5s %s\n' % ({'unresolved': '!', 'hexonly': '?'}.get(r.status, ' '),
                                          '%04X' % r.addr if r.addr is not None else '----',
                                          note or r.raw.strip()))
            if r.status == 'unresolved':
                out.write('        scanned: %s\n' % r.raw.strip())
    return counts


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog='python3 tools/hexcheck.py',
        description='Check and repair a scanned assembly listing against its own hex column.')
    ap.add_argument('file', help='the text holding the listing (prose around it is skipped)')
    ap.add_argument('--out', metavar='DIR', help='write each block\'s recovered source here')
    ap.add_argument('--block', type=int, metavar='N', help='check only block N (1-based)')
    ap.add_argument('--min-lines', type=int, default=4, metavar='N',
                    help='the shortest run of listing lines taken for a block (default 4)')
    ap.add_argument('-v', '--verbose', action='store_true', help='name every repair')
    a = ap.parse_args(argv)

    with open(a.file, 'rb') as f:
        text = f.read().decode('utf-8', 'replace')
    blocks = find_blocks(text, a.min_lines)
    if not blocks:
        sys.stderr.write('%s: no listing found\n' % a.file)
        return 2
    if a.out:
        os.makedirs(a.out, exist_ok=True)
    total = {k: 0 for k in ORDER}
    bad = 0
    for i, recs in enumerate(blocks, 1):
        if a.block and i != a.block:
            continue
        b = Block(recs, '%s block %d (lines %d-%d)'
                  % (os.path.basename(a.file), i, recs[0].n, recs[-1].n))
        b.run()
        counts = report(b, a.verbose)
        for k in ORDER:
            total[k] += counts.get(k, 0)
        bad += counts.get('unresolved', 0)
        problems = b.verify()
        for p in problems:
            sys.stdout.write('  ! re-assembly: %s\n' % p)
        bad += len(problems)
        if a.out:
            path = os.path.join(a.out, 'block%02d.asm' % i)
            with open(path, 'w') as f:
                f.write(b.recovered())
            sys.stdout.write('  -> %s\n' % path)
    seen = sum(total.values())
    sys.stdout.write('%d lines: %d clean, %d repaired, %d unresolved\n'
                     % (seen, total['clean'], total['hex'] + total['source'],
                        total['unresolved']))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
