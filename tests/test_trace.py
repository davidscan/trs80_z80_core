"""The flow tracer (z80/trace.py): recursive descent.

Every fixture is assembled here by z80.asm from source whose code/data
layout is known, and the tracer's byte map is pinned against it: 'C' a
byte some instruction reached from an entry point occupies, '.' a byte
nothing reached.  Nothing is copied from a ROM or a period listing.
"""

import io
import os
import re
import sys
import unittest
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from z80.asm import assemble                                    # noqa: E402
from z80 import trace                                           # noqa: E402
from z80 import hints                                           # noqa: E402


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
        res = trace.trace(segs, [0x7000], guess=False)
        self.assertEqual(trace.listing(res).split('\n'), [
            '7000  C3 0C 70                  L7000    JP L700C',
            '7003  41 41 41 41 41 41 41 41 ?          DB 41H,41H,41H,41H,41H,41H,41H,41H',
            '700B  41                      ?          DB 41H',
            '700C  C9                        L700C    RET ; from 7000 jump',
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

    def test_hints_file(self):
        path = os.path.join(_tmp(), 'p.hints')
        with open(path, 'w') as f:
            f.write('label 7004 FINISH\n')
        out = self.cli('--hex', 'C3 04 70 FF C9', '--base', '7000H',
                       '--hints', path)
        self.assertIn('JP FINISH', out)

    def test_a_later_hints_file_wins_and_is_reported(self):
        path = os.path.join(_tmp(), 'mine.hints')
        with open(path, 'w') as f:
            f.write('label 0033 DSP\n')
        out = self.cli('--hex', 'CD 33 00 C9', '--base', '7000H',
                       '--hints', MODEL1, '--hints', path)
        self.assertIn('CALL DSP', out)
        self.assertIn('hint override: 0033: DSP replaces VDCHAR (%s)' % path, out)

    def test_bad_hints_file_names_the_line(self):
        path = os.path.join(_tmp(), 'bad.hints')
        with open(path, 'w') as f:
            f.write('entry 7000\nentry nowhere\n')
        err = io.StringIO()
        with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()):
            stderr, sys.stderr = sys.stderr, err
            try:
                trace.main(['--hex', 'C9', '--hints', path])
            finally:
                sys.stderr = stderr
        self.assertIn('bad.hints:2:', err.getvalue())

    def test_bad_entry(self):
        with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()), \
                _quiet():
            trace.main(['--hex', 'C9', '--entry', 'zz'])


class TestHintsFile(unittest.TestCase):
    """The hints file: one keyword per line, every mistake named by line."""

    def test_every_keyword(self):
        h = hints.parse(
            '; a whole-line comment\n'
            'entry 8120 key handler ; reached via JP (HL)\n'
            'label 0033H DSP\n'
            'data 0x7F40-7F4F text\n'
            'code 8200-8240\n'
            'inline 28 1\n'
            'inline 5300 until 0DH\n'
            'inline 5310 until bit7\n'
            'noreturn 0\n'
            'noreturn 38 rst\n'
            'table 8000 8\n'
            'comment 7F12 wait for vertical blank\n')
        self.assertEqual(h.entries, [0x8120])
        self.assertEqual(h.labels, {0x33: 'DSP'})
        self.assertEqual(h.data, [(0x7F40, 0x7F4F, 'text')])
        self.assertEqual(h.code, [(0x8200, 0x8240)])
        self.assertEqual(h.inline, {0x28: 1, 0x5300: ('until', 0x0D),
                                    0x5310: ('until', 'bit7')})
        self.assertEqual(h.noreturn, {0: 'call', 0x38: 'rst'})
        self.assertEqual(h.tables, [(0x8000, 8)])
        self.assertEqual(h.comments, {0x8120: ['key handler'],
                                      0x7F12: ['wait for vertical blank']})

    def test_bare_numbers_are_hex_and_counts_decimal(self):
        h = hints.parse('entry 10\ntable 20 10\ndata 7000 bytes')
        self.assertEqual(h.entries, [0x10])
        self.assertEqual(h.tables, [(0x20, 10)])
        self.assertEqual(h.data, [(0x7000, 0x7000, 'bytes')])

    def test_errors_name_the_line(self):
        bad = [
            ('entry 7G00', 'hints:2:'),
            ('lable 7000 X', 'cannot read'),
            ('data 7000-7003 floats', 'data type floats'),
            ('data 7000-7002 words', 'even number'),
            ('data 7003-7000 bytes', 'ends before it starts'),
            ('label 7000 2X', 'not a label'),
            ('label 7000 HL', 'not a label'),
            ('inline 28 0', 'count must be 1'),
            ('inline 28 until 100', 'one byte'),
            ('inline 28 upto 0', 'cannot read'),
            ('noreturn', 'cannot read'),
            ('noreturn 0 call', 'cannot read'),
            ('entry 10000', 'outside'),
            ('table 8000', 'cannot read'),
        ]
        for line, msg in bad:
            with self.subTest(line=line):
                with self.assertRaises(hints.HintError) as cm:
                    hints.parse('; ok\n' + line)
                self.assertIn('hints:2:', str(cm.exception))
                self.assertIn(msg, str(cm.exception))

    def test_one_name_one_address(self):
        with self.assertRaises(hints.HintError):
            hints.parse('label 7000 A1\nlabel 7000 B1')
        with self.assertRaises(hints.HintError):
            hints.parse('label 7000 A1\nlabel 7001 a1')
        hints.parse('label 7000 A1\nlabel 7000 A1')        # the same twice is fine

    def test_merge(self):
        a = hints.parse('label 33 DSP\nentry 7000')
        a.merge(hints.parse('label 49 KBWAIT\nentry 7100'))
        self.assertEqual(a.labels, {0x33: 'DSP', 0x49: 'KBWAIT'})
        self.assertEqual(a.entries, [0x7000, 0x7100])
        self.assertEqual(a.overrides, [])

    def test_a_later_file_renames_an_address(self):
        a = hints.parse('label 33 VDCHAR', 'model1.hints')
        a.merge(hints.parse('label 33 DSP', 'mine.hints'))
        self.assertEqual(a.labels, {0x33: 'DSP'})
        self.assertEqual(a.overrides,
                         ['0033: DSP replaces VDCHAR (mine.hints)'])

    def test_a_later_file_moves_a_name(self):
        a = hints.parse('label 33 VDCHAR', 'model1.hints')
        a.merge(hints.parse('label 7000 vdchar', 'mine.hints'))
        self.assertEqual(a.labels, {0x7000: 'vdchar'})
        self.assertEqual(a.overrides,
                         ['vdchar: names 7000, no longer 0033 (mine.hints)'])

    def test_a_var_and_a_label_take_over_from_each_other(self):
        a = hints.parse('var 409C DEVFLG')
        a.merge(hints.parse('label 409C OUTDEV'))
        self.assertEqual((a.labels, a.vars), ({0x409C: 'OUTDEV'}, {}))
        a.merge(hints.parse('var 409C DEVFLG'))
        self.assertEqual((a.labels, a.vars), ({}, {0x409C: 'DEVFLG'}))

    def test_the_same_name_changing_kind(self):
        a = hints.parse('var 409C DEVFLG')
        a.merge(hints.parse('label 409C DEVFLG'))
        self.assertEqual((a.labels, a.vars), ({0x409C: 'DEVFLG'}, {}))
        a.merge(hints.parse('var 409C DEVFLG'))
        self.assertEqual((a.labels, a.vars), ({}, {0x409C: 'DEVFLG'}))

    def test_overrides_carry_through_a_merge_of_merges(self):
        b = hints.parse('label 33 VDCHAR', 'one')
        b.merge(hints.parse('label 33 DSP', 'two'))
        a = hints.parse('entry 7000')
        a.merge(b)
        self.assertEqual(a.overrides, ['0033: DSP replaces VDCHAR (two)'])

    def test_within_one_file_a_var_is_still_one_name(self):
        for text in ('var 409C A1\nlabel 409C A1', 'var 409C A1\nvar 409D A1',
                     'label 7000 A1\nvar 409C A1'):
            with self.subTest(text=text):
                with self.assertRaises(hints.HintError):
                    hints.parse(text)
        self.assertEqual(hints.parse('var 409C A1\nvar 409C A1').vars,
                         {0x409C: 'A1'})


def hinted(src, text):
    segs, entry, syms = build(src)
    return trace.trace(segs, [entry], hints.parse(text)), segs, syms


def round_trips(test, res, segs):
    r = assemble(trace.source(res))
    test.assertEqual(r.errors, [])
    test.assertEqual(r.segments, segs)


class TestLabels(unittest.TestCase):
    """Labels for every address the code names, and who names it."""

    def test_flow_targets(self):
        res, segs, syms = run('ST: CALL SUB\n JR ST\nSUB: RET')
        self.assertEqual(res.names, {syms['ST']: 'L7000', syms['SUB']: 'L7005'})
        self.assertEqual(res.refs[syms['SUB']], [(syms['ST'], 'call')])
        self.assertEqual(res.refs[syms['ST']],
                         [(None, 'entry'), (syms['ST'] + 3, 'jump')])
        round_trips(self, res, segs)

    def test_data_references(self):
        res, segs, syms = run('ST: LD A,(V)\n LD (V+1),A\n LD HL,MSG\n'
                              ' LD BC,1234H\n RET\nV: DB 0,0\nMSG: DM \'HI\'')
        refs = {t: k for t, lst in res.refs.items() for _, k in lst}
        self.assertEqual(refs[syms['V']], 'read')
        self.assertEqual(refs[syms['V'] + 1], 'write')
        self.assertEqual(refs[syms['MSG']], 'addr')
        self.assertNotIn(0x1234, refs)               # outside the image: a number
        self.assertIn(syms['V'] + 1, res.names)
        text = trace.source(res)
        self.assertIn('LD A,(L%04X)' % syms['V'], text)
        self.assertIn('LD HL,L%04X' % syms['MSG'], text)
        self.assertIn('LD BC,1234H', text)
        round_trips(self, res, segs)

    def test_data_ref_in_explain(self):
        res, _, _ = run('ST: LD HL,V\n RET\nV: DB 0')
        self.assertIn('pop 7000: LD HL,7004H [data ref 7004 addr] -> queue 7003',
                      res.steps)

    def test_a_label_inside_an_instruction_is_an_equ(self):
        res, segs, syms = run('ST: JR NZ,MID+1\nMID: LD A,0C9H\n RET')
        text = trace.source(res)
        self.assertIn('L7003    EQU 7003H', text)
        round_trips(self, res, segs)

    def test_outside_names_come_only_from_hints(self):
        res, segs, _ = run('ST: CALL 0033H\n RET')
        self.assertNotIn(0x33, res.names)
        res, segs, _ = hinted('ST: CALL 0033H\n RET', 'label 33 DSP')
        text = trace.source(res)
        self.assertIn('DSP      EQU 0033H', text)
        self.assertIn('CALL DSP', text)
        self.assertIn('external 0033 (DSP) from 7000', trace.report(res))
        round_trips(self, res, segs)

    def test_an_outside_name_is_not_put_on_a_constant(self):
        # LD BC,0033H may be a count; only a jump, call or (nn) is renamed
        res, segs, _ = hinted('ST: LD BC,0033H\n CALL 0033H\n RET', 'label 33 DSP')
        text = trace.source(res)
        self.assertIn('LD BC,0033H', text)
        self.assertIn('CALL DSP', text)
        round_trips(self, res, segs)

    def test_a_label_splits_a_data_run(self):
        res, segs, _ = run('ST: LD A,(V+3)\n RET\nV: DB 1,2,3,4,5')
        text = trace.source(res)
        self.assertNotIn('EQU', text)
        self.assertIn('L7007    DB 04H,05H', text)
        round_trips(self, res, segs)

    def test_a_label_inside_a_word_table(self):
        res, segs, _ = hinted('ST: LD A,(T+1)\n RET\nT: DW 1234H,5678H',
                              'data 7004-7007 words')
        text = trace.source(res)
        self.assertIn('         DB 34H\nL7005    DB 12H,78H,56H', text)
        round_trips(self, res, segs)

    def test_a_hint_name_inside_the_image(self):
        res, segs, syms = hinted('ST: CALL SUB\n RET\nSUB: RET', 'label 7004 PRINT')
        self.assertEqual(res.names[syms['SUB']], 'PRINT')
        self.assertIn('CALL PRINT', trace.source(res))
        round_trips(self, res, segs)

    def test_an_auto_name_never_takes_a_hint_name(self):
        res, _, syms = hinted('ST: CALL SUB\n RET\nSUB: RET', 'label 7000 L7004')
        self.assertEqual(res.names[syms['SUB']], 'L7004_')

    def test_xref_and_hint_comment_in_the_listing(self):
        res, _, _ = hinted('ST: CALL SUB\n RET\nSUB: RET',
                           'comment 7004 the subroutine')
        self.assertIn('L7004    RET ; from 7000 call; the subroutine',
                      trace.listing(res))


class TestVars(unittest.TestCase):
    """A var names a RAM location in (nn), and never the program's bytes."""

    def test_names_nn_only(self):
        res, segs, _ = hinted('ST: LD A,(409CH)\n LD HL,409CH\n'
                              ' LD (409CH),A\n RET',
                              'var 409C DEVFLG\ncomment 409C output device')
        text = trace.source(res)
        self.assertIn('LD A,(DEVFLG)', text)
        self.assertIn('LD (DEVFLG),A', text)
        self.assertIn('LD HL,409CH', text)
        self.assertIn('DEVFLG   EQU 409CH ; output device', text)
        round_trips(self, res, segs)

    def test_never_a_jump_target(self):
        res, segs, _ = hinted('ST: CALL 41C4H\n RET', 'var 41C4 HOOK')
        text = trace.source(res)
        self.assertIn('CALL 41C4H', text)
        self.assertNotIn('HOOK', text)
        self.assertNotIn('HOOK', trace.report(res))
        round_trips(self, res, segs)

    def test_never_a_relative_target(self):
        res, segs, _ = hinted('ST: JR NZ,7010H\n RET', 'var 7010 FLAG')
        text = trace.source(res)
        self.assertIn('JR NZ,7010H', text)
        round_trips(self, res, segs)

    def test_a_program_loaded_over_it_keeps_its_bytes(self):
        segs, _, _ = build('ST: LD A,(V)\n RET\nV: DB 1', org=0x409A)
        res = trace.trace(segs, [0x409A],
                          hints.parse('var 409E DEVFLG\ncomment 409E output device'))
        text = trace.source(res)
        self.assertNotIn('DEVFLG', text)
        self.assertNotIn('output device', text)
        self.assertIn('L409E', text)
        round_trips(self, res, segs)

    def test_an_unused_var_writes_no_equ(self):
        res, _, _ = hinted('ST: RET', 'var 409C DEVFLG')
        self.assertNotIn('DEVFLG', trace.source(res))


class TestHintEffects(unittest.TestCase):

    def test_inline_data_after_a_call(self):
        res, segs, syms = hinted('ST: RST 28H\n DB 5\n RET\n DB 9', 'inline 28 1')
        self.assertEqual(bytemap(res, segs), 'CDC.')
        round_trips(self, res, segs)

    def test_inline_until_a_terminator(self):
        src = "ST: CALL PR\n DM 'HI'\n DB 0\n RET\nPR: RET\n DB 9"
        res, segs, _ = hinted(src, 'inline 7007 until 00')
        self.assertEqual(bytemap(res, segs), 'CCC' + 'DDD' + 'CC.')
        self.assertEqual(res.data[0x7003], ('text', 0x7003))
        text = trace.source(res)
        self.assertIn("DM 'HI'", text)
        round_trips(self, res, segs)

    def test_inline_until_bit7(self):
        res, segs, _ = hinted("ST: RST 28H\n DM 'O'\n DB 'K'+80H\n RET",
                              'inline 28 until bit7')
        self.assertEqual(bytemap(res, segs), 'CDDC')
        round_trips(self, res, segs)

    def test_inline_with_no_terminator_stops_the_path(self):
        res, segs, _ = hinted("ST: RST 28H\n DM 'NO END'", 'inline 28 until 0DH')
        self.assertEqual(res.truncated, [0x7000])
        self.assertEqual(bytemap(res, segs), 'C' + 't' * 6)     # S3's guess
        self.assertIn('no terminator', '\n'.join(res.steps))

    def test_noreturn_ends_the_path(self):
        res, segs, _ = hinted("ST: RST 0\n DM 'X'", 'noreturn 0')
        self.assertEqual(bytemap(res, segs), 'C.')
        self.assertIn('never returns', '\n'.join(res.steps))

    def test_noreturn_rst_leaves_a_call_alone(self):
        res, segs, _ = hinted('ST: CALL 0\n RET', 'noreturn 0 rst')
        self.assertEqual(bytemap(res, segs), 'CCCC')
        res, segs, _ = hinted('ST: RST 0\n RET', 'noreturn 0 rst')
        self.assertEqual(bytemap(res, segs), 'C.')

    def test_a_conditional_call_to_noreturn_still_falls_through(self):
        res, segs, _ = hinted('ST: CALL Z,0\n RET', 'noreturn 0')
        self.assertEqual(bytemap(res, segs), 'CCCC')

    def test_inline_without_the_hint_decodes_the_byte(self):
        res, segs, _ = run('ST: RST 28H\n DB 5\n RET\n DB 9')
        self.assertEqual(res.truncated, [])
        self.assertEqual(bytemap(res, segs)[:2], 'CC')

    def test_jump_table(self):
        src = ('ST: LD HL,TAB\n JP (HL)\nTAB: DW A1,A2\n'
               'A1: RET\nA2: XOR A\n RET\n DB 7')
        res, segs, syms = hinted(src, 'table %04X 2' % (0x7000 + 4))
        self.assertEqual(bytemap(res, segs), 'CCCC' + 'DDDD' + 'CCC.')
        self.assertEqual(res.refs[syms['A2']], [(syms['TAB'] + 2, 'table')])
        text = trace.source(res)
        self.assertIn('DW L7008,L7009', text)
        round_trips(self, res, segs)

    def test_data_hint_against_proven_code_is_a_conflict(self):
        res, segs, syms = hinted('ST: NOP\n LD A,1\n RET', 'data 7002-7003 bytes')
        self.assertEqual(res.conflicts,
                         [trace.Conflict(syms['ST'] + 1, 0x7002, syms['ST'], 'data')])
        self.assertEqual(bytemap(res, segs), 'C.DD')
        self.assertIn('conflict at 7001: inside the data hinted at 7002, from 7000',
                      trace.report(res))

    def test_text_and_words(self):
        res, segs, _ = hinted("ST: RET\n DM 'IT''S'\n DB 0\n DW 7000H,0C000H",
                              'data 7001-7004 text\ndata 7005-7005 bytes\n'
                              'data 7006-7009 words')
        text = trace.source(res)
        self.assertIn("DM 'IT''S'", text)
        self.assertIn('DW L7000,0C000H', text)
        self.assertEqual(bytemap(res, segs), 'C' + 'D' * 9)
        round_trips(self, res, segs)

    def test_text_with_a_control_byte(self):
        res, segs, _ = hinted("ST: RET\n DM 'AB'\n DB 0DH\n DM 'C'",
                              'data 7001-7004 text')
        text = trace.source(res)
        self.assertIn("DM 'AB'", text)
        self.assertIn('DB 0DH', text)
        round_trips(self, res, segs)

    def test_code_hint_reaches_what_flow_does_not(self):
        res, segs, _ = hinted('ST: RET\n NOP\n RET\n NOP\n RET\n DB 1',
                              'code 7001-7004')
        self.assertEqual(bytemap(res, segs), 'CCCCC.')
        self.assertIn('code hint: 7003 not reached yet', res.steps)

    def test_code_hint_over_bytes_that_do_not_decode(self):
        res, segs, _ = hinted('ST: RET\n DB 0C3H', 'code 7001-7001')
        self.assertEqual(res.truncated, [0x7001])
        self.assertEqual(bytemap(res, segs), 'C.')

    def test_entry_hint_with_comment(self):
        res, segs, syms = hinted('ST: RET\nHND: XOR A\n RET',
                                 'entry 7001 key handler')
        self.assertEqual(bytemap(res, segs), 'CCC')
        self.assertIn('key handler', trace.listing(res))

    def test_summary_counts_data(self):
        res, _, _ = hinted('ST: RET\n DB 1,2\n DB 3', 'data 7001-7002 bytes')
        self.assertEqual(res.summary(), '1 of 4 bytes code, 2 data, 1 unknown')


class TestGuess(unittest.TestCase):
    """S3: what the bytes nothing reached are guessed to be."""

    def test_a_string_with_its_terminator(self):
        res, segs, _ = run("ST: RET\n DM 'HELLO'\n DB 0DH\n DB 1,2")
        self.assertEqual(bytemap(res, segs), 'C' + 't' * 6 + '..')
        self.assertEqual(res.guess[0x7001], ('text', 0x7001))
        round_trips(self, res, segs)

    def test_a_bit7_terminated_string(self):
        res, segs, _ = run("ST: RET\n DM 'STOPP'\n DB 'S'+80H\n DB 1")
        self.assertEqual(bytemap(res, segs), 'C' + 't' * 6 + '.')
        round_trips(self, res, segs)

    def test_the_bit7_character_does_not_count(self):
        # four printable bytes and a RET (C9H) are code often enough
        res, segs, _ = run("ST: RET\n DM 'STOP'\n DB 'S'+80H")
        self.assertEqual(bytemap(res, segs), 'C' + '.' * 5)

    def test_short_or_letterless_runs_are_not_text(self):
        res, segs, _ = run("ST: RET\n DM 'ABCD'\n DB 0\n DM '12.50'\n DB 1")
        self.assertEqual(bytemap(res, segs), 'C' + '.' * 11)

    def test_a_word_table_of_routines(self):
        src = ('ST: CALL A1\n RET\nTAB: DW A1,ST,A1\nA1: RET\n DB 7')
        res, segs, syms = run(src)
        self.assertEqual(bytemap(res, segs), 'CCCC' + 'w' * 6 + 'C.')
        self.assertIn((syms['TAB'] + 2, 'word'), res.refs[syms['ST']])
        text = trace.source(res)
        self.assertIn('DW L700A,L7000,L700A', text)
        round_trips(self, res, segs)

    def test_words_that_point_at_data_are_not_a_table(self):
        res, segs, _ = run('ST: RET\n DW 7003H,7004H\n DB 1')
        self.assertEqual(bytemap(res, segs), 'C' + '.' * 5)

    def test_fill(self):
        res, segs, _ = run('ST: RET\n DB 0,0,0,0,0\n DB 0FFH,0FFH,0FFH\n DB 1')
        self.assertEqual(bytemap(res, segs), 'C' + 'f' * 5 + '....')
        round_trips(self, res, segs)
        res, segs, _ = run("ST: RET\n DM 'AAAAA'")     # one letter: fill
        self.assertEqual(bytemap(res, segs), 'C' + 'f' * 5)

    def test_a_hint_overrides_a_guess(self):
        res, segs, _ = hinted("ST: RET\n DM 'HELLO'", 'data 7001-7005 bytes')
        self.assertEqual(bytemap(res, segs), 'C' + 'D' * 5)
        self.assertEqual(res.guess, {})

    def test_never_over_code_and_nothing_traced_from_a_guess(self):
        src = 'ST: RET\nTAB: DW X,X\nX: NOP\n RET'
        res, segs, _ = run(src)
        self.assertEqual(bytemap(res, segs), 'C......')  # X is not traced: no table
        self.assertEqual(res.guess, {})

    def test_the_listing_flags_and_summary(self):
        # the text takes its 00 terminator; the four zeros after are fill
        res, segs, _ = run("ST: RET\n DM 'HELLO'\n DB 0,0,0,0,0\n DB 9")
        listing = trace.listing(res)
        self.assertRegex(listing, r"7001  48 45 4C 4C 4F +t +DM 'HELLO'")
        self.assertRegex(listing, r'7006  00 +t +DB 00H')
        self.assertRegex(listing, r'7007  00 00 00 00 +f +DB')
        self.assertEqual(res.summary(), '1 of 12 bytes code, '
                         '10 guessed data (6 text, 4 fill), 1 unknown')

    def test_no_guess(self):
        res, segs, _ = run("ST: RET\n DM 'HELLO'")
        self.assertEqual(trace.trace(segs, [0x7000], guess=False).guess, {})
        for args, flag in ((['--hex', 'C9 48 45 4C 4C 4F', '--base', '7000H'], 't'),
                           (['--hex', 'C9 48 45 4C 4C 4F', '--base', '7000H',
                             '--no-guess'], '?')):
            out = io.StringIO()
            with redirect_stdout(out):
                trace.main(args)
            self.assertRegex(out.getvalue(), r'7001  48 45 4C 4C 4F +%s ' % (re.escape(flag)))


MODEL1 = os.path.join(ROOT, 'hints', 'model1.hints')


class TestModel1Hints(unittest.TestCase):
    """hints/model1.hints: published names, each with its sources."""

    def test_it_parses_and_every_name_assembles(self):
        h = hints.load(MODEL1)
        self.assertGreaterEqual(len(h.labels), 28)
        self.assertGreaterEqual(len(h.vars), 56)
        self.assertEqual(sorted({**h.labels, **h.vars}), sorted(h.comments))

    def test_every_label_cites_a_source(self):
        keys = ('L2 ', 'M3 ', 'MP ', 'RRD ', 'FV ', 'SAMS ')
        with open(MODEL1) as f:
            for line in f:
                if line.startswith(('label', 'var')):
                    cite = line.split(';', 1)[1] if ';' in line else ''
                    self.assertTrue(any(k in cite for k in keys), line)

    def test_a_program_that_calls_the_entry_points(self):
        segs, entry, _ = build('ST: CALL 0049H\n CALL 0033H\n JP 1A19H')
        res = trace.trace(segs, [entry], hints.load(MODEL1))
        text = trace.source(res)
        for want in ('CALL KBWAIT', 'CALL VDCHAR', 'JP READY',
                     'VDCHAR   EQU 0033H ; display the character in A'):
            self.assertIn(want, text)
        self.assertNotIn('RESET', text)          # an EQU only for what is used
        round_trips(self, res, segs)

    def test_the_two_restarts(self):
        # RST 08H checks the byte after it and returns past it; RST 0
        # restarts the machine, so what follows it is not reached; a CALL
        # 0000H is a placeholder and falls through
        segs, entry, _ = build("ST: RST 8\n DM ','\n RET\nX: RST 0\n DM 'NO'\n"
                               "Y: CALL 0\n RET")
        res = trace.trace(segs, [entry, 0x7003, 0x7006], hints.load(MODEL1))
        self.assertEqual(bytemap(res, segs), 'CDCC..CCCC')
        round_trips(self, res, segs)

    def test_ready_never_returns(self):
        # a CALL to READY (1A19H) is a way back to BASIC: what follows it
        # is not reached; a JP there ends its path as any jump does
        segs, entry, _ = build("ST: CALL 1A19H\n DM 'NO'\nX: JP 1A19H\n DB 1")
        res = trace.trace(segs, [entry, 0x7005], hints.load(MODEL1))
        self.assertEqual(bytemap(res, segs), 'CCC..CCC.')
        self.assertIn('[never returns]', ' '.join(res.steps))
        round_trips(self, res, segs)

    def test_a_program_that_uses_the_ram_locations(self):
        segs, entry, _ = build('ST: LD HL,(4020H)\n LD (409CH),A\n'
                               ' LD HL,4020H\n LD (40F2H),A\n RET')
        res = trace.trace(segs, [entry], hints.load(MODEL1))
        text = trace.source(res)
        for want in ('LD HL,(CCRPOS)', 'LD (DTF),A', 'LD HL,4020H',
                     'LD (ERRFLG),A',
                     'CCRPOS   EQU 4020H ; cursor address in video memory'):
            self.assertIn(want, text)
        self.assertNotIn('VIDEO', text)          # an EQU only for what is used
        round_trips(self, res, segs)


def _span(segs):
    org, data = segs[0]
    return org, len(data)


_TMP = []


def _tmp():
    import tempfile
    if not _TMP:
        d = tempfile.TemporaryDirectory()
        _TMP.append(d)
    return _TMP[0].name


class _quiet:
    def __enter__(self):
        self.err = sys.stderr
        sys.stderr = io.StringIO()

    def __exit__(self, *a):
        sys.stderr = self.err


if __name__ == '__main__':
    unittest.main()
