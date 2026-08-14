"""Phase A EXTRACTOR -- BASIC-idiom knowledge.

Turns a rescued listing into zero or more machine-language PAYLOAD
records plus the USR-entry evidence that says whether anything can
reach them. Emits the JSON intermediate defined in DESIGN.md
"LOADER EXTRACTION":

    {file, idiom, base (int|symbolic), bytes, provenance, confidence}

which is itself a durable corpus artifact -- a manifest of every ML
payload in the collection -- not just plumbing into the classifier.

STANDING RULE, DESIGN.md: computed addresses this cannot resolve are
FLAGGED, never guessed. "N files unextractable" is a reported category.

A second discipline the corpus forced (see Z80_FINDINGS.md): NOT EVERY
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


def find_loaders(path, prog, stream, symbols):
    """FOR/READ/POKE loops and VARPTR-array loads."""
    payloads = []
    fname = os.path.basename(path)

    for li, (lineno, _body, stmts) in enumerate(prog):
        # RESTORE appearing on this line redirects the DATA pointer.
        restore_target = None
        for st in stmts:
            m = RESTORE_RE.match(st)
            if m:
                restore_target = int(m.group(1)) if m.group(1) else 0

        for si, st in enumerate(stmts):
            fm = FOR_RE.match(st)
            if not fm or is_comment(st):
                continue
            var = fm.group(1).upper()
            start = eval_const(fm.group(2), symbols)
            end = eval_const(fm.group(3), symbols)
            step = eval_const(fm.group(4), symbols) if fm.group(4) else 1

            # Find READ then POKE (or array READ) later on this line.
            read_targets = None
            read_si = None
            poke = None
            for sj in range(si + 1, len(stmts)):
                s2 = stmts[sj]
                if is_comment(s2):
                    continue
                if read_targets is None:
                    rm = READ_RE.match(s2)
                    if rm:
                        read_targets = split_args(rm.group(1))
                        read_si = sj
                        continue
                else:
                    pm = POKE_RE.match(s2)
                    if pm:
                        poke = (pm.group(1), pm.group(2), sj)
                        break
                    if FOR_RE.match(s2):
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
                sp = (stream_pos_at_line(stream, restore_target)
                      if restore_target else
                      stream_pos_after(stream, lineno, read_si))
                vals, _e, exact = take_from(stream, sp, count)
                payloads.append(_make_varptr_payload(
                    fname, arr, lineno, count, vals, exact, restore_target))
                continue

            if poke is None:
                continue

            addr_expr, val_expr, poke_si = poke

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
            if addr_ids & read_vars:
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
            base, fixed, flag = resolve_poke_target(addr_expr, var, start,
                                                    step, symbols)
            if base is None and fixed is None:
                payloads.append(_unresolved(fname, 'for-read-poke', lineno,
                                            flag or 'poke-address-unresolved',
                                            count=count))
                continue

            per_iter = len(read_targets)
            kind, dflag = classify_destination(base, count, fixed)
            flags = [f for f in (flag, dflag) if f]

            if per_iter != 1:
                kind = 'table-data'
                flags.append('multi-value-read-%d' % per_iter)

            sp = (stream_pos_at_line(stream, restore_target)
                  if restore_target else
                  stream_pos_after(stream, lineno, read_si))
            need = count * per_iter
            vals, _e, exact = take_from(stream, sp, need)

            conf, cflags = grade(vals, need, exact, restore_target)
            flags.extend(cflags)

            if per_iter == 1:
                by = [v & 0xFF for v in vals if v is not None]
            else:
                by = []

            if step != 1:
                flags.append('step-%d' % step)
                if kind == 'candidate-ml':
                    kind = 'table-data'

            payloads.append(Payload(
                file=fname, idiom='for-read-poke',
                base=base, base_symbol=None, length=len(by), bytes=by,
                provenance={'loader_line': lineno, 'count_declared': count,
                            'values_found': len(vals),
                            'data_from': 'restore-%d' % restore_target
                            if restore_target else 'adjacent',
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
    varpat = re.compile(r'\b%s\b' % re.escape(var))

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

def find_poke_sequences(path, prog, symbols, min_run=8):
    """Runs of literal `POKE addr,val` at consecutive ascending addresses."""
    fname = os.path.basename(path)
    pokes = []
    for lineno, _body, stmts in prog:
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

def find_usr_evidence(prog, symbols):
    entries = []
    usr_calls = 0
    system_calls = 0
    pending_lo = {}
    for lineno, body, stmts in prog:
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

    DESIGN.md says bucket these as `raw`, not force them through the
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
