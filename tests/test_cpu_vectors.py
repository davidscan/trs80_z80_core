"""The single-step vectors EXECUTED against z80.cpu -- the semantic check.

tests/test_vectors.py pins the SHAPE of the suite (which encodings exist)
and runs with no data on disk.  This file needs the data: it runs the
fetched cases through `Z80.step()` and compares every register, every
flag bit, MEMPTR, R, IFF1/2, IM, the EI delay, the Q state, every RAM
cell the case names, every port access, and the T-state count (which is
what finally validates the table's cycle column -- DD-9).

It skips cleanly when the vectors are not fetched
(`python3 tools/fetch_vectors.py --all`), unless Z80_VECTORS_REQUIRE=1,
which makes absence a failure and asks for all 1604 files.  When v1/ is
there, it is first checked against the pin (tools/vectors.lock and the
cached .manifest.json): a file that does not hash to its blob, a file the
pin does not name, or no case run at all is a failure, never a pass (the
2026-09-30 audit, ZM-10: an empty v1/ passed in 0.002 s).

    python3 -m unittest tests.test_cpu_vectors          # sample: 40 cases per file
    Z80_VECTORS=all python3 -m unittest tests.test_cpu_vectors   # all 1.6M cases
    Z80_VECTORS=all Z80_VECTORS_FILES='ed b2,cb' ...     # only those files/pages
    Z80_VECTORS_REQUIRE=1 python3 -m unittest tests.test_cpu_vectors  # the full set, or fail

A failure prints the case name (upstream's "<opcode> <index>"), so a
regression is reproducible by name against the pinned SHA.
"""

import json
import os
import shutil
import sys
import tempfile
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


REQUIRE = os.environ.get('Z80_VECTORS_REQUIRE') == '1'


def pin_problems(require=REQUIRE, dest=None):
    """What is wrong with the local vectors against the pin: a list of
    reasons, empty when they may be run.  A partial fetch (--pages) is
    run as it stands unless require is set."""
    from tools import fetch_vectors as fv
    lock = fv.load_lock()
    saved = fv.MANIFEST
    if dest is not None:
        fv.MANIFEST = os.path.join(dest, '.manifest.json')
    try:
        files = fv.cached_files(lock)
    finally:
        fv.MANIFEST = saved
    if files is None:
        return ['no file list for the pinned SHA in tests/vectors/.manifest.json: '
                'the files on disk are not checked against the pin (fetch_vectors.py --all)']
    good, bad, missing, strays = fv.local_state(files, dest)
    out = []
    if bad:
        out.append('%d file(s) do not hash to the pin, e.g. %s' % (len(bad), bad[0]))
    if strays:
        out.append('%d file(s) in v1/ the pin does not name, e.g. %s' % (len(strays), strays[0]))
    if not good:
        out.append('no fetched file matches the pin')
    if require and missing:
        out.append('Z80_VECTORS_REQUIRE=1 and %d of %d pinned files are missing'
                   % (len(missing), len(files)))
    return out


class TestVectorsArePresentWhenRequired(unittest.TestCase):

    def test_require_makes_absence_a_failure(self):
        if not REQUIRE:
            self.skipTest('Z80_VECTORS_REQUIRE is not 1')
        self.assertTrue(os.path.isdir(V1), 'Z80_VECTORS_REQUIRE=1 and no tests/vectors/v1')


MANIFEST = os.path.join(ROOT, 'tests', 'vectors', '.manifest.json')


@unittest.skipUnless(os.path.exists(MANIFEST), 'no cached manifest (tools/fetch_vectors.py --all)')
class TestThePinCheck(unittest.TestCase):
    """The check itself, on a scratch copy of the manifest and stand-in
    files: an empty v1/, a stray, a corrupted file, a partial fetch."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d)
        shutil.copy(MANIFEST, self.d)
        os.makedirs(os.path.join(self.d, 'v1'))

    def put(self, name, src=None):
        dst = os.path.join(self.d, 'v1', name)
        if src:
            shutil.copy(src, dst)
        else:
            with open(dst, 'w') as f:
                f.write('[]')

    def test_an_empty_directory_is_not_a_pass(self):
        self.assertIn('no fetched file matches the pin', ' '.join(pin_problems(False, self.d)))

    def test_one_good_file_is_a_partial_fetch(self):
        self.put('00.json', os.path.join(V1, '00.json'))
        self.assertEqual(pin_problems(False, self.d), [])
        self.assertIn('1603 of 1604', ' '.join(pin_problems(True, self.d)))

    def test_a_stray_and_a_corrupted_file_are_named(self):
        self.put('00.json', os.path.join(V1, '00.json'))
        self.put('01.json')
        self.put('zz.json')
        got = ' '.join(pin_problems(False, self.d))
        self.assertIn('do not hash to the pin, e.g. v1/01.json', got)
        self.assertIn('the pin does not name, e.g. zz.json', got)

    def test_no_manifest_is_not_checked_and_says_so(self):
        os.remove(os.path.join(self.d, '.manifest.json'))
        self.assertIn('not checked against the pin', ' '.join(pin_problems(False, self.d)))


@unittest.skipUnless(os.path.isdir(V1), 'vectors not fetched (tools/fetch_vectors.py --all)')
class TestVectorsExecute(unittest.TestCase):

    def test_every_file(self):
        problems = pin_problems()
        self.assertFalse(problems, 'the local vectors are not the pinned set:\n  '
                         + '\n  '.join(problems))
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
        self.assertGreater(total, 0, 'no vector case was run')
        self.assertFalse(failures, '%d of %d cases failed; first:\n%s'
                         % (len(failures), total, '\n'.join(failures[:40])))


if __name__ == '__main__':
    unittest.main()
