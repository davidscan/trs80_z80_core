"""ANCHOR 1 -- the opcode table validated against known-good disassembly.

DESIGN.md / CLAUDE.md "ANCHORS BEFORE TRUST": the table must pass this
BEFORE any classifier output is trusted. A classifier count produced
over an unvalidated table is not a measurement.

Three layers:
  A. STRUCTURAL   -- the encoding space is covered totally and the
                     declared length of every entry equals the length
                     the decoder actually consumes.
  B. KNOWN-GOOD   -- a hand-authored validation set of documented Z80
                     encodings across all six pages (main, CB, ED, DD,
                     FD, DDCB/FDCB), including the specific encodings
                     the two corpus anchors depend on.
  C. ROUND-TRIP   -- the inverse (assembler) index recovers the same
                     encoding from the mnemonic+operand signature, so
                     seam 3 (future assembler) is real, not aspirational.

The vectors are authored here from the documented instruction set.
Nothing is copied from a ROM, a magazine, or a third-party listing.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from z80.table import TABLE, INVERSE, build_table          # noqa: E402
from z80.disasm import decode, disassemble, listing        # noqa: E402


# --------------------------------------------------------------------
# B. Known-good disassembly vectors.
#    (hex bytes, base address, expected text)
# --------------------------------------------------------------------

MAIN = [
    ('00', 'NOP'),
    ('013412', 'LD BC,1234H'),
    ('02', 'LD (BC),A'),
    ('03', 'INC BC'),
    ('04', 'INC B'),
    ('05', 'DEC B'),
    ('0642', 'LD B,42H'),
    ('07', 'RLCA'),
    ('08', "EX AF,AF'"),
    ('09', 'ADD HL,BC'),
    ('0A', 'LD A,(BC)'),
    ('0B', 'DEC BC'),
    ('0F', 'RRCA'),
    ('11CDAB', 'LD DE,ABCDH'),
    ('12', 'LD (DE),A'),
    ('17', 'RLA'),
    ('1A', 'LD A,(DE)'),
    ('1F', 'RRA'),
    ('21003C', 'LD HL,3C00H'),
    ('22003C', 'LD (3C00H),HL'),
    ('27', 'DAA'),
    ('29', 'ADD HL,HL'),
    ('2A003C', 'LD HL,(3C00H)'),
    ('2F', 'CPL'),
    ('31FF7F', 'LD SP,7FFFH'),
    ('32003C', 'LD (3C00H),A'),
    ('34', 'INC (HL)'),
    ('35', 'DEC (HL)'),
    ('36FF', 'LD (HL),FFH'),
    ('37', 'SCF'),
    ('39', 'ADD HL,SP'),
    ('3A0038', 'LD A,(3800H)'),
    ('3E01', 'LD A,01H'),
    ('3F', 'CCF'),
    ('40', 'LD B,B'),
    ('45', 'LD B,L'),
    ('46', 'LD B,(HL)'),
    ('70', 'LD (HL),B'),
    ('76', 'HALT'),
    ('78', 'LD A,B'),
    ('7E', 'LD A,(HL)'),
    ('80', 'ADD A,B'),
    ('86', 'ADD A,(HL)'),
    ('88', 'ADC A,B'),
    ('90', 'SUB B'),
    ('96', 'SUB (HL)'),
    ('98', 'SBC A,B'),
    ('A0', 'AND B'),
    ('A8', 'XOR B'),
    ('B0', 'OR B'),
    ('B3', 'OR E'),
    ('B8', 'CP B'),
    ('C0', 'RET NZ'),
    ('C1', 'POP BC'),
    ('C23412', 'JP NZ,1234H'),
    ('C33412', 'JP 1234H'),
    ('C43412', 'CALL NZ,1234H'),
    ('C5', 'PUSH BC'),
    ('C610', 'ADD A,10H'),
    ('C7', 'RST 00H'),
    ('C9', 'RET'),
    ('CD7F0A', 'CALL 0A7FH'),          # USR argument-fetch trap
    ('CD9A0A', 'CALL 0A9AH'),          # USR return-value trap
    ('D3FF', 'OUT (FFH),A'),           # the cassette-port sound trick
    ('D603', 'SUB 03H'),
    ('D9', 'EXX'),
    ('DBFF', 'IN A,(FFH)'),
    ('E603', 'AND 03H'),
    ('E3', 'EX (SP),HL'),
    ('E9', 'JP (HL)'),
    ('EB', 'EX DE,HL'),
    ('F1', 'POP AF'),
    ('F3', 'DI'),
    ('F5', 'PUSH AF'),
    ('F9', 'LD SP,HL'),
    ('FB', 'EI'),
    ('FE01', 'CP 01H'),
    ('FF', 'RST 38H'),
]

# Relative branches -- resolved against a non-zero base so an
# off-by-one in the "PC after the instruction" rule cannot hide.
RELATIVE = [
    ('10FE', 0x8000, 'DJNZ 8000H'),
    ('10F6', 0x8000, 'DJNZ 7FF8H'),
    ('1805', 0x8000, 'JR 8007H'),
    ('18F2', 0x8000, 'JR 7FF4H'),
    ('2004', 0x8000, 'JR NZ,8006H'),
    ('2804', 0x8000, 'JR Z,8006H'),
    ('30FE', 0x8000, 'JR NC,8000H'),
    ('38FE', 0x8000, 'JR C,8000H'),
    ('20F1', 0x403E, 'JR NZ,4031H'),
]

CB = [
    ('CB00', 'RLC B'),
    ('CB06', 'RLC (HL)'),
    ('CB07', 'RLC A'),
    ('CB08', 'RRC B'),
    ('CB10', 'RL B'),
    ('CB18', 'RR B'),
    ('CB20', 'SLA B'),
    ('CB28', 'SRA B'),
    ('CB38', 'SRL B'),
    ('CB3F', 'SRL A'),
    ('CB40', 'BIT 0,B'),
    ('CB7E', 'BIT 7,(HL)'),
    ('CB7F', 'BIT 7,A'),
    ('CB80', 'RES 0,B'),
    ('CBBE', 'RES 7,(HL)'),
    ('CBC0', 'SET 0,B'),
    ('CBFE', 'SET 7,(HL)'),
    ('CBFF', 'SET 7,A'),
]

ED = [
    ('ED40', 'IN B,(C)'),
    ('ED41', 'OUT (C),B'),
    ('ED42', 'SBC HL,BC'),
    ('ED43003C', 'LD (3C00H),BC'),
    ('ED44', 'NEG'),
    ('ED45', 'RETN'),
    ('ED46', 'IM 0'),
    ('ED47', 'LD I,A'),
    ('ED4A', 'ADC HL,BC'),
    ('ED4B003C', 'LD BC,(3C00H)'),
    ('ED4D', 'RETI'),
    ('ED4F', 'LD R,A'),
    ('ED56', 'IM 1'),
    ('ED57', 'LD A,I'),
    ('ED5B3D40', 'LD DE,(403DH)'),     # Space Chase
    ('ED5E', 'IM 2'),
    ('ED5F', 'LD A,R'),
    ('ED67', 'RRD'),
    ('ED6F', 'RLD'),
    ('ED73FFFF', 'LD (FFFFH),SP'),
    ('ED7B0040', 'LD SP,(4000H)'),
    ('EDA0', 'LDI'),
    ('EDA1', 'CPI'),
    ('EDA2', 'INI'),
    ('EDA3', 'OUTI'),
    ('EDA8', 'LDD'),
    ('EDA9', 'CPD'),
    ('EDB0', 'LDIR'),
    ('EDB1', 'CPIR'),
    ('EDB8', 'LDDR'),
    ('EDB9', 'CPDR'),
    ('EDB3', 'OTIR'),
]

INDEX = [
    ('DD09', 'ADD IX,BC'),
    ('DD213412', 'LD IX,1234H'),
    ('DD22003C', 'LD (3C00H),IX'),
    ('DD23', 'INC IX'),
    ('DD2A003C', 'LD IX,(3C00H)'),
    ('DD2B', 'DEC IX'),
    ('DD3405', 'INC (IX+05H)'),
    ('DD3505', 'DEC (IX+05H)'),
    ('DD3605FF', 'LD (IX+05H),FFH'),
    ('DD4605', 'LD B,(IX+05H)'),
    ('DD6605', 'LD H,(IX+05H)'),      # H, NOT IXH -- (IX+d) suppresses it
    ('DD7005', 'LD (IX+05H),B'),
    ('DD7E05', 'LD A,(IX+05H)'),
    ('DD7EFB', 'LD A,(IX-05H)'),      # negative displacement
    ('DD8605', 'ADD A,(IX+05H)'),
    ('DD9605', 'SUB (IX+05H)'),
    ('DDBE05', 'CP (IX+05H)'),
    ('DDE1', 'POP IX'),
    ('DDE3', 'EX (SP),IX'),
    ('DDE5', 'PUSH IX'),
    ('DDE9', 'JP (IX)'),
    ('DDF9', 'LD SP,IX'),
    ('DD19', 'ADD IX,DE'),
    ('DD29', 'ADD IX,IX'),
    ('FD213412', 'LD IY,1234H'),
    ('FD19', 'ADD IY,DE'),
    ('FD23', 'INC IY'),
    ('FD2B', 'DEC IY'),
    ('FD6601', 'LD H,(IY+01H)'),      # endgame: 253,102,1
    ('FD7E00', 'LD A,(IY+00H)'),      # endgame: 253,126,0
    ('FD2300', 'INC IY'),             # trailing byte ignored (len check)
    ('FD25', 'DEC IYH'),              # undocumented index-half
    ('DD24', 'INC IXH'),              # undocumented index-half
    ('DD7C', 'LD A,IXH'),             # undocumented index-half
    ('DD6F', 'LD IXL,A'),             # undocumented index-half
    ('FD21DDB0', 'LD IY,B0DDH'),      # endgame: 253,33,221,176
    ('DD2A4BB7', 'LD IX,(B74BH)'),    # endgame: 221,42,75,183
    ('DD22D9B0', 'LD (B0D9H),IX'),    # endgame: 221,34,217,176
    ('DD7700', 'LD (IX+00H),A'),      # endgame: 221,119,0
    ('DD23', 'INC IX'),
    ('DD2B', 'DEC IX'),
]

DDCB = [
    ('DDCB0506', 'RLC (IX+05H)'),
    ('DDCB0546', 'BIT 0,(IX+05H)'),
    ('DDCB057E', 'BIT 7,(IX+05H)'),
    ('DDCB0586', 'RES 0,(IX+05H)'),
    ('DDCB05C6', 'SET 0,(IX+05H)'),
    ('FDCB027E', 'BIT 7,(IY+02H)'),
    ('DDCBFB46', 'BIT 0,(IX-05H)'),
]


def dis1(hexs, base=0):
    data = bytes.fromhex(hexs)
    return decode(data, 0, base)


class TestStructural(unittest.TestCase):
    """Layer A -- total coverage and self-consistent lengths."""

    def test_main_page_total(self):
        # 256 minus the four prefix escapes CB/DD/ED/FD.
        main = [k for k in TABLE if len(k) == 1]
        self.assertEqual(len(main), 252)
        for op in range(256):
            if op in (0xCB, 0xDD, 0xED, 0xFD):
                self.assertNotIn((op,), TABLE)
            else:
                self.assertIn((op,), TABLE, 'main %02X missing' % op)

    def test_prefixed_pages_total(self):
        for pfx in (0xCB, 0xED):
            for op in range(256):
                self.assertIn((pfx, op), TABLE, '%02X %02X missing'
                              % (pfx, op))
        for pfx in (0xDD, 0xFD):
            present = sum(1 for op in range(256) if (pfx, op) in TABLE)
            # same 252 as the main page: CB/DD/ED/FD escape out
            self.assertEqual(present, 252)
            for op in range(256):
                self.assertIn((pfx, 0xCB, op), TABLE)

    def test_declared_length_matches_consumed(self):
        """Every entry's declared length is what the decoder eats."""
        filler = bytes([0x11, 0x22, 0x33, 0x44])
        for enc, op in TABLE.items():
            if len(enc) == 3:          # DDCB: displacement is interior
                data = bytes([enc[0], enc[1], 0x05, enc[2]]) + filler
            else:
                data = bytes(enc) + filler
            ins = decode(data, 0, 0)
            self.assertIsNotNone(ins.op, 'no decode for %s' % (enc,))
            self.assertEqual(ins.op.encoding, enc,
                             'decoded %s, wanted %s'
                             % (ins.op.encoding, enc))
            self.assertEqual(ins.length, op.length,
                             '%s: decoder ate %d, table says %d'
                             % (enc, ins.length, op.length))

    def test_flag_strings_well_formed(self):
        for enc, op in TABLE.items():
            self.assertEqual(len(op.flags), 6, '%s bad flags' % (enc,))
            for ch in op.flags:
                self.assertIn(ch, '-*01?PV', '%s bad flag char %r'
                              % (enc, ch))

    def test_cycles_present(self):
        for enc, op in TABLE.items():
            self.assertTrue(len(op.cycles) in (1, 2))
            self.assertTrue(all(c > 0 for c in op.cycles), '%s' % (enc,))

    def test_table_is_deterministic(self):
        self.assertEqual(len(build_table()), len(TABLE))

    def test_no_truncation_on_full_sweep(self):
        """Sweeping a buffer of every encoding leaves no undecodables."""
        for enc in TABLE:
            if len(enc) == 3:
                data = bytes([enc[0], enc[1], 0x05, enc[2]])
            else:
                data = bytes(enc) + b'\x00\x00'
            for ins in disassemble(data, 0):
                self.assertFalse(ins.truncated, 'truncated on %s' % (enc,))


class TestKnownGood(unittest.TestCase):
    """Layer B -- documented encodings vs expected disassembly."""

    def _check(self, cases, base=0):
        bad = []
        for hexs, want in cases:
            got = dis1(hexs, base).text
            if got != want:
                bad.append('%-10s got %-24r want %r' % (hexs, got, want))
        if bad:
            self.fail('%d mismatch(es):\n' % len(bad) + '\n'.join(bad))

    def test_main(self):
        self._check(MAIN)

    def test_cb(self):
        self._check(CB)

    def test_ed(self):
        self._check(ED)

    def test_index(self):
        self._check(INDEX)

    def test_ddcb(self):
        self._check(DDCB)

    def test_relative(self):
        bad = []
        for hexs, base, want in RELATIVE:
            got = dis1(hexs, base).text
            if got != want:
                bad.append('%-8s @%04X got %-18r want %r'
                           % (hexs, base, got, want))
        if bad:
            self.fail('\n'.join(bad))

    def test_vector_count(self):
        """Guard against the validation set silently shrinking."""
        total = (len(MAIN) + len(CB) + len(ED) + len(INDEX)
                 + len(DDCB) + len(RELATIVE))
        self.assertGreaterEqual(total, 180)


class TestPrefixSemantics(unittest.TestCase):
    """DD/FD chaining and escape rules -- real corpus bytes hit these."""

    def test_dd_before_dd_is_discarded(self):
        ins = dis1('DDDD23')
        self.assertEqual(ins.text, 'INC IX')
        self.assertEqual(ins.ignored_prefixes, 1)
        self.assertEqual(ins.length, 3)

    def test_dd_before_fd_yields_iy(self):
        ins = dis1('DDFD23')
        self.assertEqual(ins.text, 'INC IY')

    def test_dd_before_ed_is_discarded(self):
        ins = dis1('DDED44')
        self.assertEqual(ins.text, 'NEG')

    def test_lone_prefix_truncates_cleanly(self):
        for hexs in ('DD', 'CB', 'ED', 'DDCB', 'DDCB05'):
            ins = dis1(hexs)
            self.assertTrue(ins.truncated, hexs)
            self.assertTrue(ins.invalid, hexs)


class TestRoundTrip(unittest.TestCase):
    """Layer C -- seam 3. The inverse index really does invert."""

    def test_every_documented_signature_inverts(self):
        bad = []
        for enc, op in TABLE.items():
            if op.kind == 'invalid' or op.undoc:
                continue
            sig = op.signature()
            self.assertIn(sig, INVERSE, 'no inverse for %s' % (sig,))
            back_enc, back_op = INVERSE[sig]
            if back_op.signature() != sig:
                bad.append('%s -> %s' % (sig, back_op.signature()))
        self.assertEqual(bad, [])

    def test_inverse_prefers_documented(self):
        """Undocumented aliases never shadow a documented encoding."""
        for sig, (enc, op) in INVERSE.items():
            if op.undoc:
                twins = [o for o in TABLE.values()
                         if o.signature() == sig and not o.undoc]
                self.assertEqual(twins, [], 'undoc shadows doc for %s'
                                 % (sig,))

    def test_spot_inverse_encodings(self):
        cases = [
            (('NOP', ()), (0x00,)),
            (('LD', ('BC', 'nn')), (0x01,)),
            (('CALL', ('nn',)), (0xCD,)),
            (('OUT', ('(n)', 'A')), (0xD3,)),
            (('RET', ()), (0xC9,)),
            (('LD', ('A', '(nn)')), (0x3A,)),
            (('BIT', ('7', '(HL)')), (0xCB, 0x7E)),
            (('LDIR', ()), (0xED, 0xB0)),
            (('LD', ('IX', 'nn')), (0xDD, 0x21)),
            (('SET', ('0', '(IX+d)')), (0xDD, 0xCB, 0xC6)),
        ]
        for sig, want in cases:
            self.assertIn(sig, INVERSE, '%s' % (sig,))
            self.assertEqual(INVERSE[sig][0], want, '%s' % (sig,))


class TestAccessMetadata(unittest.TestCase):
    """The classifier keys on these; wrong metadata = wrong buckets."""

    def test_absolute_addresses_surface(self):
        self.assertEqual(dis1('3A0038').abs_addresses(),
                         [('r', 0x3800, 1)])
        self.assertEqual(dis1('32003C').abs_addresses(),
                         [('w', 0x3C00, 1)])
        self.assertEqual(dis1('22003C').abs_addresses(),
                         [('w', 0x3C00, 2)])
        self.assertEqual(dis1('ED4B003C').abs_addresses(),
                         [('r', 0x3C00, 2)])

    def test_register_indirect_has_no_absolute(self):
        self.assertEqual(dis1('7E').abs_addresses(), [])
        self.assertEqual(dis1('77').abs_addresses(), [])
        self.assertEqual([a for a in dis1('7E').op.access], [('r', 'hl')])
        self.assertEqual([a for a in dis1('77').op.access], [('w', 'hl')])

    def test_port_metadata(self):
        self.assertEqual(dis1('D3FF').port(), ('out', 0xFF))
        self.assertEqual(dis1('DBFF').port(), ('in', 0xFF))
        self.assertEqual(dis1('ED41').port(), ('out', None))
        self.assertEqual(dis1('ED40').port(), ('in', None))
        self.assertIsNone(dis1('00').port())

    def test_call_targets_resolve(self):
        self.assertEqual(dis1('CD7F0A').target, 0x0A7F)
        self.assertEqual(dis1('CD9A0A').target, 0x0A9A)
        self.assertEqual(dis1('C33412').target, 0x1234)
        self.assertEqual(dis1('FF').target, 0x38)


if __name__ == '__main__':
    unittest.main(verbosity=2)
