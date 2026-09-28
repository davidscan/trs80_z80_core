"""A hand-written flag and cycle fixture that ALWAYS runs -- CI's CPU net.

The single-step vector suites (tests/test_cpu_vectors.py) are fetched,
never committed, so CI has no semantic check of the CPU at all: a
half-carry mutant passed the vector-less suite (audit 2026-09-26 ZM-7).
This file is that check.  Every case here is this project's own,
hand-written against the Zilog manual's flag rules (and, for the
undocumented X/Y bits, the NMOS behavior the fetched vectors pin), so it
can be committed; it is a pin, not a re-derivation -- the fetched
vectors remain the exhaustive oracle.

Each case is one instruction stepped once from address 0:

    (name, code hex, inputs, expected, t_states)

Inputs and expected name Z80 attributes (`a`, `f`, `b` .. `ix`, `wz`),
plus `mem` {addr: value} and, in inputs, `ports` [(port, value, 'r')].
A flag value may be written as a string of set bits from "SZYHXPNC"
(bit 7 to bit 0; "" = no flags) -- Y and X are the undocumented bits 5
and 3.  Only the named attributes are compared, plus the T-state count.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from z80.cpu import Z80                                       # noqa: E402

FLAGBITS = {'S': 0x80, 'Z': 0x40, 'Y': 0x20, 'H': 0x10,
            'X': 0x08, 'P': 0x04, 'N': 0x02, 'C': 0x01}


def flags(v):
    if isinstance(v, str):
        return sum(FLAGBITS[ch] for ch in v)
    return v


# (name, code, inputs, expected, t_states)
CASES = [
    # ---- 8-bit add/subtract: S Z H P/V N C and X/Y from the result ----
    ('ADD A,B half-carry', '80', {'a': 0x0F, 'b': 0x01}, {'a': 0x10, 'f': 'H'}, 4),
    ('ADD A,B overflow to 80H', '80', {'a': 0x7F, 'b': 0x01}, {'a': 0x80, 'f': 'SHP'}, 4),
    ('ADD A,B both negative: carry+overflow', '80', {'a': 0x80, 'b': 0x80}, {'a': 0x00, 'f': 'ZPC'}, 4),
    ('ADD A,B wraps to zero', '80', {'a': 0xFF, 'b': 0x01}, {'a': 0x00, 'f': 'ZHC'}, 4),
    ('ADD A,B X/Y from the result', '80', {'a': 0x14, 'b': 0x14}, {'a': 0x28, 'f': 'YX'}, 4),
    ('ADC A,B takes the carry in', '88', {'a': 0x0E, 'b': 0x01, 'f': 'C'}, {'a': 0x10, 'f': 'H'}, 4),
    ('ADC A,B carry makes the overflow', '88', {'a': 0x7F, 'b': 0x00, 'f': 'C'}, {'a': 0x80, 'f': 'SHP'}, 4),
    ('SUB B half-borrow', '90', {'a': 0x10, 'b': 0x01}, {'a': 0x0F, 'f': 'HXN'}, 4),
    ('SUB B borrows through zero', '90', {'a': 0x00, 'b': 0x01}, {'a': 0xFF, 'f': 'SYHXNC'}, 4),
    ('SUB B overflow at 80H', '90', {'a': 0x80, 'b': 0x01}, {'a': 0x7F, 'f': 'YHXPN'}, 4),
    ('SUB B equal is zero', '90', {'a': 0x42, 'b': 0x42}, {'a': 0x00, 'f': 'ZN'}, 4),
    ('SBC A,B borrows the carry', '98', {'a': 0x10, 'b': 0x0F, 'f': 'C'}, {'a': 0x00, 'f': 'ZHN'}, 4),
    ('CP B: X/Y from the OPERAND, not the result', 'B8',
     {'a': 0x40, 'b': 0x28}, {'a': 0x40, 'f': 'YHXN'}, 4),
    ('CP B equal: Y still from the operand', 'B8', {'a': 0x33, 'b': 0x33}, {'f': 'ZYN'}, 4),

    # ---- logic: AND sets H, OR/XOR clear it, P is parity ----
    ('AND B to zero', 'A0', {'a': 0xF0, 'b': 0x0F}, {'a': 0x00, 'f': 'ZHP'}, 4),
    ('AND B even parity', 'A0', {'a': 0xFF, 'b': 0x81}, {'a': 0x81, 'f': 'SHP'}, 4),
    ('XOR B', 'A8', {'a': 0xFF, 'b': 0x0F}, {'a': 0xF0, 'f': 'SYP'}, 4),
    ('OR B of zeros', 'B0', {'a': 0x00, 'b': 0x00}, {'a': 0x00, 'f': 'ZP'}, 4),
    ('OR B odd parity', 'B0', {'a': 0x01, 'b': 0x06}, {'a': 0x07, 'f': ''}, 4),

    # ---- INC/DEC preserve C ----
    ('INC A keeps the carry', '3C', {'a': 0x7F, 'f': 'C'}, {'a': 0x80, 'f': 'SHPC'}, 4),
    ('INC A wraps without touching C', '3C', {'a': 0xFF, 'f': 'C'}, {'a': 0x00, 'f': 'ZHC'}, 4),
    ('DEC A half-borrow', '3D', {'a': 0x10}, {'a': 0x0F, 'f': 'HXN'}, 4),
    ('DEC A overflow at 80H', '3D', {'a': 0x80}, {'a': 0x7F, 'f': 'YHXPN'}, 4),
    ('DEC A to zero', '3D', {'a': 0x01}, {'a': 0x00, 'f': 'ZN'}, 4),

    # ---- DAA, NEG, CPL, SCF, CCF ----
    ('DAA after 9AH: +66H, carry', '27', {'a': 0x9A}, {'a': 0x00, 'f': 'ZHPC'}, 4),
    ('DAA after add of 15H+27H=3CH', '27', {'a': 0x3C}, {'a': 0x42, 'f': 'HP'}, 4),
    ('DAA after subtract with half-borrow', '27', {'a': 0x0F, 'f': 'HN'}, {'a': 0x09, 'f': 'XPN'}, 4),
    ('NEG of 01H', 'ED44', {'a': 0x01}, {'a': 0xFF, 'f': 'SYHXNC'}, 8),
    ('NEG of 80H overflows', 'ED44', {'a': 0x80}, {'a': 0x80, 'f': 'SPNC'}, 8),
    ('NEG of zero', 'ED44', {'a': 0x00}, {'a': 0x00, 'f': 'ZN'}, 8),
    ('CPL sets H and N, X/Y from the result', '2F', {'a': 0x55}, {'a': 0xAA, 'f': 'YHXN'}, 4),
    ('SCF: X/Y from A when Q is clear', '37', {'a': 0x28}, {'f': 'YXC'}, 4),
    ('CCF moves C into H', '3F', {'a': 0x00, 'f': 'C'}, {'f': 'H'}, 4),

    # ---- rotates: RLCA keeps S Z P, the CB set computes them ----
    ('RLCA', '07', {'a': 0x81}, {'a': 0x03, 'f': 'C'}, 4),
    ('RLCA preserves S Z P', '07', {'a': 0x81, 'f': 'SZP'}, {'a': 0x03, 'f': 'SZPC'}, 4),
    ('RRA rotates the carry in, S untouched', '1F', {'a': 0x01, 'f': 'C'}, {'a': 0x80, 'f': 'C'}, 4),
    ('RLC B computes S Z P', 'CB00', {'b': 0x80}, {'b': 0x01, 'f': 'C'}, 8),
    ('SRA D keeps the sign', 'CB2A', {'d': 0x81}, {'d': 0xC0, 'f': 'SPC'}, 8),
    ('SRL A to zero', 'CB3F', {'a': 0x01}, {'a': 0x00, 'f': 'ZPC'}, 8),
    ('SLA E', 'CB23', {'e': 0xC0}, {'e': 0x80, 'f': 'SC'}, 8),
    ('RLD rotates the nibbles', 'ED6F', {'a': 0x12, 'h': 0x40, 'l': 0x00, 'mem': {0x4000: 0x34}},
     {'a': 0x13, 'mem': {0x4000: 0x42}}, 18),

    # ---- BIT: Z and PV from the bit, H always, X/Y from the register ----
    ('BIT 3,A of a set bit', 'CB5F', {'a': 0x08}, {'f': 'HX'}, 8),
    ('BIT 7,B of a clear bit', 'CB78', {'b': 0x00}, {'f': 'ZHP'}, 8),
    ('BIT 0,(HL): X/Y from WZ high', 'CB46',
     {'h': 0x40, 'l': 0x00, 'wz': 0x2800, 'mem': {0x4000: 0x01}}, {'f': 'YHX'}, 12),

    # ---- 16-bit arithmetic: H from bit 11, ADD HL keeps S Z P ----
    ('ADD HL,DE half-carry, S Z P preserved', '19',
     {'h': 0x0F, 'l': 0xFF, 'd': 0x00, 'e': 0x01, 'f': 'SZP'},
     {'h': 0x10, 'l': 0x00, 'f': 'SZHP'}, 11),
    ('ADD HL,HL carries out', '29', {'h': 0x80, 'l': 0x00}, {'h': 0x00, 'l': 0x00, 'f': 'C'}, 11),
    ('ADC HL,DE overflows to 8000H', 'ED5A',
     {'h': 0x7F, 'l': 0xFF, 'd': 0x00, 'e': 0x00, 'f': 'C'},
     {'h': 0x80, 'l': 0x00, 'f': 'SHP'}, 15),
    ('ADC HL,DE: Z from all 16 bits', 'ED5A',
     {'h': 0xFF, 'l': 0xFF, 'd': 0x00, 'e': 0x00, 'f': 'C'},
     {'h': 0x00, 'l': 0x00, 'f': 'ZHC'}, 15),
    ('SBC HL,DE borrows the carry', 'ED52',
     {'h': 0x00, 'l': 0x00, 'd': 0x00, 'e': 0x00, 'f': 'C'},
     {'h': 0xFF, 'l': 0xFF, 'f': 'SYHXNC'}, 15),

    # ---- block ops ----
    ('LDI moves the byte, X/Y from A+byte, PV from BC', 'EDA0',
     {'a': 0x01, 'h': 0x40, 'l': 0x00, 'd': 0x50, 'e': 0x00, 'b': 0x00, 'c': 0x02,
      'mem': {0x4000: 0x09}},
     {'mem': {0x5000: 0x09}, 'h': 0x40, 'l': 0x01, 'd': 0x50, 'e': 0x01,
      'b': 0x00, 'c': 0x01, 'f': 'YXP'}, 16),
    ('CPI: N set, PV from BC, X/Y from result-H', 'EDA1',
     {'a': 0x10, 'h': 0x40, 'l': 0x00, 'b': 0x00, 'c': 0x02, 'mem': {0x4000: 0x01}},
     {'l': 0x01, 'c': 0x01, 'f': 'YHXPN'}, 16),

    # ---- memory and prefixed operands ----
    ('ADD A,(HL)', '86', {'a': 0x0F, 'h': 0x40, 'l': 0x00, 'mem': {0x4000: 0x01}},
     {'a': 0x10, 'f': 'H'}, 7),
    ('ADD A,(IX+1)', 'DD8601', {'a': 0x0F, 'ix': 0x4000, 'mem': {0x4001: 0x01}},
     {'a': 0x10, 'f': 'H'}, 19),
    ('IN A,(C) sets S Z P, keeps C', 'ED78',
     {'b': 0x12, 'c': 0x34, 'f': 'C', 'ports': [(0x1234, 0x80, 'r')]},
     {'a': 0x80, 'f': 'SC'}, 12),

    # ---- conditional cycle counts ----
    ('DJNZ taken', '10FE', {'b': 0x02}, {'b': 0x01, 'pc': 0x0000}, 13),
    ('DJNZ falls through', '10FE', {'b': 0x01}, {'b': 0x00, 'pc': 0x0002}, 8),
    ('JR Z taken', '2802', {'f': 'Z'}, {'pc': 0x0004}, 12),
    ('JR Z not taken', '2802', {'f': ''}, {'pc': 0x0002}, 7),
    ('CALL pushes the return address', 'CD0040', {'sp': 0x8000},
     {'pc': 0x4000, 'sp': 0x7FFE, 'mem': {0x7FFE: 0x03, 0x7FFF: 0x00}}, 17),
    ('RET pops it', 'C9', {'sp': 0x7FFE, 'mem': {0x7FFE: 0x03, 0x7FFF: 0x00}},
     {'pc': 0x0003, 'sp': 0x8000}, 10),

    # ---- register file plumbing ----
    ("EX AF,AF'", '08', {'a': 0x11, 'f': 'C', 'a2': 0x22, 'f2': 'Z'},
     {'a': 0x22, 'f': 'Z', 'a2': 0x11, 'f2': 'C'}, 4),
    ('PUSH AF stores the flag byte', 'F5', {'a': 0xAB, 'f': 'SYHXPNC', 'sp': 0x8000},
     {'sp': 0x7FFE, 'mem': {0x7FFF: 0xAB, 0x7FFE: 0xBF}}, 11),
    ('POP AF loads the flag byte', 'F1', {'sp': 0x7FFE, 'mem': {0x7FFE: 0x51, 0x7FFF: 0xCD}},
     {'a': 0xCD, 'f': 'ZHC', 'sp': 0x8000}, 10),
    ('HALT halts', '76', {}, {'pc': 0x0001}, 4),
]


class TestFlags(unittest.TestCase):

    def run_case(self, name, code, inp, want, tstates):
        mem = bytearray(65536)
        ports = list(inp.get('ports', ()))

        def port_in(port):
            if ports and ports[0][2] == 'r' and ports[0][0] == port:
                return ports.pop(0)[1]
            self.fail('%s: unexpected IN from port %04X' % (name, port))

        cpu = Z80(lambda a: mem[a], lambda a, v: mem.__setitem__(a, v), port_in,
                  lambda port, v: self.fail('%s: unexpected OUT' % name))
        for i, b in enumerate(bytes.fromhex(code)):
            mem[i] = b
        for a, v in inp.get('mem', {}).items():
            mem[a] = v
        for k, v in inp.items():
            if k in ('mem', 'ports'):
                continue
            setattr(cpu, k, flags(v) if k in ('f', 'f2') else v)
        got = cpu.step()
        self.assertEqual(got, tstates, '%s: %d T-states, want %d' % (name, got, tstates))
        for k, v in want.items():
            if k == 'mem':
                for a, b in v.items():
                    self.assertEqual(mem[a], b, '%s: mem[%04X]=%02X want %02X'
                                     % (name, a, mem[a], b))
                continue
            v = flags(v) if k in ('f', 'f2') else v
            self.assertEqual(getattr(cpu, k), v, '%s: %s=%02X want %02X'
                             % (name, k, getattr(cpu, k), v))
        self.assertFalse(ports, '%s: scripted port reads left over' % name)

    def test_cases(self):
        for case in CASES:
            with self.subTest(case[0]):
                self.run_case(*case)

    def test_halt_flag(self):
        mem = bytearray(65536)
        mem[0] = 0x76
        cpu = Z80(lambda a: mem[a], lambda a, v: mem.__setitem__(a, v))
        cpu.step()
        self.assertTrue(cpu.halted)


if __name__ == '__main__':
    unittest.main()
