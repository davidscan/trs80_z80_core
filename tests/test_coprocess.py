"""The coprocess half of PROTOCOL.md, driven without the interpreter.

Two layers.  `Machine` tests script the protocol lines a call would
exchange (send/recv are plain lists) and assert on what the core says
back: the sentinel ending a call, the three HLE traps, `ERR rom` and
`ERR halt`, the write-set's last-write-wins coalescing, video streamed as
`V` and left out of the write-set, the keyboard callback, BREAK on a
tick, and pacing left alone at mhz=0.  The transport test runs core.py
as a real subprocess through pipes, including `NEED full`, `BYE` and
exit on EOF.  trs80basic's `sh programs/tests/z80.sh` remains the
acceptance bar (DD-17); these pin the mechanism so a regression names
itself here first.
"""

import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from z80.coprocess import Machine, Fixture, SENTINEL, TICK_TSTATES   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, 'core.py')


class Scripted:
    """send() collects lines; recv() pops scripted replies."""

    def __init__(self, replies=()):
        self.out = []
        self.replies = list(replies)

    def send(self, s):
        self.out.append(s)

    def recv(self):
        return self.replies.pop(0) if self.replies else 'OK'

    def ret(self):
        rets = [l for l in self.out if l.startswith('RET ')]
        assert len(rets) == 1, self.out
        return dict(kv.split('=') for kv in rets[0].split()[1:])

    def writes(self):
        return [l[2:] for l in self.out if l.startswith('W ')]

    def video(self):
        return [l[2:] for l in self.out if l.startswith('V ')]


def machine(code, at=0x7000, replies=()):
    sc = Scripted(replies)
    m = Machine(sc.send, sc.recv)
    m.ram[at:at + len(code)] = code
    return m, sc


class TestCalls(unittest.TestCase):

    def test_plain_ret_ends_at_sentinel_with_result_0(self):
        m, sc = machine(bytes.fromhex('C9'))
        m.run(0x7000, 5, 0xF000)
        r = sc.ret()
        self.assertEqual((r['result'], r['break']), ('0', '0'))
        # the two sentinel bytes are the whole write-set
        self.assertEqual(sc.writes(), ['%d:%d,%d' % (0xEFFE, SENTINEL & 0xFF, SENTINEL >> 8)])
        self.assertEqual(int(r['cycles']), 10)

    def test_0a7f_then_0a9a_returns_a_value(self):
        # CALL 0A7FH / ADD HL,HL / JP 0A9AH
        m, sc = machine(bytes.fromhex('CD7F0A' '29' 'C39A0A'))
        m.run(0x7000, -21, 0xF000)
        r = sc.ret()
        self.assertEqual(r['result'], '1')
        self.assertEqual(int(r['hl']), (-42) & 0xFFFF)

    def test_0a7f_truncates_like_the_stub(self):
        m, sc = machine(bytes.fromhex('CD7F0A' 'C39A0A'))
        m.run(0x7000, int(float('1.9')), 0xF000)
        self.assertEqual(int(sc.ret()['hl']), 1)

    def test_0a9a_by_call_also_ends_the_frame(self):
        m, sc = machine(bytes.fromhex('210300' 'CD9A0A' '76'))   # never reaches HALT
        m.run(0x7000, 0, 0xF000)
        self.assertEqual(sc.ret()['hl'], '3')

    def test_cls_trap_paints_and_homes(self):
        # CALL 01C9H / RET, with a byte on screen and the cursor elsewhere
        m, sc = machine(bytes.fromhex('CDC901' 'C9'))
        m.ram[0x3C05] = 0x41
        m.run(0x7000, 0, 0xF000)
        self.assertEqual(sc.ret()['result'], '0')
        self.assertEqual(sc.video(), ['15360:' + ','.join(['32'] * 1024)])
        ws = sc.writes()
        self.assertIn('16416:0,60', ws)            # 4020H/4021H <- 3C00H
        self.assertTrue(all(b == 0x20 for b in m.ram[0x3C00:0x4000]))

    def test_err_rom_names_the_address(self):
        m, sc = machine(bytes.fromhex('CD0000'))
        with self.assertRaises(Exception) as cm:
            m.run(0x7000, 0, 0xF000)
        self.assertEqual((cm.exception.code, cm.exception.text),
                         ('rom', 'called 0000H, no ROM here'))

    def test_rst_is_rom_too(self):
        m, sc = machine(bytes.fromhex('FF'))
        with self.assertRaises(Exception) as cm:
            m.run(0x7000, 0, 0xF000)
        self.assertEqual(cm.exception.text, 'called 0038H, no ROM here')

    def test_halt_is_an_error(self):
        m, sc = machine(bytes.fromhex('76'))
        with self.assertRaises(Exception) as cm:
            m.run(0x7000, 0, 0xF000)
        self.assertEqual(cm.exception.code, 'halt')

    def test_write_set_last_write_wins_and_coalesces(self):
        # LD A,1 / LD (7530H),A / LD A,2 / LD (7530H),A / LD (7531H),A / RET
        m, sc = machine(bytes.fromhex('3E01' '323075' '3E02' '323075' '323175' 'C9'))
        m.run(0x7000, 0, 0xF000)
        self.assertEqual(sc.writes(), ['30000:2,2', '61438:253,47'])
        self.assertEqual(sc.ret()['writes'], '2')

    def test_video_is_streamed_not_written(self):
        # LD A,41H / LD (3C00H),A / LD (7530H),A / RET
        m, sc = machine(bytes.fromhex('3E41' '32003C' '323075' 'C9'))
        m.run(0x7000, 0, 0xF000)
        self.assertEqual(sc.video(), ['15360:65'])
        self.assertEqual(sc.writes(), ['30000:65', '61438:253,47'])
        v_index = sc.out.index('V 15360:65')
        r_index = [i for i, l in enumerate(sc.out) if l.startswith('RET')][0]
        self.assertLess(v_index, r_index)

    def test_keyboard_callback(self):
        # LD A,(38FFH) / LD L,A / LD H,0 / JP 0A9AH
        m, sc = machine(bytes.fromhex('3AFF38' '6F' '2600' 'C39A0A'), replies=['K 3'])
        m.run(0x7000, 0, 0xF000)
        self.assertIn('K 255', sc.out)
        self.assertEqual(sc.ret()['hl'], '3')

    def test_unwritten_memory_reads_255(self):
        # LD A,(0C350H) / LD L,A / LD H,0 / JP 0A9AH
        m, sc = machine(bytes.fromhex('3A50C3' '6F' '2600' 'C39A0A'))
        m.run(0x7000, 0, 0xF000)
        self.assertEqual(sc.ret()['hl'], '255')

    def test_ticks_and_break(self):
        # a loop of 65536 x 26 T-states, BREAK on the third tick
        m, sc = machine(bytes.fromhex('010000' '0B' '78' 'B1' '20FB' 'C9'),
                        replies=['OK', 'OK', 'BREAK'])
        m.run(0x7000, 0, 0xF000)
        ticks = [l for l in sc.out if l.startswith('T ')]
        self.assertEqual(len(ticks), 3)
        self.assertGreaterEqual(int(ticks[0].split()[1]), TICK_TSTATES)
        self.assertEqual(sc.ret()['break'], '1')

    def test_port_ff_reads_127_and_out_is_discarded(self):
        # IN A,(FFH) / OUT (FFH),A / LD L,A / LD H,0 / JP 0A9AH
        m, sc = machine(bytes.fromhex('DBFF' 'D3FF' '6F' '2600' 'C39A0A'))
        m.run(0x7000, 0, 0xF000)
        self.assertEqual(sc.ret()['hl'], '127')

    def test_stack_lands_below_sp_in_the_write_set(self):
        # the fixture's 7009 routine
        m, sc = machine(bytes.fromhex('D1' '213412' 'E5' 'E1' 'EB' 'E9'))
        m.run(0x7000, 0, 0xF000)
        self.assertEqual(sc.writes(), ['61438:52,18'])
        self.assertEqual(sc.ret()['result'], '0')


class TestFixtureLayout(unittest.TestCase):

    def test_routines_do_not_overlap_and_map_every_entry(self):
        fx = Fixture()
        self.assertEqual(sorted(fx.entry), sorted([0x7000, 0x7001, 0x7002, 0x7003,
                                                   0x7005, 0x7006, 0x7007, 0x7009,
                                                   0x700A, 0x7777]))
        addrs = sorted(fx.image)
        self.assertEqual(addrs, list(range(addrs[0], addrs[0] + len(addrs))))


class TestTransport(unittest.TestCase):

    def talk(self, lines, args=()):
        p = subprocess.Popen([sys.executable, CORE] + list(args),
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
        out, err = p.communicate('\n'.join(lines) + '\n', timeout=30)
        return out.splitlines(), err, p.returncode

    def test_hello_call_bye(self):
        out, err, rc = self.talk([
            'HELLO proto=1 mhz=0 ramtop=65535',
            'CALL gen=1 full=1 slot=0 entry=28672 arg=21 sp=61440 himem=65535 ramtop=65535 runs=1',
            'M 28672:205,127,10,41,195,154,10',       # CALL 0A7FH / ADD HL,HL / JP 0A9AH
            'GO',
            'BYE'])
        self.assertEqual(rc, 0)
        self.assertEqual(err, '')
        self.assertTrue(out[0].startswith('Z80 proto=1 name=trs80_z80_core pid='), out)
        self.assertTrue(out[1].startswith('RET hl=42 result=1 cycles='), out)
        self.assertTrue(out[1].endswith(' break=0 writes=1'), out)
        self.assertEqual(out[2], 'W 61436:3,112,253,47')   # CALL's return address, then the sentinel

    def test_need_full_when_a_generation_is_missing(self):
        out, err, rc = self.talk([
            'HELLO proto=1 mhz=0 ramtop=65535',
            'CALL gen=2 full=0 slot=0 entry=28672 arg=0 sp=61440 himem=65535 ramtop=65535 runs=0',
            'GO',
            'CALL gen=1 full=1 slot=0 entry=28672 arg=0 sp=61440 himem=65535 ramtop=65535 runs=1',
            'M 28672:201',
            'GO',
            'BYE'])
        self.assertEqual(out[1], 'NEED full')
        self.assertTrue(out[2].startswith('RET hl=0 result=0'), out)

    def test_err_then_next_call_proceeds(self):
        out, err, rc = self.talk([
            'HELLO proto=1 mhz=0 ramtop=65535',
            'CALL gen=1 full=1 slot=0 entry=28672 arg=0 sp=61440 himem=65535 ramtop=65535 runs=1',
            'M 28672:205,0,0',
            'GO',
            'CALL gen=2 full=0 slot=0 entry=28672 arg=0 sp=61440 himem=65535 ramtop=65535 runs=1',
            'M 28672:201',
            'GO',
            'BYE'])
        self.assertEqual(out[1], 'ERR rom called 0000H, no ROM here')
        self.assertTrue(out[2].startswith('RET '), out)

    def test_exit_on_eof(self):
        out, err, rc = self.talk(['HELLO proto=1 mhz=0 ramtop=65535'])
        self.assertEqual(rc, 0)

    def test_protocol_mismatch_answers_and_leaves(self):
        out, err, rc = self.talk(['HELLO proto=2 mhz=0 ramtop=65535', 'BYE'])
        self.assertTrue(out[0].startswith('Z80 proto=1'), out)
        self.assertEqual(rc, 0)


if __name__ == '__main__':
    unittest.main()
