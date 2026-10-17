"""The flow tracer (z80/trace.py): recursive descent.

Every fixture is assembled here by z80.asm from source whose code/data
layout is known, and the tracer's byte map is pinned against it: 'C' a
byte some instruction reached from an entry point occupies, '.' a byte
nothing reached.  Nothing is copied from a ROM or a period listing.
"""

import io
import os
import sys
import unittest
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from z80.asm import assemble                                    # noqa: E402
from z80 import trace                                           # noqa: E402


def build(src, org=0x7000):
    """Assemble SRC at ORG: (segments, entry, symbols)."""
    r = assemble(' ORG %d\n%s\n END ST\n' % (org, src))
    assert not r.errors, r.errors
    return r.segments, r.entry, r.symbols


def run(src, entries=None):
    segs, entry, syms = build(src)
    res = trace.trace(segs, entries if entries is not None else [entry])
    return res, segs, syms


def bytemap(res, segs):
    org, data = segs[0]
    return res.map(org, len(data))


class TestFlow(unittest.TestCase):
    """The successors of each instruction class, read off the byte map."""

    def test_jp_over_data(self):
        res, segs, _ = run('ST: JP L1\n DB 1,2,3\nL1: RET')
        self.assertEqual(bytemap(res, segs), 'CCC...C')

    def test_call_and_ret(self):
        res, segs, _ = run('ST: CALL SUB\n RET\n DB 0FFH\n'
                           'SUB: LD A,1\n RET')
        self.assertEqual(bytemap(res, segs), 'CCCC.CCC')

    def test_conditional_branch_takes_both_ways(self):
        res, segs, _ = run('ST: OR A\n JR Z,L2\n LD A,1\n RET\n'
                           'L2: XOR A\n RET\n DB 0,0')
        self.assertEqual(bytemap(res, segs), 'CCCCCCCC..')

    def test_djnz_loop(self):
        res, segs, _ = run("ST: LD B,10\nLP: NOP\n DJNZ LP\n RET\n DM 'HI'")
        self.assertEqual(bytemap(res, segs), 'CCCCCC..')

    def test_conditional_ret_falls_through(self):
        res, segs, _ = run('ST: RET NZ\n NOP\n RET\n DB 1')
        self.assertEqual(bytemap(res, segs), 'CCC.')

    def test_unconditional_jr_has_no_fall_through(self):
        res, segs, _ = run('ST: JR L1\n DB 9\nL1: RET')
        self.assertEqual(bytemap(res, segs), 'CC.C')

    def test_halt_ends_the_path(self):
        # NOPs after it: a fall-through would make them code
        res, segs, _ = run('ST: HALT\n DB 0,0')
        self.assertEqual(bytemap(res, segs), 'C..')

    def test_reti_and_retn_end_the_path(self):
        res, segs, _ = run('ST: RETI\n DB 1')
        self.assertEqual(bytemap(res, segs), 'CC.')
        res, segs, _ = run('ST: RETN\n DB 1')
        self.assertEqual(bytemap(res, segs), 'CC.')

    def test_unreached_code_stays_unknown(self):
        res, segs, _ = run('ST: RET\nOTHER: LD A,1\n RET')
        self.assertEqual(bytemap(res, segs), 'C...')

    def test_a_second_entry_point(self):
        segs, entry, syms = build('ST: RET\nOTHER: LD A,1\n RET')
        res = trace.trace(segs, [entry, syms['OTHER']])
        self.assertEqual(res.map(*_span(segs)), 'CCCC')

    def test_a_loop_back_to_visited_code_terminates(self):
        res, segs, _ = run('ST: NOP\n JR ST')
        self.assertEqual(bytemap(res, segs), 'CCC')

    def test_entry_outside_the_image_is_external(self):
        segs, _, _ = build('ST: RET')
        res = trace.trace(segs, [0x1234])
        self.assertEqual(res.map(*_span(segs)), '.')
        self.assertEqual(res.external, {0x1234: [None]})


class TestOutside(unittest.TestCase):
    """Targets outside the loaded bytes are recorded, never followed."""

    def test_call_outside_the_image(self):
        res, segs, syms = run('ST: CALL 0033H\n RET')
        self.assertEqual(bytemap(res, segs), 'CCCC')
        self.assertEqual(res.external, {0x0033: [syms['ST']]})

    def test_rst_is_a_call(self):
        res, segs, syms = run('ST: RST 28H\n RET\n DB 7')
        self.assertEqual(bytemap(res, segs), 'CC.')
        self.assertEqual(res.external, {0x28: [syms['ST']]})

    def test_an_instruction_cut_off_by_the_end(self):
        res, segs, syms = run('ST: NOP\n DB 0C3H,00H')
        self.assertEqual(bytemap(res, segs), 'C..')
        self.assertEqual(res.truncated, [syms['ST'] + 1])


class TestIndirect(unittest.TestCase):
    """An indirect jump stops its path and is reported."""

    def test_jp_hl_stops_and_is_reported(self):
        res, segs, syms = run('ST: LD HL,TGT\n JP (HL)\n DB 0\nTGT: RET')
        self.assertEqual(bytemap(res, segs), 'CCCC..')
        self.assertEqual(res.indirect, [syms['ST'] + 3])

    def test_jp_ix_and_iy(self):
        res, segs, syms = run('ST: JP (IX)\nL2: JP (IY)')
        self.assertEqual(res.indirect, [syms['ST']])
        res = trace.trace(segs, [syms['L2']])
        self.assertEqual(res.indirect, [syms['L2']])

    def test_push_then_ret_is_flagged(self):
        res, segs, syms = run('ST: LD HL,TGT\n PUSH HL\n RET\nTGT: RET')
        self.assertEqual(bytemap(res, segs), 'CCCCC.')
        self.assertEqual(res.computed, [syms['ST'] + 4])

    def test_a_plain_ret_is_not_flagged(self):
        res, _, _ = run('ST: POP HL\n RET')
        self.assertEqual(res.computed, [])


class TestConflict(unittest.TestCase):
    """A jump into the middle of an instruction is reported, never hidden."""

    def test_jump_into_an_operand(self):
        # The fall-through decodes L as LD A,0C9H first; the branch then
        # lands on its operand byte, which is a RET read the other way.
        res, segs, syms = run('ST: JR NZ,MID+1\nMID: LD A,0C9H\n RET')
        self.assertEqual(bytemap(res, segs), 'CCCCC')
        self.assertEqual(res.conflicts,
                         [trace.Conflict(syms["MID"] + 1, syms["MID"],
                                         syms['ST'])])

    def test_overlap_at_the_far_end(self):
        # The first path decodes NOP at L2 (the second byte of the 3-byte
        # LD the second path reaches); the second path's LD then overlaps it.
        segs, _, syms = build('ST: JR L1+1\nL1: LD HL,0\n RET')
        l2 = syms['L1'] + 1
        res = trace.trace(segs, [syms['ST'], syms['L1']])
        self.assertEqual([(c.addr, c.inside) for c in res.conflicts],
                         [(syms['L1'], l2)])
        self.assertNotIn(syms['L1'], res.insns)

    def test_no_conflict_when_paths_agree(self):
        res, _, _ = run('ST: JR Z,L1\n NOP\nL1: RET')
        self.assertEqual(res.conflicts, [])


class TestUndocumented(unittest.TestCase):
    """On a proven path an undocumented opcode is code, reported by kind."""

    CASES = [
        ('DB 0EDH,00H', 'hole', True),
        ('DB 0EDH,4CH', 'mirror', True),         # NEG's second encoding
        ('DB 0EDH,55H', 'mirror', True),         # RETN's (ends the path)
        ('DB 0DDH,00H', 'prefix', True),         # DD on NOP
        ('DB 0DDH,0DDH,21H,0,0', 'prefix', True),  # a prefix the CPU drops
        ('DB 0DDH,0CBH,5,40H', 'mirror', True),  # BIT 0,(IX+5) again
        ('DB 0DDH,7CH', 'index-half', False),    # LD A,IXH
        ('DB 0CBH,30H', 'sll', False),           # SLL B
        ('DB 0DDH,0CBH,5,36H', 'sll', False),    # SLL (IX+5)
        ('DB 0DDH,0CBH,5,80H', 'index-copy', False),  # RES 0,(IX+5),B
        ('DB 0EDH,70H', 'in-out-c', False),      # IN F,(C)
    ]

    def test_kinds(self):
        for src, kind, strong in self.CASES:
            with self.subTest(src=src):
                res, segs, syms = run('ST: ' + src + '\n RET')
                self.assertEqual(res.undoc, [(syms['ST'], kind)])
                self.assertEqual(trace.UNDOC_STRONG[kind], strong)

    def test_the_path_goes_on(self):
        res, segs, _ = run('ST: DB 0EDH,00H\n RET\n DB 1')
        self.assertEqual(bytemap(res, segs), 'CCC.')

    def test_documented_code_reports_none(self):
        res, _, _ = run('ST: LD (IX+3),A\n BIT 7,(IY+1)\n RET')
        self.assertEqual(res.undoc, [])


class TestExplain(unittest.TestCase):
    """--explain: the worklist, one line per step, pinned word for word."""

    def test_steps(self):
        res, _, _ = run('ST: CALL SUB\n JP (HL)\nSUB: RET NZ\n RET')
        self.assertEqual(res.steps, [
            'entry 7000',
            'pop 7000: CALL 7004H -> queue 7004, 7003',
            'pop 7003: JP (HL) -> indirect, target unknown: stop',
            'pop 7004: RET NZ -> queue 7005',
            'pop 7005: RET -> end of path',
            'done: 6 of 6 bytes code, 0 unknown',
        ])

    def test_revisit_and_conflict_are_explained(self):
        res, _, _ = run('ST: JR NZ,MID+1\nMID: LD A,0C9H\n JR ST')
        self.assertIn('pop 7000: already code', res.steps)
        self.assertIn('pop 7003: CONFLICT, inside the instruction at 7002'
                      ' (from 7000)', res.steps)


class TestListing(unittest.TestCase):
    """The listing assembles back to the bytes it was made from."""

    FIXTURES = [
        'ST: JP L1\n DB 1,2,3\nL1: RET',
        "ST: LD B,10\nLP: NOP\n DJNZ LP\n RET\n DM 'HI'",
        'ST: JR NZ,MID+1\nMID: LD A,0C9H\n RET',
        'ST: DB 0EDH,00H\n DB 0DDH,00H\n RET\n DB 0C3H,1',
        'ST: LD HL,TGT\n JP (HL)\n DS 20\nTGT: RET',
    ]

    def test_round_trip(self):
        for src in self.FIXTURES:
            with self.subTest(src=src):
                segs, entry, _ = build(src)
                res = trace.trace(segs, [entry])
                text = trace.source(res, segs)
                r = assemble(text)
                self.assertEqual(r.errors, [])
                self.assertEqual(r.segments, segs)

    def test_listing_lines(self):
        segs = [(0x7000, bytes.fromhex('C30C70' + '41' * 9 + 'C9'))]
        res = trace.trace(segs, [0x7000])
        self.assertEqual(trace.listing(res).split('\n'), [
            '7000  C3 0C 70                  JP 700CH',
            '7003  41 41 41 41 41 41 41 41 ? DB 41H,41H,41H,41H,41H,41H,41H,41H',
            '700B  41                      ? DB 41H',
            '700C  C9                        RET',
        ])

    def test_two_segments(self):
        segs = [(0x7000, bytes([0xC3, 0x00, 0x80, 0xFF])),
                (0x8000, bytes([0xC9, 0x01]))]
        res = trace.trace(segs, [0x7000])
        self.assertEqual(res.map(0x7000, 4), 'CCC.')
        self.assertEqual(res.map(0x8000, 2), 'C.')
        self.assertEqual(assemble(trace.source(res, segs)).segments, segs)


class TestCli(unittest.TestCase):

    def cli(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            trace.main(list(argv))
        return out.getvalue()

    def test_hex_with_base(self):
        out = self.cli('--hex', 'C3 04 70 FF C9', '--base', '7000H')
        self.assertIn('7000  C3 04 70', out)
        self.assertIn('7003  FF', out)
        self.assertIn('4 of 5 bytes code', out)

    def test_explain(self):
        out = self.cli('--hex', 'C9', '--base', '0x7000', '--explain')
        self.assertIn('pop 7000: RET -> end of path', out)

    def test_entry_defaults_to_the_base(self):
        out = self.cli('--hex', '00 C9 FF')
        self.assertIn('2 of 3 bytes code', out)

    def test_extra_entry(self):
        out = self.cli('--hex', 'C9 00 C9', '--entry', '1')
        self.assertIn('3 of 3 bytes code', out)

    def test_source_output_assembles_whole(self):
        data = bytes.fromhex('C30470FFC9')
        out = self.cli('--hex', data.hex(), '--base', '7000H', '--source',
                       '--explain')
        self.assertIn('; pop 7000', out)
        r = assemble(out)
        self.assertEqual((r.errors, r.segments), ([], [(0x7000, data)]))

    def test_bad_entry(self):
        with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()), \
                _quiet():
            trace.main(['--hex', 'C9', '--entry', 'zz'])


def _span(segs):
    org, data = segs[0]
    return org, len(data)


class _quiet:
    def __enter__(self):
        self.err = sys.stderr
        sys.stderr = io.StringIO()

    def __exit__(self, *a):
        sys.stderr = self.err


if __name__ == '__main__':
    unittest.main()
