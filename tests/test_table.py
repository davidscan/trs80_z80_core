"""ANCHOR 1 -- the opcode table validated against known-good disassembly.

The ANCHORS BEFORE TRUST rule: the table must pass this
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

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
    ('11CDAB', 'LD DE,0ABCDH'),
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
    ('36FF', 'LD (HL),0FFH'),
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
    ('D3FF', 'OUT (0FFH),A'),           # the cassette-port sound trick
    ('D603', 'SUB 03H'),
    ('D9', 'EXX'),
    ('DBFF', 'IN A,(0FFH)'),
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
    ('ED73FFFF', 'LD (0FFFFH),SP'),
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
    ('DD3605FF', 'LD (IX+05H),0FFH'),
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
    ('FD21DDB0', 'LD IY,0B0DDH'),      # endgame: 253,33,221,176
    ('DD2A4BB7', 'LD IX,(0B74BH)'),    # endgame: 221,42,75,183
    ('DD22D9B0', 'LD (0B0D9H),IX'),    # endgame: 221,34,217,176
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


class TestUndocumentedAgainstTheReferenceCard(unittest.TestCase):
    """Layer B' -- the undocumented half of the table checked against an
    OUTSIDE source: the Nano Systems "Z80 Microprocessor Reference Card"
    (1981), pages 7-8, the only book in the reference library that
    tabulates the undocumented set.

    The card is a scan; its dense opcode tables OCR badly and only a few
    rows survive legibly. So this class pins the three things the card
    states that ARE checkable, not a wholesale table diff:
      1. the SHAPE of the index-half-register set,
      2. the card's stated TIMING RULE (+4 T-states over the H/L form) --
         the only external check on the cycle column that exists so far,
      3. the legible rows, and SLL's status as undocumented.
    Encodings below are authored from the card's own decimal opcode
    column; no scan text is reproduced.
    """

    HALVES = ('IXH', 'IXL', 'IYH', 'IYL')

    def _half_entries(self):
        return {k: v for k, v in TABLE.items()
                if any(o.kind == 'reg' and o.value in self.HALVES
                       for o in v.operands)}

    def test_half_register_set_has_the_shape_the_card_describes(self):
        """IX/IY each gain two addressable 8-bit registers, so every
        base instruction taking H or L as a register operand has a DD
        and an FD twin: 26 per prefix, 92 in all."""
        half = self._half_entries()
        self.assertEqual(len(half), 92)
        self.assertEqual(len([k for k in half if k[0] == 0xDD]), 46)
        self.assertEqual(len([k for k in half if k[0] == 0xFD]), 46)
        by_mnem = {}
        for op in half.values():
            by_mnem[op.mnemonic] = by_mnem.get(op.mnemonic, 0) + 1
        self.assertEqual(by_mnem['LD'], 52)
        for alu in ('ADD', 'ADC', 'SUB', 'SBC', 'AND', 'XOR', 'OR', 'CP',
                    'INC', 'DEC'):
            self.assertEqual(by_mnem[alu], 4, alu)

    def test_card_timing_rule_holds_for_every_half_register_entry(self):
        """The card: timing is the corresponding H/L-operand instruction
        plus 4 T-states, for the DD/FD prefix byte.  This is the FIRST
        external validation of any part of the cycle column -- it is a
        rule, not a per-opcode table, but it constrains all 92."""
        deviations = []
        for enc, op in sorted(self._half_entries().items()):
            base = TABLE.get((op.opcode,))
            self.assertIsNotNone(base, 'no unprefixed base for %r' % (enc,))
            self.assertEqual(len(op.cycles), len(base.cycles), repr(enc))
            deltas = set(a - b for a, b in zip(op.cycles, base.cycles))
            if deltas != {4}:
                deviations.append((enc, op.cycles, base.cycles))
        self.assertEqual(deviations, [])

    def test_rows_legible_in_the_card(self):
        for text, mnemonic, operands in [
                ('DD6F', 'LD', ('IXL', 'A')),     # card 221,111
                ('DD68', 'LD', ('IXL', 'B')),     # card 221,104
                ('DD67', 'LD', ('IXH', 'A')),     # card 221,103
                ('DD44', 'LD', ('B', 'IXH')),     # card 221,068
                ('DD45', 'LD', ('B', 'IXL')),     # card 221,069
                ('FD25', 'DEC', ('IYH',)),        # card 253,037
                ('FD2C', 'INC', ('IYL',)),        # card 253,044
                ('FD2D', 'DEC', ('IYL',))]:       # card 253,045
            op = dis1(text).op
            self.assertEqual(op.mnemonic, mnemonic, text)
            self.assertEqual(tuple(o.value for o in op.operands), operands,
                             text)
            self.assertTrue(op.undoc, '%s must be flagged undocumented'
                            % text)

    def test_sll_is_flagged_undocumented(self):
        """The card is where the SLL mnemonic comes from, and it lists
        the instruction as undocumented.  The table called it documented
        until 2026-09-07; the flag drives which encoding the inverse
        (assembler) index prefers, so it is not cosmetic."""
        sll = [op for op in TABLE.values() if op.mnemonic == 'SLL']
        self.assertEqual(len(sll), 24)
        self.assertTrue(all(op.undoc for op in sll))
        self.assertTrue(dis1('CB30').op.undoc)          # SLL B
        self.assertTrue(dis1('CB36').op.undoc)          # SLL (HL)
        self.assertTrue(dis1('DDCB0136').op.undoc)      # SLL (IX+1)

    def test_documented_undocumented_split(self):
        """Pinned so the split cannot drift silently.  1032/748 as of
        2026-09-11, when the IM undocumented set was found inverted (three
        documented IM encodings flagged undocumented, two undocumented
        duplicates flagged documented -- net one more undocumented).
        Before that 1033/747 (2026-09-07, SLL corrected), and 1043/737
        while SLL was misflagged."""
        undoc = [op for op in TABLE.values() if op.undoc]
        self.assertEqual(len(TABLE), 1780)
        self.assertEqual(len(undoc), 748)
        self.assertEqual(len(TABLE) - len(undoc), 1032)

    def test_unassigned_ed_opcodes_behave_as_a_nop(self):
        """The card lists the unassigned ED page as NOP.  The table names
        them DB (right for a disassembler) but must carry NOP timing and
        length, because the SAME table feeds the core's decoder."""
        for low in (0x80, 0x8F, 0x9F, 0x00, 0x3F, 0xC0, 0xFF):
            op = TABLE[(0xED, low)]
            self.assertEqual(op.length, 2, hex(low))
            self.assertEqual(op.cycles, (8,), hex(low))
            self.assertTrue(op.undoc, hex(low))


class TestAddressesWrapAtSixtyFourK(unittest.TestCase):
    """The Z80 has 64K, so a listing that runs off the top comes back to 0.

    Every address was `base + offset` unwrapped, so bytes at FFFEH listed
    as 10000H and up -- addresses that cannot exist (the 2026-09-19 audit,
    L-52).  The relative-jump target was already wrapped, which is what
    made the inconsistency visible: `JR $` at FFFEH named FFFEH while the
    next line claimed 10000H.
    """

    def test_a_listing_past_the_top_comes_back_to_zero(self):
        text = listing(bytes([0x18, 0xFE, 0x00, 0x00]), base=0xFFFE)
        rows = [l.split()[0] for l in text.split('\n')]
        self.assertEqual(rows, ['FFFE', '0000', '0001'])

    def test_the_instruction_address_itself_wraps(self):
        ins = disassemble(bytes([0x00, 0x00]), base=0xFFFF)
        self.assertEqual([i.addr for i in ins], [0xFFFF, 0x0000])

    def test_a_relative_jump_agrees_with_the_wrapped_address(self):
        """JR $ at FFFEH targets FFFEH, and both columns say so."""
        ins = disassemble(bytes([0x18, 0xFE]), base=0xFFFE)[0]
        self.assertEqual(ins.addr, 0xFFFE)
        self.assertEqual(ins.target, 0xFFFE)


class TestTheCommandLineSaysWhatIsWrong(unittest.TestCase):
    """`python3 -m z80.disasm` answers a bad argument with a message.

    --base outside 64K was accepted and printed impossible addresses; a
    --base that is not a number, a missing file and bad --hex digits were
    tracebacks (seen during group 3, recorded with L-52).
    """

    def run_disasm(self, *args):
        import subprocess
        return subprocess.run([sys.executable, '-m', 'z80.disasm'] + list(args),
                              capture_output=True, text=True, cwd=ROOT)

    def test_a_base_outside_64k_is_refused(self):
        r = self.run_disasm('--hex', '00', '--base', '0x10000')
        self.assertEqual(r.returncode, 2)
        self.assertIn('outside 0-65535', r.stderr)
        self.assertNotIn('Traceback', r.stderr)

    def test_a_base_that_is_not_a_number_is_a_message(self):
        r = self.run_disasm('--hex', '00', '--base', 'zz')
        self.assertEqual(r.returncode, 2)
        self.assertNotIn('Traceback', r.stderr)

    def test_a_missing_file_is_a_message(self):
        r = self.run_disasm(os.path.join(ROOT, 'no', 'such.bin'))
        self.assertEqual(r.returncode, 2)
        self.assertNotIn('Traceback', r.stderr)

    def test_bad_hex_digits_are_a_message(self):
        r = self.run_disasm('--hex', 'ZZ')
        self.assertEqual(r.returncode, 2)
        self.assertNotIn('Traceback', r.stderr)

    def test_a_good_command_line_still_works(self):
        r = self.run_disasm('--hex', 'CD 7F 0A', '--base', '7F00H')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('7F00', r.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
