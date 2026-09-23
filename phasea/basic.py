"""Minimal Level II BASIC surface parsing for the Phase A extractor.

Only as much BASIC as loader extraction needs: line/statement splitting
that respects quotes, DATA harvesting in program order, and a constant
expression evaluator for loader bounds and POKE addresses.

This is deliberately NOT an interpreter. Anything it cannot resolve is
returned as None so the caller can FLAG it rather than guess -- the
standing rule for computed addresses.
"""

import re

# A blocked/ corpus file carries an annotation header on line 0 that is
# not part of the original listing; extraction ignores it.
BLOCKED_HDR = re.compile(r'^\s*0\s+REM\s+\*\*\*\s*BLOCKED:')

LINE_RE = re.compile(r'^\s*(\d+)\s?(.*)$', re.S)


def read_source(path):
    with open(path, 'rb') as fh:
        raw = fh.read()
    # Corpus files are byte-exact detokenized images; latin-1 keeps every
    # byte addressable without throwing on high bytes.
    return raw.decode('latin-1')


def split_statements(body):
    """Split a line body on ':' outside quotes.

    REM / ' swallow the rest of the line. DATA does NOT -- a ':' ends a
    DATA statement in Level II -- so DATA is split normally.  And inside a
    DATA statement REM and ' are not comments at all: the ROM's cruncher
    leaves DATA text alone up to the next ':' outside quotes, so
    `DATA IT'S,5` and `DATA PREMIUM,7` are two items each (the 2026-09-19
    audit, L-58: 144 corpus DATA statements lost the items behind one).
    """
    out = []
    cur = []
    in_q = False
    i = 0
    n = len(body)
    while i < n:
        c = body[i]
        if c == '"':
            in_q = not in_q
            cur.append(c)
        elif c == ':' and not in_q:
            out.append(''.join(cur))
            cur = []
        elif not in_q:
            rest = body[i:]
            up = rest.upper()
            if ((up.startswith('REM') or c == "'")
                    and not ''.join(cur).lstrip().upper().startswith('DATA')):
                # comment to end of line; keep it as a statement so
                # callers can see it, but stop splitting
                if cur:
                    out.append(''.join(cur))
                out.append(rest)
                return out
            cur.append(c)
        else:
            cur.append(c)
        i += 1
    out.append(''.join(cur))
    return [s for s in out]


def parse_program(text, drop_blocked_header=True):
    """-> list of (lineno, raw_body, [statements]) in file order."""
    prog = []
    for raw in text.split('\n'):
        raw = raw.rstrip('\r')
        if not raw.strip():
            continue
        if drop_blocked_header and BLOCKED_HDR.match(raw):
            continue
        m = LINE_RE.match(raw)
        if not m:
            continue
        lineno = int(m.group(1))
        body = m.group(2)
        prog.append((lineno, body, split_statements(body)))
    return prog


def is_comment(stmt):
    s = stmt.lstrip()
    return s.startswith("'") or s[:3].upper() == 'REM'


# No \b after DATA: `DATA205,127,...` is a real and common Level II
# line, and \b would refuse it because A and 2 are both word chars.
DATA_RE = re.compile(r'^\s*DATA(.*)$', re.S | re.I)


def data_items(stmt):
    """Numeric DATA items in one DATA statement, or None if not DATA.

    Non-numeric items are returned as None entries so a caller counting
    positions stays aligned with the real READ stream.  An EMPTY item is
    0, a bare DATA one such item: the ROM's number reader (224DH) finds
    nothing and returns 0 (the 2026-09-19 audit, L-59).
    """
    m = DATA_RE.match(stmt)
    if not m:
        return None
    body = m.group(1)
    items = []
    cur = []
    in_q = False
    for c in body:
        if c == '"':
            in_q = not in_q
        elif c == ',' and not in_q:
            items.append(''.join(cur))
            cur = []
            continue
        cur.append(c)
    items.append(''.join(cur))
    out = []
    for it in items:
        t = it.strip()
        out.append(0 if t == '' else parse_number(t))
    return out


NUM_RE = re.compile(r'^[+-]?\d+$')
HEX_RE = re.compile(r'^&H([0-9A-F]+)$', re.I)
OCT_RE = re.compile(r'^&O?([0-7]+)$', re.I)


def parse_number(tok):
    """Literal -> int, or None when the token is not an integer literal."""
    t = tok.strip().strip('"')
    if not t:
        return None
    t = t.replace(' ', '')
    if NUM_RE.match(t):
        return int(t)
    m = HEX_RE.match(t)
    if m:
        return int(m.group(1), 16)
    m = OCT_RE.match(t)
    if m:
        return int(m.group(1), 8)
    if re.match(r'^[+-]?\d*\.\d+$', t):
        f = float(t)
        return int(f) if f == int(f) else None
    return None


# --------------------------------------------------------------------
# Constant expression evaluation
# --------------------------------------------------------------------

TOKEN_RE = re.compile(r'&H[0-9A-Fa-f]+|\d+\.\d+|\d+|[A-Za-z][A-Za-z0-9]*[%!#$]?'
                      r'|[()+\-*/]')


def eval_const(expr, symbols=None):
    """Evaluate a constant integer expression.

    Handles integer/hex literals, + - * /, parentheses, and symbol
    lookup through `symbols`. Returns None on anything unresolvable --
    a function call, a string, an unknown variable, division that is
    not exact. Never guesses.
    """
    if expr is None:
        return None
    symbols = symbols or {}
    s = expr.strip()
    if not s:
        return None
    toks = TOKEN_RE.findall(s)
    if not toks or ''.join(toks) != re.sub(r'\s+', '', s):
        return None                      # unparsed residue -> refuse
    pos = [0]

    def peek():
        return toks[pos[0]] if pos[0] < len(toks) else None

    def take():
        t = peek()
        pos[0] += 1
        return t

    def primary():
        t = take()
        if t is None:
            raise ValueError
        if t == '(':
            v = expression()
            if take() != ')':
                raise ValueError
            return v
        if t == '-':
            return -primary()
        if t == '+':
            return primary()
        n = parse_number(t)
        if n is not None:
            return n
        if t.upper() in symbols:
            return symbols[t.upper()]
        raise ValueError

    def term():
        v = primary()
        while peek() in ('*', '/'):
            o = take()
            r = primary()
            if o == '*':
                v = v * r
            else:
                if r == 0 or v % r:
                    raise ValueError
                v = v // r
        return v

    def expression():
        v = term()
        while peek() in ('+', '-'):
            o = take()
            r = term()
            v = v + r if o == '+' else v - r
        return v

    try:
        v = expression()
    except (ValueError, IndexError, TypeError):
        return None
    if pos[0] != len(toks):
        return None
    return v


ASSIGN_RE = re.compile(r'^\s*(?:LET\s+)?([A-Za-z][A-Za-z0-9]*[%!#]?)\s*=\s*(.+)$',
                       re.S)


NAME_RE = re.compile(r'([A-Za-z][A-Za-z0-9]*)([%!#$]?)')


def var_key(name):
    """The variable a name IS: Level II keeps two characters and the type.

    ML, MLOAD and ML! are one variable; ML% and ML$ are others. A symbol
    is constant only if nothing assigns to its variable under any name.
    """
    m = NAME_RE.match(name.strip())
    if not m:
        return None
    suffix = m.group(2)
    return m.group(1)[:2].upper() + ('' if suffix == '!' else suffix)


def _split_top(text):
    """Split on commas outside quotes and parentheses."""
    out, cur, depth, in_q = [], [], 0, False
    for c in text:
        if c == '"':
            in_q = not in_q
        elif not in_q and c == '(':
            depth += 1
        elif not in_q and c == ')':
            depth -= 1
        elif not in_q and c == ',' and depth == 0:
            out.append(''.join(cur))
            cur = []
            continue
        cur.append(c)
    out.append(''.join(cur))
    return out


def stored_names(stmt):
    """Variables a statement stores into OTHER than by a plain assignment:
    the targets of INPUT, LINE INPUT, INPUT#, READ and FOR. Array elements
    are left out (they are never symbols)."""
    s = stmt.strip()
    up = s.upper()
    m = re.match(r'FOR\s*([A-Z][A-Z0-9]*?[%!#]?)\s*=', up)
    if m:
        return [m.group(1)]
    m = re.match(r'(?:LINE\s*)?INPUT|READ', up)
    if not m:
        return []
    rest = s[m.end():].lstrip()
    if rest.startswith('#'):                         # INPUT#n,
        rest = rest.partition(',')[2]
    rest = rest.lstrip()
    if rest.startswith('"'):                         # INPUT "PROMPT";
        end = rest.find('"', 1)
        rest = rest[end + 1:] if end > 0 else ''
        rest = rest.lstrip().lstrip(';,')
    out = []
    for item in _split_top(rest):
        m = NAME_RE.match(item.strip())
        if m and '(' not in item:
            out.append(m.group(0))
    return out


# IF is reserved: no variable starts with it, so `IFA=1THEN...` is an IF.
IF_RE = re.compile(r'^\s*IF', re.I)


class Symbols(dict):
    """constant_symbols' result: name -> value, plus WHERE a symbol stops
    being one.

    The dict itself holds only symbols that are constant everywhere.
    `at(lineno)` is the view for a use on that line: it adds the symbols
    that INPUT, READ, FOR or an IF branch store into only FURTHER DOWN the
    listing. Loop and scratch names are reused all over a program
    (meltdown.bas sets X=-1073, pokes its routine at X+I on the same line,
    and runs FOR X= 250 lines later), so a store bans from its own line
    on, in listing order, not everywhere.
    """

    def __init__(self, vals=(), later=None, events=None):
        dict.__init__(self, vals)
        self.later = later or {}
        self.events = events or {}      # variable -> [(lineno, is_store)]

    def at(self, lineno):
        out = dict(self)
        for k, v in self.later.items():
            seen = [st for ln, st in self.events[var_key(k)] if ln <= lineno]
            # the last thing the listing did to it, down to this line: a
            # store bans it, the constant assigned again gives it back
            # (compkorn.bas: Y=217, FOR Y= at 49, Y=217 again at 1010)
            if seen and not seen[-1]:
                out[k] = v
        return out


COND_RE = re.compile(r'^\s*IF(.+?)(<=|>=|=<|=>|<>|><|<|>|=)(.+?)(?:THEN|GOTO)',
                     re.I | re.S)


def _const_condition(st, symbols):
    """True/False when an IF compares two constants, else None."""
    m = COND_RE.match(st)
    if not m:
        return None
    a, b = eval_const(m.group(1), symbols), eval_const(m.group(3), symbols)
    if a is None or b is None:
        return None
    op = m.group(2)
    return {'<': a < b, '>': a > b, '=': a == b, '<>': a != b, '><': a != b,
            '<=': a <= b, '=<': a <= b, '>=': a >= b, '=>': a >= b}[op]


def constant_symbols(prog, before_line=None):
    """Symbols assigned an unambiguous integer constant -> Symbols.

    A symbol assigned more than one distinct constant, or assigned any
    non-constant expression, is dropped -- an ambiguous base is an
    unresolved base. One that INPUT, READ or FOR stores into, or that is
    assigned behind an IF (the THEN and ELSE clauses, and every statement
    after them on the line, run only sometimes), is dropped from that line
    on (Symbols.at):
        ML=32000:INPUT "LOAD ADDRESS";ML
    is a base the user chooses, and extracting it at 32000 with high
    confidence would be a guess. One IF is read through: a condition on
    constants, the signed-address idiom
        MS=65001:IF MS>32767 THEN MS=MS-65536
    whose branch is known and whose two values are one address.
    Identity is the two-character variable (var_key): MLOAD=5 unsettles ML.
    """
    vals = {}                     # full name -> value
    keyval = {}                   # variable -> the one constant seen
    banned = set()                # variables, banned everywhere
    events = {}                   # variable -> [(lineno, is_store)], in order

    def stored(key, lineno):
        events.setdefault(key, []).append((lineno, True))

    def visible():
        return {k: x for k, x in vals.items()
                if var_key(k) not in banned
                and not events[var_key(k)][-1][1]}

    for lineno, _body, stmts in prog:
        if before_line is not None and lineno >= before_line:
            break
        conditional = False
        for st in stmts:
            if is_comment(st):
                continue
            clauses = [st]
            same_address = False
            if IF_RE.match(st):
                m = re.search(r'THEN|GOTO', st, re.I)
                clauses = re.split(r'ELSE', st[m.end():], flags=re.I) if m else []
                known = None if conditional else _const_condition(st, visible())
                if known is True and len(clauses) == 1:
                    same_address = True           # the branch always runs
                elif known is False and len(clauses) == 1:
                    continue                      # and this one never does
                else:
                    conditional = True
            for cl in clauses:
                for name in stored_names(cl):
                    stored(var_key(name), lineno)
                m = ASSIGN_RE.match(cl)
                if not m:
                    continue
                name = m.group(1).upper()
                head = cl.lstrip().upper()
                if head.startswith(('IF', 'FOR', 'DEF', 'PRINT', 'INPUT')):
                    continue
                key = var_key(name)
                if conditional:
                    stored(key, lineno)
                    continue
                v = eval_const(m.group(2), visible())
                if v is None:
                    banned.add(key)
                elif key not in keyval:
                    vals[name] = keyval[key] = v
                elif keyval[key] == v or (same_address
                                          and to_addr(keyval[key]) == to_addr(v)):
                    vals.setdefault(name, keyval[key])
                else:
                    banned.add(key)
                events.setdefault(key, []).append((lineno, False))
    ok = {k: v for k, v in vals.items() if var_key(k) not in banned}

    def ever_stored(k):
        return any(st for _ln, st in events[var_key(k)])

    return Symbols({k: v for k, v in ok.items() if not ever_stored(k)},
                   {k: v for k, v in ok.items() if ever_stored(k)}, events)


def to_addr(v):
    """Level II POKE address convention: negatives wrap into 32768..65535."""
    if v is None:
        return None
    return v & 0xFFFF
