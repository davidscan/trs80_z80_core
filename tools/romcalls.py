#!/usr/bin/env python3
"""tools/romcalls.py -- which ROM entry points do a library's listings call?

    python3 tools/romcalls.py FILE... [--top N] [-v]

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
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import hexcheck                                                 # noqa: E402
from z80 import coprocess                                       # noqa: E402
from z80 import disasm                                          # noqa: E402

ROM_TOP = coprocess.ROM_TOP

# The names the Level II manual and the period ROM guides give these entry
# points.  Documentation names only: no ROM bytes, no disassembly.
NAMES = {
    0x0000: 'RESET', 0x0008: 'RST 08H syntax check', 0x0010: 'RST 10H next char',
    0x0018: 'RST 18H compare HL,DE', 0x0020: 'RST 20H test type',
    0x0028: 'RST 28H DOS hook', 0x0030: 'RST 30H DOS hook', 0x0038: 'RST 38H interrupt',
    0x002B: 'KBCHAR keyboard scan', 0x0033: 'DSP display char', 0x003B: 'PRT print char',
    0x0040: 'KBLINE keyboard line', 0x0049: 'KBWAIT wait for key', 0x0060: 'DELAY',
    0x0066: 'NMI', 0x01C9: 'CLS', 0x01D3: 'RANDOM', 0x01F8: 'CSOFF cassette off',
    0x0212: 'CSON cassette on', 0x0235: 'CSIN read byte', 0x0264: 'CSOUT write byte',
    0x0287: 'CSHWR write leader', 0x0296: 'CSHIN read leader',
    0x032A: 'CHROUT char to device (DE)', 0x0A7F: 'GETARG USR argument to HL',
    0x0A9A: 'RETINT return integer', 0x1A19: 'READY', 0x28A7: 'VDLINE display string (HL)',
}

DATA_OPS = {'DEFB', 'DB', 'DEFW', 'DW', 'DEFM', 'DM', 'DEFS', 'DS'}


def rom_calls(recs):
    """(target, mnemonic, one_column, rec) for every ROM-range branch in
    the settled lines of one block."""
    out = []
    # A listing assembled at a low address (relocatable code, ORG 0) has
    # its own branches in ROM range: a target inside the block is a call to
    # itself, not to the ROM.
    here = [r.addr for r in recs if r.addr is not None and r.bytes]
    lo, hi = (min(here), max(here)) if here else (0, -1)
    for r in recs:
        if not r.bytes or r.addr is None or r.status not in hexcheck.CONFIDENT + ('hexonly',):
            continue
        if (r.fop or r.op) in DATA_OPS:
            continue
        for ins in disasm.disassemble(r.bytes, r.addr):
            if ins.invalid or ins.op is None or ins.target is None:
                continue
            if ins.op.kind in ('jump', 'call') and ins.target < ROM_TOP \
                    and not lo <= ins.target <= hi:
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


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog='python3 tools/romcalls.py',
        description='Tally the ROM entry points the listings in these files call.')
    ap.add_argument('files', nargs='+', metavar='FILE', help='text holding scanned listings')
    ap.add_argument('--top', type=int, metavar='N', help='print the N most called entries only')
    ap.add_argument('-v', '--verbose', action='store_true', help='one line per file on stderr')
    a = ap.parse_args(argv)
    table, seen = tally(a.files, a.verbose)
    if not seen:
        sys.stderr.write('no listing in any file\n')
        return 2
    report(table, a.top)
    return 0


if __name__ == '__main__':
    sys.exit(main())
