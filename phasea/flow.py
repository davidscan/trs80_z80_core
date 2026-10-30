"""Follow the DATA pointer through the program's control flow (re-ruled
2026-10-22: where the walk reaches a READ, its start
replaces adjacency in extract.py).

Line order is not flow (GLOBE's GOSUB, polar2's RUN 400), so the one READ
pointer can only be trusted where the flow is known.  follow() walks the
program from its first line as Level II runs it -- GOTO, GOSUB/RETURN,
FOR/NEXT with bounds it can evaluate (including counts read from the DATA
itself), RESTORE, RUN, and IFs whose condition it can evaluate -- and
records where the pointer is the first time each READ statement runs.

It stops (keeping what it recorded) wherever it cannot know what comes
next: an IF it cannot evaluate whose branches could move the pointer or
the flow, ON n GOTO/GOSUB, a READ inside a loop whose count it does not
know, a RETURN with no GOSUB, running out of DATA, a CLEAR after a READ,
or its step budget.  An IF it cannot evaluate whose branches only assign
or print (or jump over / back across code that reads nothing) is passed,
and what those branches assign becomes unknown; one whose THEN branch only
ends the program (a MEMORY SIZE check's `THEN PRINT ...:STOP`) is taken as
false, since a branch that stops reaches no READ.
"""
import re

from .basic import is_comment, var_key, _split_top, parse_number

BUDGET = 300000


class Stop(Exception):
    pass


class Unknown(Exception):
    pass


# ---------------------------------------------------------------- expressions

_TOK = re.compile(r'\s*(?:(&H[0-9A-F]+|&O[0-7]+|\d+\.?\d*(?:E[+-]?\d+)?|\.\d+(?:E[+-]?\d+)?)'
                  r'|("[^"]*"?)'
                  r'|(<>|><|<=|=<|>=|=>|[-+*/^()<>=,])'
                  r'|([A-Z][A-Z0-9]*[%!#$]?))', re.I)

_FUNCS = {'ABS', 'INT', 'SGN', 'SQR', 'RND', 'LEN', 'ASC', 'VAL', 'CHR$',
          'LEFT$', 'RIGHT$', 'MID$', 'STR$', 'PEEK', 'USR', 'INKEY$', 'POINT',
          'MEM', 'FRE', 'VARPTR', 'INSTR', 'STRING$', 'SIN', 'COS', 'TAN',
          'ATN', 'LOG', 'EXP', 'FIX', 'CINT', 'CSNG', 'CDBL', 'POS', 'TAB'}


def tokens(s):
    out, i = [], 0
    s = s.strip()
    while i < len(s):
        m = _TOK.match(s, i)
        if not m or m.end() == i:
            raise Unknown
        i = m.end()
        num, st, op, name = m.groups()
        if num:
            n = num.upper()
            if n.startswith('&H'):
                out.append(('n', int(n[2:], 16)))
            elif n.startswith('&O'):
                out.append(('n', int(n[2:], 8)))
            else:
                out.append(('n', float(n)))
        elif st is not None:
            out.append(('s', st.strip('"')))
        elif op:
            out.append(('o', op))
        else:
            out.append(('v', name.upper()))
    return out


class Expr:
    """A small evaluator: numbers, strings, variables and array elements
    the walker knows, + - * / ^, comparisons, AND/OR/NOT.  Anything else
    (a function, an unknown variable) raises Unknown."""

    def __init__(self, env):
        self.env = env

    def eval(self, text):
        self.t = tokens(text)
        self.i = 0
        v = self.orx()
        if self.i != len(self.t):
            raise Unknown
        return v

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def orx(self):
        v = self.andx()
        while self.peek() == ('v', 'OR'):
            self.take()
            r = self.andx()
            v = -1 if (int(v) | int(r)) & 0xFFFF == 0xFFFF else (int(v) | int(r))
        return v

    def andx(self):
        v = self.notx()
        while self.peek() == ('v', 'AND'):
            self.take()
            r = self.notx()
            v = int(v) & int(r)
        return v

    def notx(self):
        if self.peek() == ('v', 'NOT'):
            self.take()
            return ~int(self.notx())
        return self.cmp()

    def cmp(self):
        v = self.add()
        k, o = self.peek()
        if k == 'o' and o in ('=', '<>', '><', '<', '>', '<=', '=<', '>=', '=>'):
            self.take()
            r = self.add()
            if isinstance(v, str) != isinstance(r, str):
                raise Unknown
            res = {'=': v == r, '<>': v != r, '><': v != r, '<': v < r,
                   '>': v > r, '<=': v <= r, '=<': v <= r, '>=': v >= r,
                   '=>': v >= r}[o]
            return -1 if res else 0
        return v

    def add(self):
        v = self.mul()
        while self.peek() in (('o', '+'), ('o', '-')):
            o = self.take()[1]
            r = self.mul()
            if isinstance(v, str) or isinstance(r, str):
                if o != '+' or not (isinstance(v, str) and isinstance(r, str)):
                    raise Unknown
                v = v + r
            else:
                v = v + r if o == '+' else v - r
        return v

    def mul(self):
        v = self.unary()
        while self.peek() in (('o', '*'), ('o', '/')):
            o = self.take()[1]
            r = self.unary()
            if isinstance(v, str) or isinstance(r, str):
                raise Unknown
            if o == '*':
                v = v * r
            else:
                if r == 0:
                    raise Unknown
                v = v / r
        return v

    def unary(self):
        if self.peek() == ('o', '-'):
            self.take()
            v = self.unary()
            if isinstance(v, str):
                raise Unknown
            return -v
        if self.peek() == ('o', '+'):
            self.take()
            return self.unary()
        return self.power()

    def power(self):
        v = self.prim()
        while self.peek() == ('o', '^'):
            self.take()
            r = self.prim()
            v = v ** r
        return v

    def prim(self):
        k, x = self.take()
        if k == 'n':
            return x
        if k == 's':
            return x
        if k == 'o' and x == '(':
            v = self.orx()
            if self.take() != ('o', ')'):
                raise Unknown
            return v
        if k == 'v':
            if x in _FUNCS or x.rstrip('$') in _FUNCS:
                raise Unknown
            key = var_key(x)
            if self.peek() == ('o', '('):
                self.take()
                idx = [self.orx()]
                while self.peek() == ('o', ','):
                    self.take()
                    idx.append(self.orx())
                if self.take() != ('o', ')'):
                    raise Unknown
                ak = (key, tuple(int(i) for i in idx))
                if ak in self.env:
                    return self.env[ak]
                raise Unknown
            if key in self.env:
                return self.env[key]
            raise Unknown
        raise Unknown


# ---------------------------------------------------------------- statements

_NUM = r'(\d+)'
GOTO_RE = re.compile(r'^\s*GO\s*TO\s*' + _NUM + r'\s*$', re.I)
GOSUB_RE = re.compile(r'^\s*GO\s*SUB\s*' + _NUM + r'\s*$', re.I)
RETURN_RE = re.compile(r'^\s*RETURN\s*$', re.I)
END_RE = re.compile(r'^\s*(END|STOP)\b', re.I)
RUN_RE = re.compile(r'^\s*RUN\s*(\d*)\s*$', re.I)
RESTORE_RE = re.compile(r'^\s*RESTORE\s*(\d*)\s*$', re.I)
ON_ERR_RE = re.compile(r'^\s*ON\s*ERROR\s*GO\s*TO', re.I)
ON_RE = re.compile(r'^\s*ON\b', re.I)
IF_RE = re.compile(r'^\s*IF(.+?)(THEN|GO\s*TO)(.*)$', re.I | re.S)
FOR_RE = re.compile(r'^\s*FOR\s*([A-Z][A-Z0-9]*[%!#]?)\s*=\s*(.+?)\s*TO\s*'
                    r'(.+?)(?:\s*STEP\s*(.+))?\s*$', re.I | re.S)
NEXT_RE = re.compile(r'^\s*NEXT\s*(.*)$', re.I | re.S)
READ_RE = re.compile(r'^\s*READ\s*(.+)$', re.I | re.S)
INPUT_RE = re.compile(r'^\s*(LINE\s*)?INPUT\b(.*)$', re.I | re.S)
CLEAR_RE = re.compile(r'^\s*CLEAR\b', re.I)
DATA_RE = re.compile(r'^\s*DATA', re.I)   # no \b: `DATA205,...` (basic.py)
ELSE_RE = re.compile(r'^\s*ELSE(.*)$', re.I | re.S)
ELSE_ANY = re.compile(r'ELSE', re.I)
ASSIGN_RE = re.compile(r'^\s*(?:LET\s*)?([A-Z][A-Z0-9]*[%!#$]?)\s*(\(([^=]*)\))?\s*=\s*(.+)$',
                       re.I | re.S)
NEUTRAL_KW = re.compile(r'^\s*(PRINT|\?|POKE|CLS|DIM|DEF|RANDOM|CMD|SET|RESET|OUT|'
                        r'LPRINT|REM|TRON|TROFF|SOUND|ERROR|NAME|POSITION)', re.I)

# a statement that can move the pointer or the flow
FLOWY = re.compile(r'\b(READ|RESTORE|RUN|RETURN|GO\s*SUB|GO\s*TO|END|STOP|NEXT|FOR|ON|CLEAR)\b'
                   r'|\b(THEN|ELSE)\s*\d', re.I)
POINTERY = re.compile(r'\b(READ|RESTORE|RUN|CLEAR)\b', re.I)


def _blank_strings(s):
    return re.sub(r'"[^"]*"?', '""', s)


def _split_else(text):
    """THEN-part / ELSE-part of one statement's text, at a top-level ELSE."""
    t = _blank_strings(text)
    m = re.search(r'ELSE', t, re.I)
    if not m:
        return text, None
    return text[:m.start()], text[m.end():]


def _ends_program(text):
    """Does this branch only do what cannot matter to a later READ --
    print, assign, poke -- and then END or STOP?  (`IF MEM>24497 THEN
    CLS:PRINT"...":STOP`: a branch that ends the program never reaches a
    READ, so the walk goes on as if the condition were false.)"""
    parts = [x.strip() for x in _blank_strings(text).split(':')]
    if not parts or not re.match(r'^(END|STOP)$', parts[-1], re.I):
        return False
    return not any(FLOWY.search(x) or re.match(r'^IF\b', x, re.I)
                   for x in parts[:-1])


def _assigned(text):
    """Variable keys a piece of code might assign (for 'becomes unknown')."""
    out = set()
    for part in re.split(r':|\bTHEN\b|\bELSE\b', _blank_strings(text), flags=re.I):
        m = ASSIGN_RE.match(part)
        if m:
            out.add(var_key(m.group(1)))
        m = re.match(r'^\s*(?:LINE\s*)?(?:INPUT|READ)\b(.*)$', part, re.I | re.S)
        if m:
            for nm in re.findall(r'[A-Z][A-Z0-9]*[%!#$]?', m.group(1), re.I):
                k = var_key(nm)
                if k:
                    out.add(k)
    return out


class Walker:
    def __init__(self, prog, stream, texts):
        self.prog = prog
        self.stream = stream
        self.texts = texts
        self.idx = {}
        for i, (ln, _b, _s) in enumerate(prog):
            self.idx.setdefault(ln, i)
        self.reads_at = {}
        self.env = {}
        self.p = 0
        self.read_any = False
        self.gosubs = []      # (li, si, depth of fors)
        self.fors = []        # [key, cur, end, step, (li, si), known]
        self.steps = 0
        self.why = None

    # -- helpers
    def line_index(self, ln):
        if ln not in self.idx:
            raise Stop('undefined line %d' % ln)
        return self.idx[ln]

    def pos_at_line(self, ln):
        for i, (l2, _si, _v) in enumerate(self.stream):
            if l2 >= ln:
                return i
        return len(self.stream)

    def ev(self, text):
        return Expr(self.env).eval(text)

    def forget(self, keys):
        for k in keys:
            self.env.pop(k, None)
            for ak in [a for a in self.env if isinstance(a, tuple) and a[0] == k]:
                del self.env[ak]

    def neutral_region(self, lo, hi):
        """Lines lo..hi (indexes, inclusive) neither read nor jump outside
        themselves (a GOSUB anywhere counts as not neutral)."""
        if lo > hi:
            return True
        lo_ln, hi_ln = self.prog[lo][0], self.prog[hi][0]
        for i in range(lo, hi + 1):
            for st in self.prog[i][2]:
                if is_comment(st) or DATA_RE.match(st):
                    continue
                s = _blank_strings(st)
                if POINTERY.search(s) or re.search(r'\bRETURN\b|\bON\b|\bEND\b|\bSTOP\b', s, re.I):
                    return False
                for t in re.findall(r'GO\s*SUB\s*(\d+)', s, re.I):
                    if int(t) not in self.idx or not self.reads_nothing_from(self.idx[int(t)]):
                        return False
                s = re.sub(r'GO\s*SUB\s*\d+', '', s, flags=re.I)
                for t in re.findall(r'(?:GO\s*TO|THEN|ELSE)\s*(\d+)', s, re.I):
                    if not lo_ln <= int(t) <= hi_ln:
                        return False
        return True

    def reads_nothing_from(self, li0, limit=3000):
        """Static reach from line index li0 (a GOSUB target): can any
        statement it reaches -- following GOTO, THEN/ELSE n and GOSUB, and
        falling through until an unconditional GOTO, RETURN or END -- move
        the pointer or leave the routine some other way?"""
        seen, todo = set(), [li0]
        while todo:
            li = todo.pop()
            while li < len(self.prog) and li not in seen:
                seen.add(li)
                if len(seen) > limit:
                    return False
                stop_here = False
                for st in self.prog[li][2]:
                    if is_comment(st) or DATA_RE.match(st):
                        if is_comment(st):
                            break
                        continue
                    b = _blank_strings(st)
                    if POINTERY.search(b) or (ON_RE.match(st) and not ON_ERR_RE.match(st)):
                        return False
                    for t in re.findall(r'(?:GO\s*TO|GO\s*SUB|THEN|ELSE)\s*(\d+)', b, re.I):
                        if int(t) not in self.idx:
                            return False
                        todo.append(self.idx[int(t)])
                    if GOTO_RE.match(st) or RETURN_RE.match(st) or END_RE.match(st):
                        stop_here = True
                        break
                if stop_here:
                    break
                li += 1
        return True

    # -- the run
    def run(self):
        li, si = 0, 0
        try:
            while True:
                self.steps += 1
                if self.steps > BUDGET:
                    raise Stop('budget')
                if li >= len(self.prog):
                    raise Stop('end of program')
                stmts = self.prog[li][2]
                if si >= len(stmts):
                    li, si = li + 1, 0
                    continue
                li, si = self.stmt(li, si, stmts[si], top=True)
        except Stop as e:
            self.why = str(e)
        except (Unknown, ValueError, TypeError, OverflowError, ZeroDivisionError,
                IndexError, KeyError, RecursionError) as e:
            self.why = 'internal: %s %s' % (type(e).__name__, e)
        return self.reads_at

    def goto(self, ln):
        return self.line_index(ln), 0

    def stmt(self, li, si, st, top):
        """Execute one statement; return the next (li, si)."""
        nxt = (li, si + 1)
        if not st.strip():
            return nxt
        if is_comment(st):
            return li + 1, 0
        if DATA_RE.match(st):
            return nxt
        if ELSE_RE.match(st):
            return li + 1, 0                 # a THEN branch ran: skip its ELSE
        b = _blank_strings(st)
        if not IF_RE.match(st) and ELSE_ANY.search(b):
            pre = st[:ELSE_ANY.search(b).start()]
            nli, nsi = self.stmt(li, si, pre, top=False)
            return (li + 1, 0) if (nli, nsi) == (li, si + 1) else (nli, nsi)
        if END_RE.match(st):
            raise Stop('END')
        m = GOTO_RE.match(st)
        if m:
            return self.goto(int(m.group(1)))
        m = GOSUB_RE.match(st)
        if m:
            self.gosubs.append((li, si + 1, len(self.fors)))
            return self.goto(int(m.group(1)))
        if RETURN_RE.match(st):
            if not self.gosubs:
                raise Stop('RETURN without GOSUB')
            rli, rsi, depth = self.gosubs.pop()
            del self.fors[depth:]
            return rli, rsi
        m = RUN_RE.match(st)
        if m:
            self.p, self.env, self.fors, self.gosubs = 0, {}, [], []
            return self.goto(int(m.group(1))) if m.group(1) else (0, 0)
        m = RESTORE_RE.match(st)
        if m:
            self.p = self.pos_at_line(int(m.group(1))) if m.group(1) else 0
            return nxt
        if ON_ERR_RE.match(st):
            return nxt
        if ON_RE.match(st):
            raise Stop('ON n GOTO/GOSUB')
        if CLEAR_RE.match(st):
            if self.read_any:
                raise Stop('CLEAR after a READ')
            self.env = {}
            return nxt
        m = IF_RE.match(st)
        if m:
            return self.do_if(li, si, m)
        m = FOR_RE.match(st)
        if m:
            return self.do_for(li, si, m)
        m = NEXT_RE.match(st)
        if m:
            return self.do_next(li, si, m.group(1))
        m = READ_RE.match(st)
        if m:
            self.do_read(li, si, m.group(1))
            return nxt
        m = INPUT_RE.match(st)
        if m:
            self.forget(_assigned(st) | {var_key(n) for n in
                        re.findall(r'[A-Z][A-Z0-9]*[%!#$]?', _blank_strings(m.group(2)), re.I)})
            return nxt
        m = ASSIGN_RE.match(st)
        if m and not NEUTRAL_KW.match(st):
            self.do_assign(m)
            return nxt
        if NEUTRAL_KW.match(st) or re.match(r'^\s*(SYSTEM|CONT|NEW|LIST|EDIT|CLOAD|CSAVE|AUTO|DELETE)\b', st, re.I) is None:
            # a statement that moves neither the pointer nor the flow
            if FLOWY.search(_blank_strings(st)):
                raise Stop('unparsed flow: %r' % st[:40])
            return nxt
        raise Stop('statement %r' % st[:40])

    def do_assign(self, m):
        key = var_key(m.group(1))
        try:
            v = self.ev(m.group(4))
        except Unknown:
            v = None
        if m.group(2):
            try:
                idx = tuple(int(self.ev(x)) for x in _split_top(m.group(3)))
            except Unknown:
                self.forget({key})
                return
            ak = (key, idx)
            if v is None:
                self.env.pop(ak, None)
            else:
                self.env[ak] = v
            return
        if v is None:
            self.env.pop(key, None)
        else:
            if key and not key.endswith('$') and isinstance(v, str):
                self.env.pop(key, None)
                return
            if key and key.endswith('%') and not isinstance(v, str):
                v = int(v // 1) if v >= 0 else -int((-v) // 1)
            self.env[key] = v

    def do_read(self, li, si, targets):
        if any(not f[5] for f in self.fors):
            raise Stop('READ in a loop of unknown count')
        key = (self.prog[li][0], si)
        self.reads_at.setdefault(key, self.p)
        self.read_any = True
        for t in _split_top(targets):
            t = t.strip()
            if self.p >= len(self.stream):
                raise Stop('out of DATA')
            mv = re.match(r'([A-Z][A-Z0-9]*[%!#$]?)\s*(?:\((.*)\))?\s*$', t, re.I)
            if not mv:
                raise Stop('READ target %r' % t)
            k = var_key(mv.group(1))
            if k.endswith('$'):
                v = self.texts[self.p]
            else:
                v = self.stream[self.p][2]
            self.p += 1
            if mv.group(2) is not None:
                try:
                    idx = tuple(int(self.ev(x)) for x in _split_top(mv.group(2)))
                except Unknown:
                    self.forget({k})
                    continue
                if v is None:
                    self.env.pop((k, idx), None)
                else:
                    self.env[(k, idx)] = v
            else:
                if v is None:
                    self.env.pop(k, None)
                else:
                    self.env[k] = v

    def do_for(self, li, si, m):
        key = var_key(m.group(1))
        try:
            a = self.ev(m.group(2))
            b = self.ev(m.group(3))
            s = self.ev(m.group(4)) if m.group(4) else 1
            known = not any(isinstance(x, str) for x in (a, b, s)) and s != 0
        except Unknown:
            a = b = None
            s = 1
            known = False
        # a FOR on a variable already looping drops that loop and those inside it
        for i, f in enumerate(self.fors):
            if f[0] == key:
                del self.fors[i:]
                break
        self.fors.append([key, a, b, s, (li, si + 1), known])
        if known:
            self.env[key] = a
        else:
            self.env.pop(key, None)
        return li, si + 1

    def do_next(self, li, si, names):
        names = [n.strip() for n in _blank_strings(names).split(',') if n.strip()]
        if not names:
            names = [None]
        for n in names:
            if not self.fors:
                raise Stop('NEXT without FOR')
            if n is None:
                i = len(self.fors) - 1
            else:
                k = var_key(n)
                i = max((j for j, f in enumerate(self.fors) if f[0] == k), default=None)
                if i is None:
                    raise Stop('NEXT %s without its FOR' % n)
            del self.fors[i + 1:]
            f = self.fors[i]
            if not f[5]:
                self.fors.pop()
                self.env.pop(f[0], None)
                continue
            # NEXT steps the VARIABLE: the loop body may have assigned it
            # (TOSTYPER's `IF TT$="*" THEN J=NW:NEXT J,I` leaves the loop)
            cur = self.env.get(f[0])
            if cur is None or isinstance(cur, str):
                raise Stop('loop variable %s unknown at NEXT' % f[0])
            f[1] = cur + f[3]
            if (f[3] > 0 and f[1] <= f[2]) or (f[3] < 0 and f[1] >= f[2]):
                self.env[f[0]] = f[1]
                return f[4]
            self.fors.pop()
            self.env[f[0]] = f[1]
        return li, si + 1

    def do_if(self, li, si, m):
        cond, kw, rest = m.group(1), m.group(2), m.group(3)
        then_part, else_part = _split_else(rest)
        if re.match(r'^\s*GO', kw, re.I):
            then_part = then_part      # IF c GOTO n: the THEN part is the line number
        try:
            v = self.ev(cond)
            truth = None if isinstance(v, str) else (v != 0)
        except Unknown:
            truth = None
        stmts = self.prog[li][2]
        if truth is None and not re.match(r'^\s*\d+\s*$', then_part) and _ends_program(
                then_part if else_part is not None
                else ':'.join([then_part] + stmts[si + 1:])):
            truth = False
        if truth is True:
            return self.branch(li, si, then_part)
        if truth is False:
            if else_part is not None:
                if re.search(r'\bIF', _blank_strings(then_part), re.I):
                    raise Stop('nested IF before ELSE, line %d' % self.prog[li][0])
                return self.branch(li, si, else_part)
            for sj in range(si + 1, len(stmts)):
                b = _blank_strings(stmts[sj])
                if re.match(r'^\s*IF', b, re.I) or re.search(r'THEN', b, re.I):
                    if ELSE_ANY.search(b) or any(ELSE_ANY.search(_blank_strings(x)) for x in stmts[sj + 1:]):
                        raise Stop('nested IF before ELSE, line %d' % self.prog[li][0])
                me = ELSE_ANY.search(b)
                if me:
                    return self.branch(li, sj, stmts[sj][me.end():])
            return li + 1, 0
        # unknown: only if what is conditional moves neither the pointer nor
        # the flow (or jumps across code that reads nothing) can the walk go on
        tail = ':'.join([rest] + stmts[si + 1:])
        tb = _blank_strings(tail)
        for t in re.findall(r'GO\s*SUB\s*(\d+)', tb, re.I):
            if int(t) not in self.idx or not self.reads_nothing_from(self.idx[int(t)]):
                raise Stop('IF it cannot decide calls a reading routine, line %d' % self.prog[li][0])
        tb = re.sub(r'GO\s*SUB\s*\d+', '', tb, flags=re.I)
        if POINTERY.search(tb) or re.search(r'\bRETURN\b|\bON\b|\bEND\b|\bSTOP\b|\bNEXT\b|\bFOR\b', tb, re.I):
            raise Stop('IF it cannot decide, line %d' % self.prog[li][0])
        targets = [int(t) for t in re.findall(r'(?:GO\s*TO|THEN|ELSE)\s*(\d+)', tb, re.I)]
        if re.match(r'^\s*\d+\s*$', then_part):
            targets.append(int(then_part))
        here = li
        for t in targets:
            ti = self.line_index(t)
            lo, hi = (ti, here) if ti <= here else (here + 1, ti - 1)
            if not self.neutral_region(lo, hi):
                raise Stop('IF it cannot decide jumps across reading code, line %d' % self.prog[li][0])
        self.forget(_assigned(tail))
        if targets and min(targets) > self.prog[li][0]:
            # both ways reach the target through code that reads nothing:
            # go on at the next line, which falls through to it
            pass
        return li + 1, 0

    def branch(self, li, si, text):
        t = text.strip()
        if re.match(r'^\d+$', t):
            return self.goto(int(t))
        if not t:
            return li, si + 1
        # the branch's first statement is in this statement's text; the
        # rest of the line follows as usual
        nli, nsi = self.stmt(li, si, t, top=False)
        return nli, nsi


def follow(prog, stream, texts):
    """{(lineno, stmt index): DATA stream index} for every READ statement the
    walk reached, at its first run; and why the walk stopped."""
    w = Walker(prog, stream, texts)
    reads = w.run()
    return reads, w.why
