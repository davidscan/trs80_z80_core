#!/usr/bin/env python3
"""tools/romcalls.py -- which ROM entry points do a library's listings call?

    python3 tools/romcalls.py FILE... [--from LIST] [--record OUT.json] [--top N] [-v]

The trap measurement.  The core holds no ROM (the never-commit-ROM rule),
so a routine that calls into 0000H-2FFFH gets a trap that reimplements the
documented entry point, or `ERR rom`.  Which entry points earn a trap is a
question of what the period listings actually call, and hexcheck's
recovered sources are where that can be read off without guessing: this
runs hexcheck over every file given, takes each line it settled on two
witnesses, disassembles the reconciled bytes, and tallies every CALL, JP,
JR and RST whose target lies in ROM.  Lines read off one object column
alone are counted apart -- a reading, not a fact -- and never decide the
order.  Data lines (DEFB, DEFW) are not calls, and are skipped even where
a jump table holds a ROM address.

Give it the programming books, not the ROM disassemblies: a listing of
the ROM itself calls its own routines on every page and says nothing
about what programs need.

Prints one row per entry point, most called first: the address, the name
the period manuals give it (where they give one), how many calls from
two-witness lines, how many more from one-column lines, how many files,
and whether the core serves it today (z80.coprocess.SERVED).  The last
lines give the totals and the served share.  Exit status 0; 2 if no file
held a listing.

--record writes the measurement with its inputs: every file read and
its sha1, the set's fingerprint, the core's commit, and the table.  The
2026-09-17 tally could not be rebuilt (the 2026-09-30 audit, ZM-7): its
"251" counted part files nobody listed, and the books left out were
named nowhere.  --from reads the file list from a file, one path a line.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import hexcheck                                                 # noqa: E402
from z80 import coprocess                                       # noqa: E402
from z80 import disasm                                          # noqa: E402
from z80 import hints                                           # noqa: E402

ROM_TOP = coprocess.ROM_TOP

# The entry points' names come from hints/model1.hints, where each one
# cites its published sources: one table for this report and the tracer.
NAMES = hints.load(os.path.join(ROOT, 'hints', 'model1.hints')).labels

REACH = 64          # bytes between two lines of one run (hexcheck.continues' reach)

DATA_OPS = {'DEFB', 'DB', 'DEFW', 'DW', 'DEFM', 'DM', 'DEFS', 'DS'}


def rom_calls(recs):
    """(target, mnemonic, one_column, rec) for every ROM-range branch in
    the settled lines of one block."""
    out = []
    # A listing assembled at a low address (relocatable code, ORG 0) has
    # its own branches in ROM range: a target inside the block is a call to
    # itself, not to the ROM.
    # "Inside the block" is inside one of its RUNS of lines, not anywhere
    # from its lowest address to its highest: one misread address, or a
    # second ORG far away, stretched that span across the ROM and every
    # real ROM call inside it was counted as a call to itself.  Lines whose
    # addresses lie within REACH of each other are one run (lines the scan
    # lost leave holes that size); an EQU's first column is a value, not a
    # place, and joins nothing.
    spans = []
    for a, n in sorted((r.addr, max(len(r.bytes or b''), getattr(r, 'reserve', None) or 0, 1))
                       for r in recs if r.addr is not None and r.op not in ('EQU', 'DEFL')):
        if spans and a - spans[-1][1] <= REACH:
            spans[-1][1] = max(spans[-1][1], a + n - 1)
        else:
            spans.append([a, a + n - 1])

    def own(target):
        return any(lo <= target <= hi for lo, hi in spans)

    for r in recs:
        if not r.bytes or r.addr is None or r.status not in hexcheck.CONFIDENT + ('hexonly',):
            continue
        if (r.fop or r.op) in DATA_OPS:
            continue
        for ins in disasm.disassemble(r.bytes, r.addr):
            if ins.invalid or ins.op is None or ins.target is None:
                continue
            if ins.op.kind in ('jump', 'call') and ins.target < ROM_TOP \
                    and not own(ins.target):
                out.append((ins.target, ins.text.split()[0], r.status == 'hexonly', r))
    return out


def tally(paths, verbose=False, out=sys.stderr):
    """{target: {'calls': n, 'alone': n, 'files': set, 'ops': set}} over the files."""
    table = {}
    seen = 0
    for path in paths:
        with open(path, 'rb') as f:
            text = f.read().decode('utf-8', 'replace')
        blocks = hexcheck.find_blocks(text)
        if not blocks:
            continue
        seen += 1
        streams = hexcheck.find_data(text)
        found = 0
        for recs in blocks:
            b = hexcheck.Block(recs, os.path.basename(path), streams).run()
            for target, op, alone, r in rom_calls(b.recs):
                row = table.setdefault(target, {'calls': 0, 'alone': 0, 'files': set(), 'ops': set()})
                row['alone' if alone else 'calls'] += 1
                row['files'].add(path)
                row['ops'].add(op)
                found += 1
                if verbose:
                    out.write('  %04XH %-4s %04XH %-8s %s\n'
                              % (r.addr, op, target, 'alone' if alone else r.status, r.raw.strip()))
        if verbose:
            out.write('%s: %d listing%s, %d ROM-range call%s\n'
                      % (path, len(blocks), '' if len(blocks) == 1 else 's',
                         found, '' if found == 1 else 's'))
    return table, seen


def report(table, top=None, out=sys.stdout):
    rows = sorted(table.items(), key=lambda kv: (-(kv[1]['calls'] + kv[1]['alone']), kv[0]))
    if top:
        rows = rows[:top]
    out.write('%-6s %-30s %6s %6s %6s %-6s %s\n'
              % ('entry', 'name', 'calls', '+alone', 'files', 'served', 'by'))
    for target, row in rows:
        out.write('%04XH  %-30s %6d %6d %6d %-6s %s\n'
                  % (target, NAMES.get(target, '-'), row['calls'], row['alone'],
                     len(row['files']), 'yes' if target in coprocess.SERVED else 'no',
                     ','.join(sorted(row['ops']))))
    calls = sum(r['calls'] for r in table.values())
    alone = sum(r['alone'] for r in table.values())
    served = [t for t in table if t in coprocess.SERVED]
    served_calls = sum(table[t]['calls'] for t in served)
    out.write('%d ROM-range calls to %d entry points on two witnesses (%d more from one column); '
              'the core serves %d of the %d entries, %d of the %d calls\n'
              % (calls, len(table), alone, len(served), len(table), served_calls, calls))


def inputs(paths):
    """The input set: each file's path and sha1, and their fingerprint (the
    sha1 of the `sha1  path` lines in the order given)."""
    files = []
    for p in paths:
        with open(p, 'rb') as f:
            files.append({'path': p, 'sha1': hashlib.sha1(f.read()).hexdigest()})
    lines = ''.join('%s  %s\n' % (x['sha1'], x['path']) for x in files)
    try:
        core = subprocess.run(['git', '-C', ROOT, 'rev-parse', '--short', 'HEAD'],
                              capture_output=True, text=True, check=True).stdout.strip()
        if subprocess.run(['git', '-C', ROOT, 'status', '--porcelain', '--untracked-files=no'],
                          capture_output=True, text=True).stdout.strip():
            core += '+dirty'
    except (OSError, subprocess.CalledProcessError):
        core = '?'
    return {'core': core, 'files': len(files),
            'fingerprint': hashlib.sha1(lines.encode()).hexdigest(),
            'when': time.strftime('%Y-%m-%dT%H:%M:%S'), 'list': files}


def record(path, paths, table, seen):
    rows = [{'entry': '%04XH' % t, 'name': NAMES.get(t), 'calls': r['calls'],
             'alone': r['alone'], 'files': len(r['files']), 'served': t in coprocess.SERVED,
             'by': sorted(r['ops'])}
            for t, r in sorted(table.items(),
                               key=lambda kv: (-(kv[1]['calls'] + kv[1]['alone']), kv[0]))]
    meta = inputs(paths)
    meta['files_with_a_listing'] = seen
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump({'inputs': meta, 'table': rows}, f, indent=1)
    os.replace(tmp, path)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog='python3 tools/romcalls.py',
        description='Tally the ROM entry points the listings in these files call.')
    ap.add_argument('files', nargs='*', metavar='FILE', help='text holding scanned listings')
    ap.add_argument('--from', dest='list', metavar='LIST',
                    help='read more FILE paths from LIST, one a line')
    ap.add_argument('--record', metavar='OUT', help='write the inputs and the table as JSON')
    ap.add_argument('--top', type=int, metavar='N', help='print the N most called entries only')
    ap.add_argument('-v', '--verbose', action='store_true', help='one line per file on stderr')
    a = ap.parse_args(argv)
    files = list(a.files)
    if a.list:
        with open(a.list) as f:
            files += [l.rstrip('\n') for l in f if l.strip()]
    if not files:
        ap.error('no FILE given')
    table, seen = tally(files, a.verbose)
    if not seen:
        sys.stderr.write('no listing in any file\n')
        return 2
    report(table, a.top)
    if a.record:
        record(a.record, files, table, seen)
    return 0


if __name__ == '__main__':
    sys.exit(main())
