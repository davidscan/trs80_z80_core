"""The corpus traced: z80.trace pointed at the machine code
the family's own tools already find, to measure how much of it control
flow reaches, how much is left unknown, and how many conflicts appear.
Two populations, both read in place:

  extractor  every candidate-ml payload with a concrete load address that
             phasea.extract finds in the pinned input set (the BASIC
             loaders: FOR/READ/POKE and POKE sequences); the entry is the
             file's USR entry when it falls inside the payload, else the
             payload's base.
  sweep      every out/usr_sweep run that reached a USR call: the memory
             the interpreter sent the core (every M line applied in order,
             a full frame starting over from nothing) with every distinct
             CALL entry as an entry point.  Here the image is the whole
             frame (the screen, the system variables, the program image
             too), so the unit scored is the run of bytes the first entry
             sits in, and the whole frame is reported beside it.

Each item is traced twice, without and with --guess-tables, with the
hints files given.  Writes OUT/items.tsv (one row per item and mode),
OUT/json/<item>.<mode>.json (z80.trace's --json for each), and
OUT/summary.json (the inputs: commits, the input-set fingerprint, the
sweep's own inputs, the hints, and the totals).

    python3 tools/trace_corpus.py --hints hints/model1.hints
    python3 tools/trace_corpus.py --hints hints/model1.hints --out out/trace_corpus

Measurement only: nothing here changes the tracer, and no number is a
test gate.  There is no truth for these bytes (unlike the source/object
pairs), so 'code found' is what flow reaches, not a score.
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from z80 import trace, hints as hintmod                           # noqa: E402
from phasea import sweep                                          # noqa: E402
from phasea.extract import extract_file                           # noqa: E402

SWEEP_OUT = os.path.join(HERE, 'out', 'usr_sweep')
MODES = (('plain', False), ('tables', True))


def git(path, *args):
    try:
        return subprocess.run(['git', '-C', path] + list(args), capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def commit(path):
    h = git(path, 'rev-parse', '--short', 'HEAD')
    if h and git(path, 'status', '--porcelain', '--untracked-files=no'):
        h += '+dirty'
    return h


# ---------------------------------------------------------------- inputs

def extractor_items():
    """(name, segments, entries, info) for every concrete candidate-ml payload."""
    files = sweep.input_files()
    paths = [p for p, _, _ in files]
    problem = sweep.input_set_problem(paths)
    out, empty = [], 0
    for path, half, cat in files:
        rep = extract_file(path)
        usr = [e.addr for e in rep.usr_entries if isinstance(e.addr, int)]
        for i, p in enumerate(rep.payloads):
            if p.kind != 'candidate-ml' or not isinstance(p.base, int):
                continue
            data = bytes(b & 0xFF for b in p.bytes)
            if not data:                # a length declared, no bytes found
                empty += 1
                continue
            inside = [a for a in usr if p.base <= a < p.base + len(data)]
            entries = sorted(set(inside)) or [p.base]
            name = '%s__%s__%d' % (half, os.path.basename(path), i)
            out.append((name, [(p.base, data)], entries,
                        {'set': 'extractor', 'file': os.path.relpath(path, sweep.PROGRAMS),
                         'half': half, 'idiom': p.idiom, 'confidence': p.confidence,
                         'usr_entry_inside': bool(inside), 'base': p.base}))
    return out, {'listings': len(paths), 'input_set_problem': problem,
                 'fingerprint': sweep.fingerprint(paths), 'payloads_without_bytes': empty}


_CALL = re.compile(r'^CALL gen=(\d+) full=([01]) .*?\bentry=(\d+)')


def sweep_items():
    """(name, segments, entries, info) for every usr_sweep run with a CALL:
    the memory as the core saw it at the last CALL, every entry called."""
    try:
        results = json.load(open(os.path.join(SWEEP_OUT, 'results.json')))
    except OSError:
        sys.exit('no %s/results.json: run tools/usr_sweep.py first' % SWEEP_OUT)
    cls = {r['file']: r['cls'] for r in results['results']}
    out = []
    for path in sorted(glob.glob(os.path.join(SWEEP_OUT, 'runs', '*.in'))):
        mem, entries, calls = {}, [], 0
        with open(path, 'rb') as f:
            for raw in f:
                line = raw.decode('latin-1').rstrip('\n')
                m = _CALL.match(line)
                if m:
                    calls += 1
                    if m.group(2) == '1':
                        mem = {}
                    e = int(m.group(3))
                    if e not in entries:
                        entries.append(e)
                elif line.startswith('M '):
                    addr, _, vals = line[2:].partition(':')
                    a = int(addr)
                    for v in vals.split(','):
                        mem[a & 0xFFFF] = int(v) & 0xFF
                        a += 1
        if not calls:
            continue
        name = os.path.basename(path)[:-3]
        fname = name.replace('__', '/')
        segments = _segments(mem)
        # the BASIC program image: from the start-of-program pointer
        # (40A4H) to the end-of-program pointer (40F9H), both in every
        # frame (PROTOCOL.md); an entry inside it is a routine packed in
        # the program's own text, or a wrong address
        pstart = mem.get(0x40A4, 0) | (mem.get(0x40A5, 0) << 8)
        pend = mem.get(0x40F9, 0) | (mem.get(0x40FA, 0) << 8)
        e = entries[0]
        out.append((name, segments, entries,
                    {'set': 'sweep', 'file': fname, 'cls': cls.get(fname),
                     'calls': calls, 'entries': len(entries),
                     'program': [pstart, pend],
                     'where': 'none' if e not in mem else
                     'program' if pstart <= e < pend else 'poked'}))
    return out, results['inputs']


def _segments(mem):
    segs, run, start = [], [], None
    for a in sorted(mem):
        if run and a == start + len(run):
            run.append(mem[a])
        else:
            if run:
                segs.append((start, bytes(run)))
            run, start = [mem[a]], a
    if run:
        segs.append((start, bytes(run)))
    return segs


# ---------------------------------------------------------------- scoring

COLS = ('set', 'item', 'file', 'mode', 'entry', 'entry_in_image', 'unit_total',
        'unit_code', 'unit_guessed_code', 'unit_data', 'unit_guessed_data',
        'unit_unknown', 'frame_total',
        'code', 'guessed_code', 'data', 'guessed_data', 'unknown',
        'conflicts', 'indirect', 'computed', 'external', 'undoc_strong',
        'undoc_weak', 'truncated', 'tables_kept', 'tables_dropped', 'info')


def score(name, segments, entries, info, h, tables):
    res = trace.trace(segments, entries, h, guess=True, tables=tables)
    d = json.loads(trace.to_json(res))
    s = d['summary']
    entry = entries[0]
    unit = next(((org, len(data)) for org, data in segments
                 if org <= entry < org + len(data)), None)
    row = {'set': info['set'], 'item': name, 'file': info['file'],
           'mode': 'tables' if tables else 'plain', 'entry': entry,
           'entry_in_image': unit is not None,
           'unit_total': unit[1] if unit else 0, 'unit_code': 0,
           'unit_guessed_code': 0, 'unit_data': 0, 'unit_guessed_data': 0,
           'unit_unknown': 0,
           'frame_total': s['total'], 'code': s['code'],
           'guessed_code': s['guessed_code'], 'data': s['data'],
           'guessed_data': sum(s['guessed_data'].values()), 'unknown': s['unknown'],
           'conflicts': len(d['conflicts']), 'indirect': len(d['indirect']),
           'computed': len(d['computed']), 'external': len(d['external']),
           'undoc_strong': sum(1 for u in d['undoc'] if u['strong']),
           'undoc_weak': sum(1 for u in d['undoc'] if not u['strong']),
           'truncated': len(d['truncated']), 'tables_kept': len(d['tables']),
           'tables_dropped': len(d['dropped']),
           'info': json.dumps({k: v for k, v in info.items()
                               if k not in ('set', 'file')}, sort_keys=True)}
    if unit:
        lo, hi = unit[0], unit[0] + unit[1]
        for b in d['blocks']:
            a, e = max(b['start'], lo), min(b['end'], hi)
            if a >= e:
                continue
            if b['kind'] == 'code':
                row['unit_code'] += e - a
                if b['guessed']:
                    row['unit_guessed_code'] += e - a
            elif b['kind'] == 'data':
                row['unit_data'] += e - a
            elif b['kind'] == 'guess':
                row['unit_guessed_data'] += e - a
            elif b['kind'] == 'unknown':
                row['unit_unknown'] += e - a
    return row, d


def totals(rows):
    out = {}
    for (s, m), rs in _group(rows).items():
        t = Counter()
        for r in rs:
            for k in COLS[6:-1]:
                t[k] += r[k]
            t['items'] += 1
            t['items_with_conflicts'] += bool(r['conflicts'])
            t['items_entry_outside'] += not r['entry_in_image']
        unit = t['unit_total'] or 1
        out['%s/%s' % (s, m)] = dict(t, unit_code_pct=round(100.0 * t['unit_code'] / unit, 1),
                                     unit_unknown_pct=round(100.0 * t['unit_unknown'] / unit, 1))
    return out


def _group(rows):
    g = {}
    for r in rows:
        g.setdefault((r['set'], r['mode']), []).append(r)
    return g


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--hints', action='append', default=[], help='a hints file (repeatable)')
    ap.add_argument('--out', default=os.path.join(HERE, 'out', 'trace_corpus'))
    ap.add_argument('--set', choices=('extractor', 'sweep'), action='append',
                    help='only this population (default: both)')
    a = ap.parse_args(argv)
    h = hintmod.Hints()
    for path in a.hints:
        h.merge(hintmod.load(path))
    sets = a.set or ['extractor', 'sweep']
    started = time.strftime('%Y-%m-%dT%H:%M:%S')
    items, inputs = [], {
        'core': commit(HERE), 'corpus': commit(os.path.join(HERE, 'corpus')),
        'hints': [os.path.relpath(p, HERE) for p in a.hints], 'started': started,
        'python': sys.version.split()[0]}
    if 'extractor' in sets:
        it, inputs['extractor'] = extractor_items()
        items += it
    if 'sweep' in sets:
        it, inputs['sweep'] = sweep_items()
        items += it
    os.makedirs(os.path.join(a.out, 'json'), exist_ok=True)
    rows = []
    for name, segments, entries, info in items:
        for mode, tables in MODES:
            row, d = score(name, segments, entries, info, h, tables)
            rows.append(row)
            with open(os.path.join(a.out, 'json', '%s.%s.json' % (name, mode)), 'w') as f:
                json.dump(d, f, indent=1)
    with open(os.path.join(a.out, 'items.tsv'), 'w') as f:
        f.write('\t'.join(COLS) + '\n')
        for r in rows:
            f.write('\t'.join(str(r[c]) for c in COLS) + '\n')
    summary = {'inputs': inputs, 'finished': time.strftime('%Y-%m-%dT%H:%M:%S'),
               'items': {s: sum(1 for i in items if i[3]['set'] == s) for s in sets},
               'totals': totals(rows)}
    with open(os.path.join(a.out, 'summary.json'), 'w') as f:
        json.dump(summary, f, indent=1)
    for k, t in summary['totals'].items():
        print('%-18s %4d items: unit %6d bytes, code %6d (%4.1f%%), guessed %4d, data %5d, '
              'guessed data %6d, unknown %6d (%4.1f%%); '
              'conflicts %3d in %3d items; indirect %3d; tables %d/%d; entry outside %d'
              % (k, t['items'], t['unit_total'], t['unit_code'], t['unit_code_pct'],
                 t['unit_guessed_code'], t['unit_data'], t['unit_guessed_data'],
                 t['unit_unknown'], t['unit_unknown_pct'],
                 t['conflicts'], t['items_with_conflicts'], t['indirect'],
                 t['tables_kept'], t['tables_dropped'], t['items_entry_outside']))
    print('written: %s' % a.out)


if __name__ == '__main__':
    main()
