"""z80/load.py and z80/run.py: the readers mirror the writers, and the
headless runner runs what they load.

The three readers are pinned against z80.asm's writers (a file written
then read gives the segments, entry and name back, and the period
ambiguities -- a 256-byte tape block, a 256-byte load record -- read as
the writers meant them).  The runner is pinned on its four endings:
returned, the 0A9AH result path, a ROM call with no ROM, and the
budget; on the screen it prints; and on its command line.
"""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from z80 import run                                             # noqa: E402
from z80.asm import assemble                                    # noqa: E402
from z80.load import LoadError, load_bin, load_cas, load_cmd, load_file   # noqa: E402

HI = '''\
        ORG   7D00H
VIDEO   EQU   3C00H
START   LD    HL,MSG
        LD    DE,VIDEO+5*64+28
        LD    BC,MSGEND-MSG
        LDIR
        CALL  0A7FH
        ADD   HL,HL
        JP    0A9AH
MSG     DEFM  'HELLO'
MSGEND  EQU   $
        END   START
'''


def asm(src, **kw):
    r = assemble(src, **kw)
    assert not r.errors, r.errors
    return r


class TestReaders(unittest.TestCase):
    def test_cmd_round_trip_with_a_256_byte_record(self):
        r = asm('  ORG 7000H\n  DEFS 253,1\n  ORG 8000H\n  DEFS 256,2\n  DEFS 3,3\n  END 7005H\n')
        # the writer keeps records to 253 bytes; make one of exactly 256 by hand
        data = bytes([0x05, 4]) + b'NAME'
        data += bytes([0x01, 0x00, 0x00, 0x80]) + bytes([2]) * 254   # length 0: 256 more
        data += bytes([0x02, 0x02, 0x05, 0x70])
        segs, entry, name = load_cmd(data)
        self.assertEqual((name, entry), ('NAME', 0x7005))
        self.assertEqual(segs, [(0x8000, bytes([2]) * 254)])
        segs, entry, name = load_cmd(r.to_cmd('sample'))
        self.assertEqual((name, entry), ('SAMPLE', 0x7005))
        self.assertEqual(b''.join(b for _, b in segs), bytes([1]) * 253 + bytes([2]) * 256 + bytes([3]) * 3)
        self.assertEqual([a for a, _ in segs], [0x7000, 0x8000, 0x80FD])

    def test_cmd_skips_headers_and_rejects_junk(self):
        data = bytes([0x07, 1, 0]) + bytes([0x1F, 2, 65, 66]) + bytes([0x01, 3, 0x00, 0x70, 0xAA]) + bytes([0x02, 2, 0, 0x70])
        self.assertEqual(load_cmd(data)[0], [(0x7000, b'\xaa')])
        with self.assertRaises(LoadError):
            load_cmd(bytes([0x09, 1, 0]))
        with self.assertRaises(LoadError):
            load_cmd(bytes([0x01, 10, 0, 0]))
        with self.assertRaises(LoadError):
            load_cmd(bytes([0x02, 2, 0, 0]))       # a transfer address and no block

    def test_cas_round_trip_checksums_and_a_256_byte_block(self):
        r = asm('  ORG 4300H\n  DEFS 256,7\n  DEFS 1,8\n  END 4302H\n')
        segs, entry, name = load_cas(r.to_cas('demon'))
        self.assertEqual((name, entry), ('DEMON', 0x4302))
        self.assertEqual(segs, [(0x4300, bytes([7]) * 256), (0x4400, b'\x08')])
        bad = bytearray(r.to_cas('demon'))
        bad[300] ^= 1
        with self.assertRaises(LoadError):
            load_cas(bytes(bad))
        with self.assertRaises(LoadError):
            load_cas(bytes(256) + b'\xa5\x00')
        with self.assertRaises(LoadError):
            load_cas(b'\x00' * 10)

    def test_a_file_that_ends_early_is_a_load_error(self):
        r = asm(HI)
        for whole, load in ((r.to_cas('hi'), load_cas), (r.to_cmd('hi'), load_cmd)):
            load(whole)
            for n in range(len(whole) - 1):
                if load is load_cas and n < 257:
                    continue                    # still inside the leader: "no sync byte"
                try:
                    load(whole[:n])
                except LoadError:
                    pass                        # never an IndexError
        with self.assertRaises(LoadError):
            load_cas(bytes(3) + b'\xa5\x55HELLO \x3c')
        with self.assertRaises(LoadError):
            load_cmd(b'\x01\x01\x00')

    def test_bin_and_load_file(self):
        self.assertEqual(load_bin(b'\x00\xc9', 0x7000), ([(0x7000, b'\x00\xc9')], None, ''))
        with self.assertRaises(LoadError):
            load_bin(b'\x00', None)
        r = asm(HI)
        with tempfile.TemporaryDirectory() as d:
            for ext, data in (('cmd', r.to_cmd('hi')), ('cas', r.to_cas('hi')), ('bin', r.to_bin()),
                              ('asm', HI.encode())):
                path = os.path.join(d, 'hi.' + ext)
                with open(path, 'wb') as f:
                    f.write(data)
                segs, entry, name = load_file(path, org=0x7D00 if ext == 'bin' else None)
                self.assertEqual(segs, r.segments, ext)
                self.assertEqual(entry, 0x7D00, ext)
                # --entry wins over the entry the file names, END's operand too
                segs, entry, name = load_file(path, org=0x7D00 if ext == 'bin' else None,
                                              entry=0x7D03)
                self.assertEqual(entry, 0x7D03, ext)
            with open(os.path.join(d, 'empty.asm'), 'w') as f:
                f.write('  ORG 7000H\n  END\n')
            with self.assertRaises(LoadError):
                load_file(os.path.join(d, 'empty.asm'))
            with open(os.path.join(d, 'bad.asm'), 'w') as f:
                f.write('  ORG 0\n  FOO BAR\n')
            with self.assertRaises(LoadError):
                load_file(os.path.join(d, 'bad.asm'))


class TestHeadless(unittest.TestCase):
    def run_src(self, src, arg=0, cycles=1_000_000):
        r = asm(src)
        h = run.Headless(cycles)
        h.load(r.segments)
        return h, h.run(r.entry, arg)

    def test_result_path_and_the_screen(self):
        h, (how, detail) = self.run_src(HI, arg=21)
        self.assertEqual(how, 'result')
        self.assertEqual(h.machine.cpu.hl, 42)
        self.assertTrue(h.wrote_video())
        rows = h.screen()
        self.assertEqual(len(rows), 16)
        self.assertEqual(rows[5][28:33], 'HELLO')
        self.assertEqual(rows[0].strip(), '')             # never written: blank, not FFH

    def test_returned_and_rom_and_budget(self):
        h, (how, _) = self.run_src('  ORG 8000H\n  LD HL,7\n  RET\n')
        self.assertEqual((how, h.machine.cpu.hl), ('ret', 7))
        h, (how, detail) = self.run_src('  ORG 8000H\n  CALL 0033H\n  RET\n')
        self.assertEqual(how, 'rom')
        self.assertIn('0033H', detail)
        h, (how, detail) = self.run_src('  ORG 8000H\nLOOP JP LOOP\n', cycles=50_000)
        self.assertEqual(how, 'budget')
        self.assertGreaterEqual(h.machine.cycles, 50_000)
        self.assertLess(h.machine.cycles, 50_000 + 9000)  # stopped at the next tick
        h, (how, detail) = self.run_src('  ORG 8000H\n  HALT\n')
        self.assertEqual(how, 'halt')

    def test_keyboard_reads_see_no_key(self):
        h, (how, _) = self.run_src('  ORG 8000H\n  LD A,(38FFH)\n  LD L,A\n  LD H,0\n  JP 0A9AH\n')
        self.assertEqual((how, h.machine.cpu.hl), ('result', 0))


class TestCommandLine(unittest.TestCase):
    def main(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = run.main(list(argv))
        return rc, out.getvalue()

    def test_source_file_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'hi.asm')
            with open(path, 'w') as f:
                f.write(HI)
            rc, out = self.main(path, '--arg', '21', '--regs', '--dump', '0x7D12,5')
            self.assertEqual(rc, 0, out)
            self.assertIn('reached 0A9AH', out)
            self.assertIn('HL = 42 (002AH)', out)
            self.assertIn('HELLO', out)
            self.assertIn('HL=002A', out)
            self.assertIn('7D12  48 45 4C 4C 4F', out)
            rc, out = self.main(path, '--no-screen', '--quiet')
            self.assertEqual((rc, out), (0, ''))
            loop = os.path.join(d, 'loop.asm')
            with open(loop, 'w') as f:
                f.write('  ORG 8000H\nLOOP JP LOOP\n')
            rc, out = self.main(loop, '--cycles', '1000')
            self.assertEqual(rc, 2)
            self.assertIn('budget', out)
            # a program loaded where the default stack is: the sentinel push
            # must not land on it (0FEFEH holds the RET this routine jumps to)
            high = os.path.join(d, 'high.asm')
            with open(high, 'w') as f:
                f.write('  ORG 0FEF0H\nSTART LD HL,1234H\n  JP TAIL\n  ORG 0FEFEH\n'
                        'TAIL JP 0A9AH\n  END START\n')
            rc, out = self.main(high)
            self.assertEqual(rc, 0, out)
            self.assertIn('HL = 4660', out)
            self.assertIn('stack at FEF0H', out)
            rc, out = self.main(high, '--sp', '0FF00H')
            self.assertEqual(rc, 1)
            rc, out = self.main(high, '--sp', '0F000H')
            self.assertEqual(rc, 0, out)
            with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
                self.main(path, '--entry', '10000H')        # was an IndexError in the core
            rc, out = self.main(os.path.join(d, 'missing.cmd'))
            self.assertEqual(rc, 1)


if __name__ == '__main__':
    unittest.main()
