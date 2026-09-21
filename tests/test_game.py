"""CATCH (tools/mkgame.py): it assembles, and it plays.

Two things are under test. The little assembler over the opcode table's
inverse index -- every instruction must come back out of the
disassembler as the instruction that went in -- and the game itself,
played headlessly in the core by a bot that tracks the ball, which is
the only way to know the catch, ramp and life paths run at all.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import mkgame                                                   # noqa: E402
from z80.coprocess import Machine                               # noqa: E402
from z80.disasm import decode                                   # noqa: E402

ORG = 32000


def play(code, labels, frames, org=ORG):
    """Run the routine with a bot on the keyboard; return the machine."""
    last, polls = {'line': ''}, {'n': 0}

    def send(s):
        last['line'] = s

    def recv():
        if not last['line'].startswith('K '):
            return 'OK'
        polls['n'] += 1
        if polls['n'] > frames:
            return 'K %d' % mkgame.K_SPACE
        ball, pad = m.ram[labels['BALLCOL']], m.ram[labels['PADCOL']]
        want = max(0, min(mkgame.ROWLEN - mkgame.PAD_WIDTH, ball - mkgame.PAD_WIDTH // 2))
        if pad + 1 < want:
            return 'K %d' % mkgame.K_RIGHT
        if pad > want + 1:
            return 'K %d' % mkgame.K_LEFT
        return 'K 0'

    m = Machine(send, recv, 0.0)
    for i, b in enumerate(code):
        m.ram[org + i] = b
        m.known[org + i] = 1
    m.run(org, 0, 0xFF00)
    m.polls = polls['n']
    return m


class TestAssembles(unittest.TestCase):
    def test_every_instruction_decodes_back(self):
        """The bytes the inverse index emitted are the instructions the
        disassembler reads: a wrong encoding here is a wrong game."""
        asm, code, _, _ = mkgame.build(ORG, 30)
        end = asm.labels['HUDTEXT'] - ORG           # code stops where the data starts
        pos = 0
        seen = 0
        while pos < end:
            ins = decode(code, pos, base=ORG)
            self.assertFalse(ins.invalid, 'invalid at %04XH' % (ORG + pos))
            self.assertFalse(ins.truncated, 'truncated at %04XH' % (ORG + pos))
            pos += ins.length
            seen += 1
        self.assertEqual(pos, end, 'the last instruction overruns the data')
        self.assertGreater(seen, 80)

    def test_length_and_checksum_are_stable(self):
        """The listing's DATA checksum is what the loader verifies."""
        _, a, _, _ = mkgame.build(ORG, 30)
        _, b, _, _ = mkgame.build(ORG, 30)
        self.assertEqual(a, b)
        self.assertEqual(sum(a) & 0xFFFFFF, sum(b) & 0xFFFFFF)

    def test_relative_jump_out_of_range_is_refused(self):
        """A silent wrap here would be a wild jump in a listing."""
        asm = mkgame.Asm(0x7000)
        asm.op('JR', ('NZ', 'd'), 'FAR')
        asm.space(200)
        asm.label('FAR')
        self.assertRaises(ValueError, asm.assemble)

    def test_unknown_instruction_is_refused(self):
        asm = mkgame.Asm(0x7000)
        self.assertRaises(KeyError, asm.op, 'LD', ('A', 'Q'))


class TestPlays(unittest.TestCase):
    def test_bot_scores_and_returns_through_the_rom_trap(self):
        asm, code, _, _ = mkgame.build(ORG, 30)
        m = play(code, asm.labels, 200)
        self.assertEqual(m.result, 1, 'the score must come back through 0A9AH')
        self.assertGreaterEqual(m.cpu.hl, 1, 'a ball-tracking bot catches something')
        self.assertGreaterEqual(m.ram[asm.labels['LIVES']], 1)

    def test_the_screen_holds_the_hud_the_paddle_and_the_ball(self):
        asm, code, _, _ = mkgame.build(ORG, 30)
        m = play(code, asm.labels, 120)
        row0 = bytes(m.ram[mkgame.VIDEO:mkgame.VIDEO + len(mkgame.HUD)])
        self.assertEqual(row0[:5], b'CATCH')
        bottom = m.ram[mkgame.PADROW:mkgame.PADROW + mkgame.ROWLEN]
        self.assertEqual(bottom.count(mkgame.HALF_LOW), mkgame.PAD_WIDTH)
        body = m.ram[mkgame.VIDEO + mkgame.ROWLEN:mkgame.PADROW]
        self.assertEqual(body.count(mkgame.SOLID), 1, 'exactly one ball in play')

    def test_frame_costs_what_the_cycle_column_says(self):
        """The delay is computed from the table's cycles; if the table's
        costs and the core's execution disagreed, this would drift."""
        asm, code, _, _ = mkgame.build(ORG, 30)
        m = play(code, asm.labels, 100)
        want = mkgame.MHZ * 1e6 / 30
        self.assertAlmostEqual(m.cycles / m.polls / want, 1.0, delta=0.02)

    def test_scan_knob_multiplies_the_keyboard_reads(self):
        """--scan is the stress setting: N extra matrix reads a frame."""
        asm, code, _, _ = mkgame.build(ORG, 30, scan=3)
        m = play(code, asm.labels, 240)
        # 240 polls of the bot's own row plus three more a frame
        self.assertGreaterEqual(m.polls, 240)
        frames = m.polls / 4.0
        self.assertAlmostEqual(m.cycles / frames / (mkgame.MHZ * 1e6 / 30), 1.0, delta=0.05)


class TestValuesThatDoNotFitAreRefused(unittest.TestCase):
    """A masked immediate is a game that misbehaves and says it does not.

    Every immediate was written with `& 0xFF` or `& 0xFFFF`, so a value
    the generator computed too large was quietly cut -- `--fps 1` wants a
    delay of 68218 turns and emitted LD DE,2682, a 25x faster game, while
    the statistics it printed went on quoting 68218 (the 2026-09-19
    audit, L-66).
    """

    def test_a_frame_rate_the_loop_cannot_reach_is_refused(self):
        with self.assertRaises(ValueError) as e:
            mkgame.build(32000, 1)
        self.assertIn('65535', str(e.exception))
        self.assertIn('68218', str(e.exception))

    def test_the_message_says_what_the_loop_can_reach(self):
        with self.assertRaises(ValueError) as e:
            mkgame.delay_count(1, overhead=400)
        self.assertIn('slowest', str(e.exception))

    def test_a_reachable_frame_rate_still_builds(self):
        for fps in (2, 10, 30, 60):
            asm, code, delay, per_turn = mkgame.build(32000, fps)
            self.assertTrue(0 < delay <= 0xFFFF, fps)
            self.assertTrue(code)

    def test_a_byte_operand_that_does_not_fit_is_refused(self):
        a = mkgame.Asm(32000)
        with self.assertRaises(ValueError) as e:
            a.op('LD', ('A', 'n'), 300)
        self.assertIn('byte', str(e.exception))

    def test_a_word_operand_that_does_not_fit_is_refused(self):
        a = mkgame.Asm(32000)
        with self.assertRaises(ValueError) as e:
            a.op('LD', ('DE', 'nn'), 70000)
        self.assertIn('word', str(e.exception))

    def test_the_shipped_demo_is_unchanged(self):
        """The fix must not move demo/catch.bas."""
        asm, code, delay, fps_turn = mkgame.build(32000, 30)
        text = mkgame.listing(code, 32000, delay, 30)
        with open(os.path.join(ROOT, 'demo', 'catch.bas')) as f:
            self.assertEqual(text, f.read())


if __name__ == '__main__':
    unittest.main()
