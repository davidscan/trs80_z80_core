"""The classifier's Stage 1 verdict on synthetic routines.

stage1_ok says the CPU plus the two USR traps (0A7FH, 0A9AH) run the
routine.  Every way into the ROM refutes it, not only CALL: a tail JP
0033H prints and returns to BASIC through the ROM, and a JP (HL) goes
where no static reading can say (the 2026-09-19 audit, L-61).  Every
routine here is written for the test; nothing is corpus material.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phasea.classify import classify                          # noqa: E402

BASE = 0x7000


def c(*code):
    return classify(bytes(code), BASE, [0])


class TestStage1(unittest.TestCase):

    def test_the_usr_traps_alone_are_stage1(self):
        r = c(0xCD, 0x7F, 0x0A, 0x23, 0xC3, 0x9A, 0x0A)   # CALL 0A7FH / INC HL / JP 0A9AH
        self.assertTrue(r.stage1_ok)
        self.assertEqual(r.stage2_traps, [])

    def test_a_jump_inside_the_routine_is_not_the_rom(self):
        r = c(0x3E, 0x01, 0x3D, 0x20, 0xFD, 0xC9)   # LD A,1 / DEC A / JR NZ,-3 / RET
        self.assertTrue(r.stage1_ok)

    def test_a_symbolic_base_keeps_its_relative_jumps(self):
        # a string-packed routine has no fixed base and is decoded at 0:
        # its JR and DJNZ land at small addresses that are its own bytes
        r = classify(bytes((0x06, 0x10, 0x10, 0xFE, 0x18, 0x00, 0xC9)), None, [0])
        self.assertTrue(r.stage1_ok)                # LD B,16 / DJNZ $ / JR $+2 / RET
        r = classify(bytes((0x00, 0xC3, 0x33, 0x00)), None, [0])
        self.assertEqual(r.stage2_traps, [0x0033])  # an absolute JP is the ROM
        r = classify(bytes((0x00,) * 20 + (0xC3, 0x10, 0x00)), None, [0])
        self.assertEqual(r.stage2_traps, [0x0010])  # even one below its length

    def test_a_tail_jump_into_the_rom_needs_stage2(self):
        r = c(0x3E, 0x41, 0xC3, 0x33, 0x00)         # LD A,'A' / JP 0033H
        self.assertFalse(r.stage1_ok)
        self.assertEqual(r.stage2_traps, [0x0033])
        self.assertIn('rom-calling', r.buckets_all)

    def test_a_conditional_jump_into_the_rom_needs_stage2(self):
        r = c(0xB7, 0xCA, 0x49, 0x00, 0xC9)         # OR A / JP Z,0049H / RET
        self.assertEqual(r.stage2_traps, [0x0049])

    def test_a_call_to_3033h_is_tallied(self):
        # 3000H-37FFH is not RAM on a Model I either; ROM_NAMES has 3033H
        # and ROM_HI (2FFFH) made it untallyable
        r = c(0xCD, 0x33, 0x30, 0xC9)
        self.assertFalse(r.stage1_ok)
        self.assertEqual(r.stage2_traps, [0x3033])
        self.assertEqual(r.rom_calls, [(0x3033, 'DOS entry')])

    def test_an_indirect_jump_is_not_stage1(self):
        for code in ((0x21, 0x33, 0x00, 0xE9),                 # LD HL,0033H / JP (HL)
                     (0xDD, 0x21, 0x33, 0x00, 0xDD, 0xE9)):    # LD IX,0033H / JP (IX)
            r = c(*code)
            self.assertFalse(r.stage1_ok, code)
            self.assertIn('indirect-jump', r.evidence['direct'])
            self.assertIn('indirect', r.reason)


if __name__ == '__main__':
    unittest.main()
