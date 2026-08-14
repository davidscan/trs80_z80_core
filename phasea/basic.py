"""Minimal Level II BASIC surface parsing for the Phase A extractor.

Only as much BASIC as loader extraction needs: line/statement splitting
that respects quotes, DATA harvesting in program order, and a constant
expression evaluator for loader bounds and POKE addresses.

This is deliberately NOT an interpreter. Anything it cannot resolve is
returned as None so the caller can FLAG it rather than guess -- the
DESIGN.md rule for computed addresses.
"""

import re

# A blocked/ corpus file carries an annotation header on line 0 that is
# not part of the original listing (DESIGN.md "Mechanical").
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
    DATA statement in Level II -- so DATA is split normally.
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
            if up.startswith('REM') or c == "'":
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
    positions stays aligned with the real READ stream.
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
        if t == '' and len(items) == 1:
            continue
        out.append(parse_number(t))
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


def constant_symbols(prog, before_line=None):
    """Symbols assigned an unambiguous integer constant.

    A symbol assigned more than one distinct constant, or assigned any
    non-constant expression, is dropped -- an ambiguous base is an
    unresolved base.
    """
    vals = {}
    banned = set()
    for lineno, _body, stmts in prog:
        if before_line is not None and lineno >= before_line:
            break
        for st in stmts:
            if is_comment(st):
                continue
            m = ASSIGN_RE.match(st)
            if not m:
                continue
            name = m.group(1).upper()
            head = st.lstrip().upper()
            if head.startswith(('IF', 'FOR', 'DEF', 'PRINT', 'INPUT')):
                continue
            v = eval_const(m.group(2), {k: x for k, x in vals.items()
                                        if k not in banned})
            if v is None:
                banned.add(name)
            elif name in vals and vals[name] != v:
                banned.add(name)
            else:
                vals[name] = v
    return {k: v for k, v in vals.items() if k not in banned}


def to_addr(v):
    """Level II POKE address convention: negatives wrap into 32768..65535."""
    if v is None:
        return None
    return v & 0xFFFF
