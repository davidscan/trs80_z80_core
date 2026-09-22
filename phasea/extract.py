"""Phase A EXTRACTOR -- BASIC-idiom knowledge.

Turns a rescued listing into zero or more machine-language PAYLOAD
records plus the USR-entry evidence that says whether anything can
reach them. Emits a JSON intermediate:

    {file, idiom, base (int|symbolic), bytes, provenance, confidence}

which is itself a durable corpus artifact -- a manifest of every ML
payload in the collection -- not just plumbing into the classifier.

STANDING RULE: computed addresses this cannot resolve are
FLAGGED, never guessed. "N files unextractable" is a reported category.

A second discipline the corpus forced: NOT EVERY
POKE LOOP IS A MACHINE-CODE LOADER. Loops that stream bytes to a fixed
device address (37E8H printer), or fill video RAM (3C00H-3FFFH), or
walk an offset/value graphics table, are DATA. They are recognised and
bucketed separately so they cannot inflate the gate number.
"""

import os
import re
from dataclasses import dataclass, field, asdict

from .basic import (parse_program, read_source, is_comment, data_items,
                    eval_const, constant_symbols, parse_number, to_addr)

VIDEO_LO, VIDEO_HI = 0x3C00, 0x3FFF
KBD_LO, KBD_HI = 0x3800, 0x38FF
PRINTER_LO, PRINTER_HI = 0x37E0, 0x37FF
USR_VECTOR_LO, USR_VECTOR_HI = 16526, 16527


@dataclass
class Payload:
    file: str
    idiom: str
    base: object                 # int, or None when symbolic
    base_symbol: object          # str when symbolic, else None
    length: int
    bytes: list
    provenance: dict
    confidence: str              # high | medium | low
    flags: list = field(default_factory=list)
    kind: str = 'candidate-ml'   # candidate-ml | device-stream | screen-data
                                 # | table-data | damage


@dataclass
class UsrEntry:
    kind: str                    # vector-poke | def-usr | varptr
    slot: object                 # USR slot number, or None
    addr: object                 # int, or None when symbolic
    symbol: object               # e.g. 'VARPTR(US%(0))'
    line: int


@dataclass
class FileReport:
    file: str
    payloads: list = field(default_factory=list)
    usr_entries: list = field(default_factory=list)
    usr_calls: int = 0
    system_calls: int = 0
    notes: list = field(default_factory=list)

    def to_json(self):
        d = asdict(self)
        return d


# --------------------------------------------------------------------
# DATA stream with adjacency
# --------------------------------------------------------------------

def build_data_index(prog):
    """Flat DATA stream: list of (lineno, stmt_index, value)."""
    out = []
    for lineno, _body, stmts in prog:
        for si, st in enumerate(stmts):
            if is_comment(st):
                continue
            items = data_items(st)
            if items is None:
                continue
            for v in items:
                out.append((lineno, si, v))
    return out


def take_from(stream, start_idx, count):
    """Consume `count` values from stream[start_idx:].

    Returns (values, end_idx, exact_boundary). exact_boundary is True
    when the consumed run ends exactly at the end of a DATA statement --
    the signal that the loader and its DATA block agree, which is what
    makes the endgame FINDING 29 lock checkable.
    """
    vals = []
    i = start_idx
    while i < len(stream) and len(vals) < count:
        vals.append(stream[i][2])
        i += 1
    if len(vals) < count:
        return vals, i, False
    if i >= len(stream):
        exact = True
    else:
        prev = stream[i - 1]
        nxt = stream[i]
        exact = (prev[0], prev[1]) != (nxt[0], nxt[1])
    return vals, i, exact


def stream_pos_after(stream, lineno, stmt_index):
    """Index of the first DATA value at/after a given program position."""
    for i, (ln, si, _v) in enumerate(stream):
        if ln > lineno or (ln == lineno and si > stmt_index):
            return i
    return len(stream)


def stream_pos_at_line(stream, lineno):
    for i, (ln, _si, _v) in enumerate(stream):
        if ln >= lineno:
            return i
    return len(stream)


# --------------------------------------------------------------------
# Loader idiom recognition
# --------------------------------------------------------------------

FOR_RE = re.compile(r'^\s*FOR\s*([A-Za-z][A-Za-z0-9]*[%!#]?)\s*=\s*(.+?)\s*TO\s*'
                    r'(.+?)(?:\s*STEP\s*(.+))?$', re.I | re.S)
# Level II tokenizes keywords, so no space is required before the
# operand: `READD` is READ D, exactly as `FORC=` is FOR C=. Requiring
# \s+ here silently loses the densest (and most common) loader lines.
READ_RE = re.compile(r'^\s*READ\s*(.+)$', re.I | re.S)
POKE_RE = re.compile(r'^\s*POKE\s*(.+?)\s*,\s*(.+)$', re.I | re.S)
RESTORE_RE = re.compile(r'^\s*RESTORE\s*(\d*)\s*$', re.I)
NEXT_RE = re.compile(r'^\s*NEXT\b', re.I)
# String packing (REPLY 4 item b): a routine built as a string and run at
# VARPTR -- A$=CHR$(205)+CHR$(127)+... or STRING$(n,c) terms, or appended
# one byte per loop pass, A$=A$+CHR$(V), from READ.
STR_ASSIGN_RE = re.compile(r'^\s*(?:LET\s*)?([A-Za-z][A-Za-z0-9]*\$)\s*=\s*(.+)$', re.I | re.S)
STR_APPEND_RE = re.compile(r'^\s*(?:LET\s*)?([A-Za-z][A-Za-z0-9]*\$)\s*=\s*\1\s*\+\s*'
                           r'CHR\$\s*\(\s*([A-Za-z][A-Za-z0-9]*[%!#]?)\s*\)\s*$', re.I | re.S)
TERM_CHR_RE = re.compile(r'^\s*CHR\$\s*\((.+)\)\s*$', re.I | re.S)
TERM_STRING_RE = re.compile(r'^\s*STRING\$\s*\((.+?)\s*,\s*(.+)\)\s*$', re.I | re.S)
TERM_LIT_RE = re.compile(r'^\s*"([^"]*)"\s*$', re.S)
VARPTR_STR_RE = re.compile(r'VARPTR\s*\(\s*([A-Za-z][A-Za-z0-9]*\$)\s*\)', re.I)


USR_SINK_RE = re.compile(r'DEF\s*USR|POKE\s*(?:16526|16527|&H408E|&H408F)\b', re.I)
ALIAS_RE = re.compile(r'^\s*(?:LET\s*)?([A-Za-z][A-Za-z0-9]*[%!#]?)\s*=\s*(.+)$', re.I | re.S)


def varptr_strings(prog):
    """The string variables whose VARPTR feeds the USR ENTRY -- a DEF USR
    or a POKE of the 408EH vector that names VARPTR(X$), directly or
    through numeric variables assigned from it, however many hops
    (V=VARPTR(X$):AD=PEEK(V+1)+256*PEEK(V+2):DEFUSR=AD -- the second hop
    was dropped before the 2026-09-19 audit, H-17).  A packed routine is
    always run that way; VARPTR(X$) anywhere else is a string handed to a
    routine as its argument or aliased for a screen trick, and its bytes
    are text."""
    alias = {}                    # numeric var -> string var it was set from
    derived = []                  # (numeric var, the names on its right side)
    sinks = []                    # statements that set the USR entry
    for _ln, _body, stmts in prog:
        for st in stmts:
            if is_comment(st):
                continue
            m = ALIAS_RE.match(st)
            if m and not m.group(1).endswith('$'):
                vs = VARPTR_STR_RE.findall(m.group(2))
                if vs:
                    alias[m.group(1).upper()] = vs[0].upper()
                else:
                    derived.append((m.group(1).upper(), set(
                        x.upper() for x in
                        re.findall(r'[A-Za-z][A-Za-z0-9]*[%!#]?', m.group(2)))))
            if USR_SINK_RE.search(st):
                sinks.append(st)
    # A variable computed from an aliased one is an alias too, to a fixed
    # point: the hops need not be in program order (a subroutine below the
    # DEF USR may take them), so this is not a single pass down the listing.
    grew = True
    while grew:
        grew = False
        for var, names in derived:
            if var not in alias:
                for n in names:
                    if n in alias:
                        alias[var] = alias[n]
                        grew = True
                        break
    out = set()
    for st in sinks:
        for v in VARPTR_STR_RE.findall(st):
            out.add(v.upper())
        for ident in re.findall(r'[A-Za-z][A-Za-z0-9]*[%!#]?', st):
            if ident.upper() in alias:
                out.add(alias[ident.upper()])
    return out
LOADER_SPAN = 4          # lines after the FOR in which its READ/POKE may sit
DEFUSR_RE = re.compile(r'^\s*DEF\s*USR\s*(\d?)\s*=\s*(.+)$', re.I | re.S)
VARPTR_RE = re.compile(r'VARPTR\s*\(\s*([A-Za-z][A-Za-z0-9]*[%!#$]?)\s*'
                       r'(?:\(\s*([^)]*)\s*\))?\s*\)', re.I)
USRCALL_RE = re.compile(r'\bUSR\s*\d?\s*\(', re.I)
ARRAY_READ_RE = re.compile(r'^\s*([A-Za-z][A-Za-z0-9]*%)\s*\(\s*([^)]+)\s*\)\s*$')


def split_args(s):
    out, cur, depth, in_q = [], [], 0, False
    for c in s:
        if c == '"':
            in_q = not in_q
        if not in_q:
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
            elif c == ',' and depth == 0:
                out.append(''.join(cur))
                cur = []
                continue
        cur.append(c)
    out.append(''.join(cur))
    return [x.strip() for x in out]


def classify_destination(base, count, fixed):
    """What is this loop actually writing to? Returns (kind, flag)."""
    if fixed is not None:
        if PRINTER_LO <= fixed <= PRINTER_HI:
            return 'device-stream', 'fixed-address-printer'
        if VIDEO_LO <= fixed <= VIDEO_HI:
            return 'device-stream', 'fixed-address-video'
        return 'device-stream', 'fixed-address'
    if base is None:
        return 'candidate-ml', None
    end = base + max(count - 1, 0)
    if base >= VIDEO_LO and end <= VIDEO_HI:
        return 'screen-data', 'target-video-ram'
    if base >= KBD_LO and end <= KBD_HI:
        return 'device-stream', 'target-keyboard-matrix'
    if base < 0x4000 and end < 0x4000:
        return 'device-stream', 'target-below-4000H'
    return 'candidate-ml', None


def symbols_at(table, lineno):
    """The constants a statement on `lineno` may rely on: a symbol that
    INPUT, READ, FOR or an IF branch stores into is one only ABOVE that
    store (phasea.basic.Symbols). A plain dict is taken as it is."""
    at = getattr(table, 'at', None)
    return at(lineno) if at else table


def find_loaders(path, prog, stream, table):
    """FOR/READ/POKE loops and VARPTR-array loads."""
    payloads = []
    fname = os.path.basename(path)
    packed_ok = varptr_strings(prog)

    # A RESTORE on the line BEFORE the loader redirects it too (REPLY 4
    # item c: `100 RESTORE 900` / `110 FOR ...` was read as adjacent).
    # None: no RESTORE; 0: a bare RESTORE, the program's first DATA.
    prev_restore = None
    consumed = []                 # (start, end, pinned): what loaders above read
    for li, (lineno, _body, stmts) in enumerate(prog):
        symbols = symbols_at(table, lineno)
        restore_target = prev_restore
        prev_restore = None
        restore_si = None
        for si, st in enumerate(stmts):
            m = RESTORE_RE.match(st)
            if m:
                restore_target = int(m.group(1)) if m.group(1) else 0
                prev_restore = restore_target
                restore_si = si

        for si, st in enumerate(stmts):
            fm = FOR_RE.match(st)
            if not fm or is_comment(st):
                continue
            if restore_si is not None and si > restore_si:
                # A loader behind the RESTORE on its own line has consumed
                # it: the pointer moved on, so it is not the next line's
                # loader's too (H-18 by another path: `10 RESTORE 900:FOR
                # ...` / `20 FOR ...` read the same block twice).
                prev_restore = None
            var = fm.group(1).upper()
            start = eval_const(fm.group(2), symbols)
            end = eval_const(fm.group(3), symbols)
            step = eval_const(fm.group(4), symbols) if fm.group(4) else 1

            # Find READ then POKE (or array READ) after the FOR: on this
            # line, or on the next few lines up to the NEXT that closes the
            # loop (REPLY 4 item a: a loader split across lines was filed
            # no-ml-in-listing).  read_line is the READ's own line, which
            # is where the DATA pointer is taken from.
            read_targets = None
            read_si = None
            read_line = lineno
            poke = None
            done = False
            for lj in range(li, min(li + 1 + LOADER_SPAN, len(prog))):
                ln2, _b2, stmts2 = prog[lj]
                for sj in range(si + 1 if lj == li else 0, len(stmts2)):
                    s2 = stmts2[sj]
                    if is_comment(s2):
                        continue
                    if read_targets is None:
                        rm = READ_RE.match(s2)
                        if rm:
                            read_targets = split_args(rm.group(1))
                            read_si, read_line = sj, ln2
                            continue
                        if FOR_RE.match(s2) or NEXT_RE.match(s2):
                            done = True
                            break
                    else:
                        pm = POKE_RE.match(s2)
                        if pm:
                            poke = (pm.group(1), pm.group(2), sj)
                            done = True
                            break
                        am2 = STR_APPEND_RE.match(s2)
                        if am2 and am2.group(1).upper() in packed_ok:
                            # A$=A$+CHR$(V): string packing from DATA
                            poke = ('@STRING@' + am2.group(1).upper(), am2.group(2), sj)
                            done = True
                            break
                        if FOR_RE.match(s2) or NEXT_RE.match(s2):
                            done = True
                            break
                if done:
                    break
            if read_targets is None:
                continue

            # ---- VARPTR-array idiom: READ straight into an integer array
            am = ARRAY_READ_RE.match(read_targets[0]) if read_targets else None
            if poke is None and am and len(read_targets) == 1:
                arr = am.group(1).upper()
                if start is None or end is None or step in (None, 0):
                    payloads.append(_unresolved(fname, 'varptr-array', lineno,
                                                'loop-bounds-unresolved'))
                    continue
                count = (end - start) // step + 1
                if count <= 0:
                    continue
                sp = _data_start(stream, restore_target, read_line, read_si,
                                 consumed)
                vals, end, exact = take_from(stream, sp, count)
                consumed.append((sp, end, _pinned(restore_target, consumed, sp)))
                payloads.append(_make_varptr_payload(
                    fname, arr, lineno, count, vals, exact, restore_target))
                continue

            if poke is None:
                continue

            addr_expr, val_expr, poke_si = poke
            packed_var = addr_expr[8:] if addr_expr.startswith('@STRING@') else None

            # A POKE whose ADDRESS comes out of the READ stream is an
            # address/value table, not a linear code block. Naming that
            # explicitly beats dumping it in `unextractable`, and keeps
            # it out of candidate-ml either way.
            read_vars = set()
            for t in read_targets:
                mv = re.match(r'\s*([A-Za-z][A-Za-z0-9]*[%!#$]?)', t)
                if mv:
                    read_vars.add(mv.group(1).upper())
            addr_ids = set(x.upper() for x in
                           re.findall(r'[A-Za-z][A-Za-z0-9]*[%!#$]?',
                                      addr_expr))
            if addr_ids & read_vars and not packed_var:
                payloads.append(Payload(
                    file=fname, idiom='for-read-poke', base=None,
                    base_symbol=None, length=0, bytes=[],
                    provenance={'loader_line': lineno,
                                'count_declared': None},
                    confidence='none',
                    flags=(['poke-address-from-read-var'] +
                           (['multi-value-read-%d' % len(read_targets)]
                            if len(read_targets) > 1 else [])),
                    kind='table-data'))
                continue

            if start is None or end is None or step in (None, 0):
                payloads.append(_unresolved(fname, 'for-read-poke', lineno,
                                            'loop-bounds-unresolved'))
                continue
            count = (end - start) // step + 1
            if count <= 1:
                continue

            # Resolve the POKE destination relative to the loop variable.
            if packed_var:
                base, fixed, flag = None, None, None
            else:
                base, fixed, flag = resolve_poke_target(addr_expr, var, start,
                                                        step, symbols)
            if base is None and fixed is None and not packed_var:
                payloads.append(_unresolved(fname, 'for-read-poke', lineno,
                                            flag or 'poke-address-unresolved',
                                            count=count))
                continue

            per_iter = len(read_targets)
            if packed_var:
                kind, dflag = 'candidate-ml', None
            else:
                kind, dflag = classify_destination(base, count, fixed)
            flags = [f for f in (flag, dflag) if f]

            if per_iter != 1:
                kind = 'table-data'
                flags.append('multi-value-read-%d' % per_iter)

            sp = _data_start(stream, restore_target, read_line, read_si,
                             consumed)
            need = count * per_iter
            vals, end, exact = take_from(stream, sp, need)
            consumed.append((sp, end, _pinned(restore_target, consumed, sp)))

            conf, cflags = grade(vals, need, exact, restore_target)
            flags.extend(cflags)

            # The POKE's VALUE expression (REPLY 4 item c): `POKE I,A` stores
            # the DATA byte; `POKE I,255-A` or `POKE I,A XOR K` stores a
            # transform of it, so the raw DATA is not the routine.  Flag it
            # and never call it high confidence.
            vm = re.match(r'^\s*([A-Za-z][A-Za-z0-9]*[%!#$]?)\s*$', val_expr)
            if not (vm and vm.group(1).upper() in read_vars):
                flags.append('poke-value-transformed')
                if conf == 'high':
                    conf = 'low'

            if per_iter == 1:
                by = [v & 0xFF for v in vals if v is not None]
            else:
                by = []

            if step != 1:
                flags.append('step-%d' % step)
                if kind == 'candidate-ml':
                    kind = 'table-data'

            payloads.append(Payload(
                file=fname, idiom='string-packed' if packed_var else 'for-read-poke',
                base=base, base_symbol='VARPTR(%s)' % packed_var if packed_var else None,
                length=len(by), bytes=by,
                provenance={'loader_line': lineno, 'count_declared': count,
                            'values_found': len(vals),
                            'data_from': ('restore-%d' % restore_target
                                          if restore_target else
                                          'restore-first' if restore_target == 0
                                          else 'adjacent'),
                            'ends_on_data_boundary': exact,
                            'fixed_address': fixed},
                confidence=conf, flags=flags, kind=kind))

    return payloads


def resolve_poke_target(addr_expr, var, start, step, symbols):
    """Work out the base address of a POKE inside a FOR loop.

    Returns (base, fixed, flag):
      base  -- first address written, when the loop variable indexes it
      fixed -- the single address written, when it does not
    """
    e = addr_expr.strip()
    up = e.upper()
    # The variable as a whole name, its type suffix included: `\b` after
    # a % finds no word boundary, so FOR I%= never matched POKE I%,A and
    # the loader was filed fixed-address-unresolved (the 2026-09-19 audit,
    # H-19).  I and I% are two variables, so a suffix in the address that
    # the loop variable lacks is no match either.
    varpat = re.compile(r'(?<![A-Z0-9])%s(?![A-Z0-9%%!#$])' % re.escape(var))

    if not varpat.search(up):
        # Loop variable absent: a fixed destination -- a device stream.
        f = eval_const(e, symbols)
        if f is None:
            return None, None, 'fixed-address-unresolved'
        return None, to_addr(f), None

    if step != 1:
        return None, None, 'nonunit-step-index'

    # base + var  /  var + base  /  var alone
    probe = dict(symbols)
    probe[var] = start
    v0 = eval_const(e, probe)
    probe[var] = start + 1
    v1 = eval_const(e, probe)
    if v0 is None or v1 is None:
        return None, None, 'poke-address-unresolved'
    if v1 - v0 != 1:
        return None, None, 'poke-stride-%d' % (v1 - v0)
    return to_addr(v0), None, None


def split_plus(s):
    """Split a string expression on the '+' operators outside quotes and
    parentheses."""
    out, depth, q, cur = [], 0, False, []
    for ch in s:
        if ch == '"':
            q = not q
        elif not q:
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            elif ch == '+' and depth == 0:
                out.append(''.join(cur)); cur = []
                continue
        cur.append(ch)
    out.append(''.join(cur))
    return out


def _string_term_bytes(term, symbols):
    """The bytes one term of a string expression contributes, or None."""
    m = TERM_CHR_RE.match(term)
    if m:
        v = eval_const(m.group(1), symbols)
        return None if v is None else [int(v) & 0xFF]
    m = TERM_STRING_RE.match(term)
    if m:
        n = eval_const(m.group(1), symbols)
        c = m.group(2).strip()
        lm = TERM_LIT_RE.match(c)
        cv = ord(lm.group(1)[0]) if lm and lm.group(1) else eval_const(c, symbols)
        if n is None or cv is None or n < 0 or n > 255:
            return None
        return [int(cv) & 0xFF] * int(n)
    m = TERM_LIT_RE.match(term)
    if m:
        return [ord(ch) & 0xFF for ch in m.group(1)]
    return None


def find_string_packed(path, prog, table, min_len=8):
    """A$=CHR$(..)+CHR$(..)+STRING$(..)+"..." (and A$=A$+... continuations)
    with every term constant: the routine's bytes, at the symbolic base
    VARPTR(A$).  A term that cannot be resolved stops the string there
    and flags it; the READ-loop form A$=A$+CHR$(V) is find_loaders' job."""
    fname = os.path.basename(path)
    packed_ok = varptr_strings(prog)
    acc = {}                      # var -> [bytes, first_line, flags]
    for lineno, _body, stmts in prog:
        symbols = symbols_at(table, lineno)
        for st in stmts:
            if is_comment(st) or STR_APPEND_RE.match(st):
                continue
            m = STR_ASSIGN_RE.match(st)
            if not m:
                continue
            var = m.group(1).upper()
            terms = split_plus(m.group(2))
            first = terms[0].strip().upper()
            if first == var:
                terms = terms[1:]
                if var not in acc:
                    acc[var] = [[], lineno, []]
            else:
                acc[var] = [[], lineno, []]
            entry = acc[var]
            for t in terms:
                b = _string_term_bytes(t, symbols)
                if b is None:
                    if 'string-term-unresolved' not in entry[2]:
                        entry[2].append('string-term-unresolved')
                    break
                entry[0].extend(b)
    out = []
    for var, (by, lineno, flags) in acc.items():
        if len(by) < min_len or var not in packed_ok:
            continue
        out.append(Payload(
            file=fname, idiom='string-packed', base=None,
            base_symbol='VARPTR(%s)' % var, length=len(by), bytes=by,
            provenance={'loader_line': lineno, 'count_declared': len(by),
                        'values_found': len(by), 'variable': var,
                        'ends_on_data_boundary': True, 'data_from': 'string-terms'},
            confidence='low' if flags else 'high', flags=flags,
            kind='candidate-ml'))
    return out


def _pinned(restore_target, consumed, sp):
    """Is this loader's place in the stream KNOWN -- a RESTORE of its own,
    or the continuation of a loader whose place was known?"""
    if restore_target is not None:
        return True
    return bool(consumed) and consumed[-1][2] and sp == consumed[-1][1]


def _data_start(stream, restore_target, read_line, read_si, consumed=()):
    """Where the loader's READ starts in the DATA stream: after a RESTORE n
    at line n's DATA, after a bare RESTORE at the program's first DATA,
    otherwise adjacent -- the first DATA after the READ itself.

    Level II READ has ONE pointer (the 2026-09-19 audit, H-18: two loaders
    sharing a block came out with the same bytes, the second at confidence
    high).  `consumed` is what the loaders above this one, in program
    order, read: (start, end, pinned).  Two rules follow the pointer where
    it can be followed, and adjacency keeps the rest, because a pointer
    followed blindly through the whole listing is wrong wherever the flow
    is not the line order (measured 2026-09-22: it lost polar2 and GLOBE):
      - a loader whose adjacent start lands in DATA already read begins
        where that reading stopped;
      - a loader behind one whose place was PINNED -- a RESTORE of its own,
        or the continuation of a pinned one -- continues where it stopped,
        wherever its adjacent DATA is (ld8509b puts each DATA line ABOVE
        its loader, and only the pointer reaches them).
    A RESTORE of the loader's own is an explicit pointer and stands."""
    if restore_target:
        return stream_pos_at_line(stream, restore_target)
    if restore_target == 0:
        return 0
    if consumed and consumed[-1][2]:
        return consumed[-1][1]
    sp = stream_pos_after(stream, read_line, read_si)
    moved = True
    while moved:
        moved = False
        for s, e, _pin in consumed:
            if s <= sp < e:
                sp, moved = e, True
    return sp


def grade(vals, need, exact, restored):
    flags = []
    if len(vals) < need:
        return 'low', ['data-short-%d-of-%d' % (len(vals), need)]
    if any(v is None for v in vals):
        return 'low', ['non-numeric-data']
    oor = [v for v in vals if not (0 <= v <= 255)]
    if oor:
        flags.append('data-out-of-byte-range-%d' % len(oor))
        return 'low', flags
    if not exact:
        flags.append('data-run-not-on-boundary')
        return 'medium', flags
    return ('high' if not restored else 'high'), flags


def _make_varptr_payload(fname, arr, lineno, count, vals, exact, restored):
    flags = []
    conf = 'high'
    if len(vals) < count:
        conf, flags = 'low', ['data-short-%d-of-%d' % (len(vals), count)]
    elif any(v is None for v in vals):
        conf, flags = 'low', ['non-numeric-data']
    elif not exact:
        conf, flags = 'medium', ['data-run-not-on-boundary']
    by = []
    for v in vals:
        if v is None:
            break
        w = v & 0xFFFF
        by.append(w & 0xFF)
        by.append((w >> 8) & 0xFF)
    return Payload(
        file=fname, idiom='varptr-array', base=None,
        base_symbol='VARPTR(%s(0))' % arr, length=len(by), bytes=by,
        provenance={'loader_line': lineno, 'count_declared': count,
                    'values_found': len(vals), 'array': arr,
                    'ends_on_data_boundary': exact,
                    'data_from': 'restore-%d' % restored if restored
                    else 'adjacent'},
        confidence=conf, flags=flags, kind='candidate-ml')


def _unresolved(fname, idiom, lineno, flag, count=None):
    return Payload(file=fname, idiom=idiom, base=None, base_symbol=None,
                   length=0, bytes=[],
                   provenance={'loader_line': lineno,
                               'count_declared': count},
                   confidence='none', flags=[flag], kind='unextractable')


# --------------------------------------------------------------------
# Direct POKE sequences
# --------------------------------------------------------------------

def find_poke_sequences(path, prog, table, min_run=8):
    """Runs of literal `POKE addr,val` at consecutive ascending addresses."""
    fname = os.path.basename(path)
    pokes = []
    for lineno, _body, stmts in prog:
        symbols = symbols_at(table, lineno)
        for st in stmts:
            if is_comment(st):
                continue
            m = POKE_RE.match(st)
            if not m:
                continue
            a = eval_const(m.group(1), symbols)
            v = eval_const(m.group(2), symbols)
            if a is None or v is None or not (0 <= v <= 255):
                pokes.append(None)
                continue
            pokes.append((to_addr(a), v, lineno))
        pokes.append(None)          # a line break ends a run

    out = []
    run = []
    for p in pokes + [None]:
        if p is not None and (not run or p[0] == run[-1][0] + 1):
            run.append(p)
            continue
        if len(run) >= min_run:
            base = run[0][0]
            kind, dflag = classify_destination(base, len(run), None)
            out.append(Payload(
                file=fname, idiom='poke-seq', base=base, base_symbol=None,
                length=len(run), bytes=[x[1] for x in run],
                provenance={'loader_line': run[0][2],
                            'count_declared': len(run),
                            'values_found': len(run),
                            'ends_on_data_boundary': True,
                            'data_from': 'inline'},
                confidence='high', flags=[dflag] if dflag else [],
                kind=kind))
        run = [p] if p is not None else []
    return out


# --------------------------------------------------------------------
# USR entry evidence
# --------------------------------------------------------------------

def find_usr_evidence(prog, table):
    entries = []
    usr_calls = 0
    system_calls = 0
    pending_lo = {}
    for lineno, body, stmts in prog:
        symbols = symbols_at(table, lineno)
        for st in stmts:
            if is_comment(st):
                # a REM can still contain the text 'USR(' -- ignore it
                continue
            usr_calls += len(USRCALL_RE.findall(st))
            if re.search(r'\bSYSTEM\b', st, re.I):
                system_calls += 1

            m = DEFUSR_RE.match(st)
            if m:
                slot = int(m.group(1)) if m.group(1) else 0
                rhs = m.group(2).strip()
                vm = VARPTR_RE.search(rhs)
                if vm:
                    sym = 'VARPTR(%s%s)' % (
                        vm.group(1).upper(),
                        '(%s)' % vm.group(2) if vm.group(2) is not None else '')
                    entries.append(UsrEntry('varptr', slot, None, sym, lineno))
                else:
                    entries.append(UsrEntry('def-usr', slot,
                                            to_addr(eval_const(rhs, symbols)),
                                            None if eval_const(rhs, symbols)
                                            is not None else rhs, lineno))
                continue

            pm = POKE_RE.match(st)
            if pm:
                a = eval_const(pm.group(1), symbols)
                v = eval_const(pm.group(2), symbols)
                if a == USR_VECTOR_LO and v is not None:
                    pending_lo[lineno] = v
                elif a == USR_VECTOR_HI and v is not None:
                    lo = pending_lo.pop(lineno, None)
                    if lo is not None:
                        entries.append(UsrEntry('vector-poke', 0,
                                                (v << 8) | lo, None, lineno))
                    else:
                        entries.append(UsrEntry('vector-poke', 0, None,
                                                'hi-only-%d' % v, lineno))
    return entries, usr_calls, system_calls


# --------------------------------------------------------------------
# raw-bytes-in-code recovery
# --------------------------------------------------------------------

CTRL_OK = {9, 10, 13}


def find_raw_byte_runs(text, min_run=8):
    """Runs of bytes the detokenizer could not render as BASIC text.

    The rule is to bucket these as `raw`, not force them through the
    loader parser. We surface run LENGTHS so the findings can state how
    many are plausibly routines versus how many are stray damage --
    B1.bas's 'raw bytes' are a two-byte fragment, not a routine.
    """
    runs = []
    cur = []
    start = 0
    for i, ch in enumerate(text):
        b = ord(ch)
        printable = (32 <= b <= 126) or b in CTRL_OK
        if not printable:
            if not cur:
                start = i
            cur.append(b)
        else:
            if len(cur) >= min_run:
                runs.append((start, cur))
            cur = []
    if len(cur) >= min_run:
        runs.append((start, cur))
    return runs


def count_nonprintable(text):
    return sum(1 for ch in text
               if not ((32 <= ord(ch) <= 126) or ord(ch) in CTRL_OK))


# --------------------------------------------------------------------
# Top level
# --------------------------------------------------------------------

def extract_file(path):
    fname = os.path.basename(path)
    rep = FileReport(file=fname)
    try:
        text = read_source(path)
    except Exception as e:                       # unreadable file
        rep.notes.append('unreadable: %r' % (e,))
        return rep

    prog = parse_program(text)
    if not prog:
        rep.notes.append('no-basic-lines')
        return rep

    symbols = constant_symbols(prog)
    stream = build_data_index(prog)

    rep.payloads.extend(find_loaders(path, prog, stream, symbols))
    rep.payloads.extend(find_poke_sequences(path, prog, symbols))
    rep.payloads.extend(find_string_packed(path, prog, symbols))

    entries, calls, syscalls = find_usr_evidence(prog, symbols)
    rep.usr_entries = entries
    rep.usr_calls = calls
    rep.system_calls = syscalls

    nb = count_nonprintable(text)
    if nb:
        runs = find_raw_byte_runs(text)
        rep.notes.append('nonprintable-bytes-%d' % nb)
        for off, run in runs:
            rep.payloads.append(Payload(
                file=fname, idiom='raw-bytes', base=None, base_symbol=None,
                length=len(run), bytes=run,
                provenance={'file_offset': off, 'count_declared': len(run),
                            'values_found': len(run),
                            'ends_on_data_boundary': False,
                            'data_from': 'inline-raw'},
                confidence='low', flags=['recovered-from-raw-bytes'],
                kind='candidate-ml'))
        if not runs:
            rep.payloads.append(Payload(
                file=fname, idiom='raw-bytes', base=None, base_symbol=None,
                length=nb, bytes=[],
                provenance={'count_declared': nb, 'values_found': 0},
                confidence='none',
                flags=['raw-bytes-too-short-to-be-a-routine'],
                kind='damage'))
    return rep
