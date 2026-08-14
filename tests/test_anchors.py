"""ANCHOR 2 -- extractor and classifier against the ground-truth anchors.

CLAUDE.md "ANCHORS BEFORE TRUST": the classifier must bucket the two
ground-truth anchors correctly BEFORE its corpus-wide counts mean
anything.

The anchors live in ../awk_BASIC_interpreter/OCRsamples/, a LOCAL-ONLY
sibling holding transcriptions of copyrighted magazine listings. They
are read IN PLACE by path and never copied into this repo (DESIGN.md
"PHASE A INPUT SET"). If the sibling is absent these tests skip rather
than fail, so the suite stays green on a machine without the corpus --
but the sweep refuses to publish counts if they did not run.

ON THE ENDGAME ANCHOR. DESIGN.md described it as "endgame SCAN3
(keyboard scan)". Phase A measured it as a PURE-COMPUTE routine with no
3800H-38FFH access at all, and the parent's own FINDING 29 notes agree:
SCAN3 is "the whole EVENT-CLOCK scan", and line 1240 calls it as
USR 1(VARPTR(IC(1))) where IC() is the event-clock array. The
expectation was a mis-gloss; the measurement stands. These tests assert
the MEASURED behavior and assert the absence of keyboard access
explicitly, so the refuted expectation cannot creep back in.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phasea.extract import extract_file                      # noqa: E402
from phasea.classify import classify                         # noqa: E402
from z80.disasm import disassemble                           # noqa: E402

OCR = '../awk_BASIC_interpreter/OCRsamples'
SPACECHASE = os.path.join(OCR, 'spacechase.transcribed.bas')
ENDGAME = os.path.join(OCR, 'endgame.transcribed.cleaned.bas')
ENDGAME_RAW = os.path.join(OCR, 'endgame.transcribed.bas')


def ml_payloads(rep):
    return [p for p in rep.payloads if p.kind == 'candidate-ml']


@unittest.skipUnless(os.path.exists(SPACECHASE), 'OCRsamples not present')
class TestSpaceChaseAnchor(unittest.TestCase):
    """Sound-only USR. Should run under Stage 1 with sound swallowed."""

    @classmethod
    def setUpClass(cls):
        cls.rep = extract_file(SPACECHASE)
        cls.p = ml_payloads(cls.rep)[0]
        cls.c = classify(bytes(cls.p.bytes), cls.p.base, [0])

    def test_extraction_is_count_and_address_locked(self):
        # FOR C=16446 TO 16474 -> 29 bytes at 403EH
        self.assertEqual(self.p.base, 0x403E)
        self.assertEqual(self.p.length, 29)
        self.assertEqual(self.p.confidence, 'high')
        self.assertEqual(self.p.flags, [])
        self.assertTrue(self.p.provenance['ends_on_data_boundary'])

    def test_usr_vector_agrees_with_load_address(self):
        # POKE 16526,62 : POKE 16527,64  ->  62 + 64*256 = 16446 = 403EH
        vec = [e for e in self.rep.usr_entries if e.kind == 'vector-poke']
        self.assertEqual(len(vec), 1)
        self.assertEqual(vec[0].addr, 0x403E)
        self.assertEqual(vec[0].addr, self.p.base)

    def test_buckets_as_sound(self):
        self.assertEqual(self.c.bucket, 'sound')
        self.assertIn('port-FF-out', self.c.evidence['direct'])
        self.assertEqual(self.c.ports_out, [0xFF])

    def test_stage1_unlocks_it(self):
        self.assertTrue(self.c.stage1_ok)
        self.assertEqual(self.c.stage2_traps, [])
        self.assertEqual([a for a, _n in self.c.rom_calls], [0x0A7F])

    def test_decode_is_total_and_terminates(self):
        q = self.c.quality
        self.assertEqual(q['coverage'], 1.0)
        self.assertEqual(q['invalid_in_reachable'], 0)
        self.assertTrue(q['ends_exactly_on_ret'])

    def test_usr_results_are_discarded_by_the_listing(self):
        """Sound-only: many USR calls, none load-bearing."""
        self.assertGreater(self.rep.usr_calls, 30)


@unittest.skipUnless(os.path.exists(ENDGAME), 'OCRsamples not present')
class TestEndgameAnchor(unittest.TestCase):
    """The FINDING 29 lock: count-, address- and entry-offset-checked."""

    @classmethod
    def setUpClass(cls):
        cls.rep = extract_file(ENDGAME)
        cls.p = ml_payloads(cls.rep)[0]
        cls.c = classify(bytes(cls.p.bytes), cls.p.base, [0, 13])

    def test_finding29_count_and_address_lock(self):
        # FOR I=-20480 TO -20267 : negative Level II addresses wrap
        self.assertEqual(self.p.base, 0xB000)          # -20480 & 0xFFFF
        self.assertEqual(self.p.length, 214)           # -20267 - -20480 + 1
        self.assertEqual(self.p.confidence, 'high')
        self.assertTrue(self.p.provenance['ends_on_data_boundary'])
        self.assertEqual(self.p.provenance['count_declared'], 214)
        self.assertEqual(self.p.provenance['values_found'], 214)

    def test_def_usr_entries(self):
        e = {x.slot: x.addr for x in self.rep.usr_entries
             if x.kind == 'def-usr'}
        self.assertEqual(e, {0: 0xB000, 1: 0xB00D})

    def test_finding29_entry_offset_lock(self):
        """USR1 - USR0 = 13 = CALL(3) + 6 NOPs + LD (nn),HL(3) + RET(1).

        FINDING 29 verified that offset against the PRINTED assembly
        listing by hand. Re-deriving it from the bytes is an external
        check on the opcode table's lengths.
        """
        ins = disassemble(bytes(self.p.bytes[:13]), 0xB000)
        self.assertEqual([i.op.mnemonic for i in ins],
                         ['CALL'] + ['NOP'] * 6 + ['LD', 'RET'])
        self.assertEqual(sum(i.length for i in ins), 13)
        self.assertEqual(ins[0].target, 0x0A7F)        # = 2687 = GETHL

    def test_buckets_as_pure_compute_not_keyboard(self):
        """The measured result, and the refuted expectation, both pinned."""
        self.assertEqual(self.c.bucket, 'pure-compute')
        self.assertNotIn('keyboard', self.c.buckets_all)
        self.assertNotIn('keyboard-read', self.c.evidence['direct'])
        self.assertNotIn('keyboard-read', self.c.evidence['inferred'])

    def test_no_keyboard_bytes_anywhere_in_the_payload(self):
        """Belt and braces: no 3800H-38FFH address occurs at all."""
        data = bytes(self.p.bytes)
        for ins in disassemble(data, 0xB000):
            for _m, addr, _w in ins.abs_addresses():
                self.assertFalse(0x3800 <= addr <= 0x38FF,
                                 'unexpected keyboard access at %04X'
                                 % ins.addr)

    def test_stage1_unlocks_it(self):
        self.assertTrue(self.c.stage1_ok)
        self.assertEqual(self.c.stage2_traps, [])
        self.assertEqual([a for a, _n in self.c.rom_calls], [0x0A7F])

    def test_decode_is_total_and_terminates(self):
        q = self.c.quality
        self.assertEqual(q['coverage'], 1.0)
        self.assertEqual(q['invalid_in_reachable'], 0)
        self.assertTrue(q['ends_exactly_on_ret'])

    @unittest.skipUnless(os.path.exists(ENDGAME_RAW), 'raw transcription absent')
    def test_uncleaned_transcription_extracts_identically(self):
        rep = extract_file(ENDGAME_RAW)
        p = ml_payloads(rep)[0]
        self.assertEqual((p.base, p.length), (0xB000, 214))
        self.assertEqual(p.bytes, self.p.bytes)


class TestByteRangeLint(unittest.TestCase):
    """FINDING 29 wished for this lint; the extractor now has it.

    'A byte impossible as Z80 (281 at 4420) pinpointed the last digit
    error -- a POKE-loop DATA range lint (items 0..255) would have
    caught it statically.' The human transcription is clean at 4420, so
    the lint is demonstrated synthetically rather than claimed to have
    fired on the anchor.
    """

    def test_out_of_range_byte_downgrades_confidence(self):
        import tempfile
        from phasea.extract import extract_file as ex
        src = ('10 FOR I=32000 TO 32003:READ J:POKE I,J:NEXT\n'
               '20 DATA 205,127,281,201\n')
        with tempfile.NamedTemporaryFile('w', suffix='.bas',
                                         delete=False) as fh:
            fh.write(src)
            path = fh.name
        try:
            rep = ex(path)
            p = rep.payloads[0]
            self.assertEqual(p.confidence, 'low')
            self.assertTrue(any(f.startswith('data-out-of-byte-range')
                                for f in p.flags), p.flags)
        finally:
            os.unlink(path)


if __name__ == '__main__':
    unittest.main(verbosity=2)
