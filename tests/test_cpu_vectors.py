"""The single-step vectors EXECUTED against z80.cpu -- the semantic check.

tests/test_vectors.py pins the SHAPE of the suite (which encodings exist)
and runs with no data on disk.  This file needs the data: it runs the
fetched cases through `Z80.step()` and compares every register, every
flag bit, MEMPTR, R, IFF1/2, IM, the EI delay, the Q state, every RAM
cell the case names, every port access, and the T-state count (which is
what finally validates the table's cycle column -- DD-9).

It skips cleanly when the vectors are not fetched
(`python3 tools/fetch_vectors.py --all`).

    python3 -m unittest tests.test_cpu_vectors          # sample: 40 cases per file
    Z80_VECTORS=all python3 -m unittest tests.test_cpu_vectors   # all 1.6M cases
    Z80_VECTORS=all Z80_VECTORS_FILES='ed b2,cb' ...     # only those files/pages

A failure prints the case name (upstream's "<opcode> <index>"), so a
regression is reproducible by name against the pinned SHA.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from z80.cpu import Z80                                       # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V1 = os.path.join(ROOT, 'tests', 'vectors', 'v1')

REGS8 = ('a', 'b', 'c', 'd', 'e', 'f', 'h', 'l', 'i', 'r')
REGS16 = ('pc', 'sp', 'wz', 'ix', 'iy')
MISC = ('iff1', 'iff2', 'im', 'ei', 'q')


def load_state(cpu, st):
    for k in REGS8 + REGS16 + MISC:
        setattr(cpu, k, st[k])
    cpu.a2, cpu.f2 = st['af_'] >> 8, st['af_'] & 0xFF
    cpu.b2, cpu.c2 = st['bc_'] >> 8, st['bc_'] & 0xFF
    cpu.d2, cpu.e2 = st['de_'] >> 8, st['de_'] & 0xFF
    cpu.h2, cpu.l2 = st['hl_'] >> 8, st['hl_'] & 0xFF
    cpu.halted = False


def run_case(case, mem, cpu, ports):
    ini, fin = case['initial'], case['final']
    for a, v in ini['ram']:
        mem[a] = v
    ports.clear()
    ports.extend(case.get('ports', []))
    load_state(cpu, ini)
    cycles = cpu.step()
    bad = []
    for k in REGS8 + REGS16 + MISC:
        if getattr(cpu, k) != fin[k]:
            bad.append('%s=%d want %d' % (k, getattr(cpu, k), fin[k]))
    for name, hi, lo in (('af_', cpu.a2, cpu.f2), ('bc_', cpu.b2, cpu.c2),
                         ('de_', cpu.d2, cpu.e2), ('hl_', cpu.h2, cpu.l2)):
        if (hi << 8 | lo) != fin[name]:
            bad.append('%s=%04X want %04X' % (name, hi << 8 | lo, fin[name]))
    for a, v in fin['ram']:
        if mem[a] != v:
            bad.append('ram[%d]=%d want %d' % (a, mem[a], v))
    if cycles != len(case['cycles']):
        bad.append('cycles=%d want %d' % (cycles, len(case['cycles'])))
    if ports:
        bad.append('port accesses not consumed: %r' % ports)
    for a, _ in ini['ram']:
        mem[a] = 0
    for a, _ in fin['ram']:
        mem[a] = 0
    return bad


class Harness:
    """A 64K RAM plus a scripted port list, shared across cases."""

    def __init__(self):
        self.mem = bytearray(65536)
        self.ports = []
        self.bad_ports = []
        self.cpu = Z80(self.read, self.write, self.port_in, self.port_out)

    def read(self, a):
        return self.mem[a]

    def write(self, a, v):
        self.mem[a] = v

    def port_in(self, port):
        if self.ports and self.ports[0][2] == 'r' and self.ports[0][0] == port:
            return self.ports.pop(0)[1]
        self.bad_ports.append(('in', port))
        return 0

    def port_out(self, port, v):
        if self.ports and self.ports[0][2] == 'w' and self.ports[0][0] == port \
                and self.ports[0][1] == v:
            self.ports.pop(0)
            return
        self.bad_ports.append(('out', port, v))


def vector_files():
    if not os.path.isdir(V1):
        return []
    names = sorted(os.listdir(V1))
    sel = os.environ.get('Z80_VECTORS_FILES')
    if sel:
        wanted = [w.strip().lower() for w in sel.split(',')]
        names = [n for n in names
                 if any(n[:-5].lower() == w or n.lower().startswith(w + ' ')
                        for w in wanted)]
    return names


@unittest.skipUnless(os.path.isdir(V1), 'vectors not fetched (tools/fetch_vectors.py --all)')
class TestVectorsExecute(unittest.TestCase):

    def test_every_file(self):
        limit = None if os.environ.get('Z80_VECTORS') == 'all' else 40
        h = Harness()
        failures = []
        total = 0
        for name in vector_files():
            with open(os.path.join(V1, name)) as f:
                cases = json.load(f)
            for case in cases[:limit]:
                total += 1
                bad = run_case(case, h.mem, h.cpu, h.ports)
                if h.bad_ports:
                    bad.append('unexpected port access %r' % h.bad_ports)
                    h.bad_ports.clear()
                if bad:
                    failures.append('%s: %s' % (case['name'], '; '.join(bad)))
                    if len(failures) >= 200:
                        break
            if len(failures) >= 200:
                break
        self.assertFalse(failures, '%d of %d cases failed; first:\n%s'
                         % (len(failures), total, '\n'.join(failures[:40])))


if __name__ == '__main__':
    unittest.main()
