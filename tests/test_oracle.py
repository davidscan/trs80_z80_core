"""The dynamic extraction oracle -- FINDING 7's escalation path.

The oracle drives the companion interpreter (../trs80basic since the
2026-08-28 split), so most of what can go wrong here is a mismatch with
interpreter source that has moved underneath us.
The patch-point test is the important one: it fails loudly the moment
an instrumentation anchor stops matching, rather than silently
producing an uninstrumented build whose measurements are all zero.

Tests that need the interpreter repo or gawk skip cleanly when they are
absent, the same pattern the anchor tests use for the local-only
corpus sibling.
"""

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phasea import oracle                                     # noqa: E402

HAVE_INTERP = os.path.isdir(oracle.SRC)
HAVE_GAWK = subprocess.run(['which', 'gawk'],
                           capture_output=True).returncode == 0


class TestRunGrouping(unittest.TestCase):
    """(addr, byte) log -> contiguous payload runs."""

    def test_contiguous_run(self):
        pokes = [(100, 1), (101, 2), (102, 3), (103, 4)]
        self.assertEqual(oracle.runs_from_pokes(pokes),
                         [(100, bytes([1, 2, 3, 4]))])

    def test_gap_splits_runs(self):
        pokes = [(100, 1), (101, 2), (102, 3), (103, 4),
                 (200, 9), (201, 9), (202, 9), (203, 9)]
        self.assertEqual(oracle.runs_from_pokes(pokes),
                         [(100, bytes([1, 2, 3, 4])), (200, bytes([9] * 4))])

    def test_last_write_wins(self):
        """A loader that patches a byte after depositing it -- the whole
        reason the oracle sees things static extraction cannot."""
        pokes = [(10, 0), (11, 0), (12, 0), (13, 0), (11, 0x14)]
        self.assertEqual(oracle.runs_from_pokes(pokes),
                         [(10, bytes([0, 0x14, 0, 0]))])

    def test_short_runs_are_dropped(self):
        self.assertEqual(oracle.runs_from_pokes([(5, 1), (6, 2)]), [])

    def test_empty(self):
        self.assertEqual(oracle.runs_from_pokes([]), [])


class TestCompareTiering(unittest.TestCase):
    """Oracle output vs static ground truth.

    The criterion is deliberately NOT byte equality: a loader deposits
    DATA literals and then pokes runtime values into the operands
    before calling USR. quest_2.bas ships LD H,00H / LD L,00H / LD C,00H
    and pokes pitch 20 and duration 50 in. Byte-inequality there is the
    oracle being right.
    """

    def test_exact(self):
        d = bytes(range(20))
        self.assertEqual(oracle.compare(d, d, 100, 100), 'exact')

    def test_contained_in_a_longer_run(self):
        want = bytes(range(10))
        got = bytes(range(20))
        self.assertEqual(oracle.compare(want, got, 105, 100), 'contradiction')
        self.assertEqual(oracle.compare(want, got, 100, 100), 'exact')

    def test_runtime_patched_operands_are_agreement(self):
        want = bytes([0x26, 0x00, 0x2E, 0x00, 0x0E, 0x00] + [1] * 26)
        got = bytes([0x26, 0x14, 0x2E, 0x01, 0x0E, 0x32] + [1] * 26)
        self.assertEqual(oracle.compare(want, got, 0, 0), 'patched')

    def test_wholesale_difference_is_a_contradiction(self):
        want = bytes([1] * 40)
        got = bytes([2] * 40)
        self.assertEqual(oracle.compare(want, got, 0, 0), 'contradiction')

    def test_a_tiny_payload_is_not_agreement_by_size(self):
        """Four bytes, all different: the old floor of 4 called it patched."""
        want = bytes([0xCD, 0x7F, 0x0A, 0xC9])          # CALL 0A7FH / RET
        got = bytes([0x3E, 0x01, 0xD3, 0xFF])           # LD A,1 / OUT (FFH),A
        self.assertEqual(oracle.compare(want, got, 0, 0), 'contradiction')

    def test_changed_opcodes_in_a_short_routine_are_a_contradiction(self):
        """Four wrong opcode bytes in 27: the size of the sound routines."""
        want = bytes([0x3E, 0x01, 0xD3, 0xFF, 0x06, 0x20, 0x10, 0xFE] * 3
                     + [0x00, 0x00, 0xC9])
        got = bytearray(want)
        for i in (0, 2, 4, 6):
            got[i] ^= 0x40
        self.assertEqual(oracle.compare(want, bytes(got), 0, 0),
                         'contradiction')

    def test_relocated_addresses_are_agreement(self):
        """dskindex.bas: every (nn) high byte moved, no opcode touched."""
        want = bytes([0x21, 0x00, 0xA2, 0x22, 0x10, 0xA2, 0xC3, 0x20, 0xA2])
        got = bytes([0x21, 0x00, 0xE2, 0x22, 0x10, 0xE2, 0xC3, 0x20, 0xE2])
        self.assertEqual(oracle.compare(want, got, 0, 0), 'patched')

    def test_one_poked_opcode_in_a_long_routine_is_agreement(self):
        """freqanal.bas pokes a RET over one LD A,(nn) in 193 bytes."""
        want = bytes([0x3A, 0x00, 0x7F] * 64 + [0xC9])
        got = bytearray(want)
        got[126] = 0xC9
        self.assertEqual(oracle.compare(want, bytes(got), 0, 0), 'patched')

    def test_operand_offsets(self):
        # LD A,n / LD HL,nn / JR e / BIT 0,(IX+d) / RET
        code = bytes([0x3E, 1, 0x21, 2, 3, 0x18, 4, 0xDD, 0xCB, 5, 0x46, 0xC9])
        self.assertEqual(oracle.operand_offsets(code), {1, 3, 4, 6, 9})

    def test_run_too_short_is_a_contradiction(self):
        self.assertEqual(oracle.compare(bytes(30), bytes(10), 0, 0),
                         'contradiction')


class TestRegionDiscrimination(unittest.TestCase):
    """FINDING 5's not-every-POKE-loop-is-a-loader, applied dynamically."""

    def test_video_fill_is_screen_data(self):
        self.assertEqual(oracle.region_of(15360, bytes(1024)), 'screen-data')

    def test_printer_window_is_a_device_stream(self):
        self.assertEqual(oracle.region_of(14312, bytes(2)), 'device-stream')

    def test_ordinary_ram_is_candidate_ml(self):
        self.assertEqual(oracle.region_of(32740, bytes(27)), 'candidate-ml')

    def test_the_static_discriminations_hold_dynamically(self):
        # a run the static extractor calls a device stream is one here
        # too: the whole printer window, the keyboard matrix, anything
        # below 4000H (the 2026-09-19 audit, L-62)
        self.assertEqual(oracle.region_of(0x37E0, bytes(8)), 'device-stream')
        self.assertEqual(oracle.region_of(0x3800, bytes(8)), 'device-stream')
        self.assertEqual(oracle.region_of(0x3000, bytes(64)), 'device-stream')
        self.assertEqual(oracle.region_of(0x0100, bytes(16)), 'device-stream')
        self.assertEqual(oracle.region_of(0x3FF0, bytes(32)), 'candidate-ml')
        self.assertEqual(oracle.region_of(16554, bytes(3)), 'device-stream')


class TestHangAnalysis(unittest.TestCase):
    """Whether a USR result gates a spin cycle, read from its source lines."""

    def test_a_long_name_is_its_first_two_characters(self):
        """KEY=USR(0) assigns KE -- not the EY an unanchored pattern finds."""
        self.assertEqual(oracle.usr_gating(['KEY=USR(0):IF KEY=0 THEN 10']),
                         ({'KE'}, True))
        self.assertEqual(oracle.usr_gating(['KEY=USR(0)', 'IF KEPT=0 THEN 10']),
                         ({'KE'}, True))

    def test_usr_called_in_the_condition_gates(self):
        self.assertEqual(oracle.usr_gating(['IF USR(0)=0 THEN 10']),
                         (set(), True))

    def test_crunched_lines_read_like_spaced_ones(self):
        self.assertEqual(oracle.usr_gating(['X=USR(0):IFX=0THEN10']),
                         ({'X'}, True))
        self.assertEqual(oracle.usr_gating(['IFUSR(0)=0GOTO10']), (set(), True))

    def test_an_apostrophe_in_a_string_is_text(self):
        line = 'X=USR(0):PRINT "DON\'T MOVE":IF X=0 THEN 10'
        self.assertEqual(oracle.strip_basic_comments(line), line)
        self.assertEqual(oracle.usr_gating([line]), ({'X'}, True))

    def test_a_commented_out_if_gates_nothing(self):
        """liongrp2.bas: the IF is inside a REM, the loop is unconditional."""
        cycle = ["' X$=INKEY$:IF X$=\"\"110", 'X=USR(0): GOTO 110']
        self.assertEqual(oracle.strip_basic_comments(cycle[0]), '')
        self.assertEqual(oracle.usr_gating(cycle), ({'X'}, False))

    def test_other_variables_and_strings_do_not_gate(self):
        self.assertEqual(oracle.usr_gating(['X=USR(0)', 'IF Y=0 THEN 10']),
                         ({'X'}, False))
        self.assertEqual(oracle.usr_gating(['X=USR(0):IF X$="" THEN 10']),
                         ({'X'}, False))
        self.assertEqual(oracle.usr_gating(['X=USR(0):IF A$="X" THEN 10']),
                         ({'X'}, False))

    def test_an_assignment_behind_then_counts(self):
        self.assertEqual(
            oracle.usr_gating(['IF A=1 THEN X=USR(0) ELSE 30', 'IF X>2 GOTO 10']),
            ({'X'}, True))

    def test_defusr_is_not_a_call(self):
        self.assertEqual(oracle.usr_gating(['DEFUSR=32000:GOTO 10']),
                         (set(), False))


@unittest.skipUnless(HAVE_INTERP, 'interpreter sources not present')
class TestPatchPoints(unittest.TestCase):
    """Every instrumentation anchor must still match the interpreter EXACTLY.

    This is the test that earns its keep. If the interpreter's st_poke,
    dopeek, USR stub, or exec loop is edited, the anchor stops matching
    and the build aborts -- instead of quietly producing an interpreter
    with no instrumentation, whose every measurement would read zero
    and look like a finding.
    """

    def test_each_patch_matches_exactly_once(self):
        for module, old, _new in oracle.PATCHES:
            with open(os.path.join(oracle.SRC, module)) as f:
                text = f.read()
            self.assertEqual(
                text.count(old), 1,
                'patch anchor in %s no longer matches exactly once -- the '
                'interpreter source moved; re-verify before trusting any oracle '
                'output' % module)

    def test_every_patch_is_env_gated(self):
        """Nothing may execute unless a TRS80_* var asks for it.

        Textual check only -- the real guarantee that instrumentation
        does not perturb the measurement is the behavioural one in
        TestInstrumentedBuild.test_uninstrumented_behaviour_is_unchanged,
        which diffs this build against the shipped interpreter.
        """
        gates = ('TRS80_POKELOG', 'TRS80_CASSETTE', 'TRS80_LINELOG')
        for module, old, new in oracle.PATCHES:
            self.assertGreater(len(new), len(old),
                               '%s: patch removes code' % module)
            added = [ln for ln in new.splitlines()
                     if ln not in old.splitlines()]
            self.assertTrue(added, '%s: patch adds nothing' % module)
            self.assertTrue(
                any(g in new for g in gates),
                '%s: patch is not gated on an environment variable' % module)

    def test_no_patch_touches_the_shipped_interpreter(self):
        """The interpreter repo is data here, never a build target."""
        shipped = os.path.join(oracle.INTERP_REPO, 'trs80basic.awk')
        if not os.path.exists(shipped):
            self.skipTest('trs80basic has no built interpreter')
        with open(shipped) as f:
            text = f.read()
        for gate in ('TRS80_POKELOG', 'TRS80_CASSETTE', 'TRS80_LINELOG'):
            self.assertNotIn(gate, text,
                             'instrumentation leaked into the interpreter repo')


@unittest.skipUnless(HAVE_INTERP and HAVE_GAWK, 'needs interpreter sources + gawk')
class TestInstrumentedBuild(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.interp = oracle.build(force=True)

    def test_build_produces_an_interpreter(self):
        self.assertTrue(os.path.getsize(self.interp) > 100000)

    def test_uninstrumented_behaviour_is_unchanged(self):
        """The instrumentation must not perturb what it measures."""
        prog = os.path.join(oracle.OUT, 'selftest.bas')
        with open(prog, 'w') as f:
            f.write('10 PRINT "HELLO"\n20 PRINT 6*7\n')
        env = {k: v for k, v in os.environ.items()
               if k not in ('TRS80_POKELOG', 'TRS80_CASSETTE', 'TRS80_LINELOG')}
        mine = subprocess.run(['gawk', '-b', '-f', self.interp, '--', prog],
                              capture_output=True, env=env)
        theirs = subprocess.run(
            ['gawk', '-b', '-f', os.path.join(oracle.INTERP_REPO, 'trs80basic.awk'),
             '--', prog], capture_output=True, env=env)
        self.assertEqual(mine.stdout, theirs.stdout)
        self.assertEqual(mine.returncode, theirs.returncode)

    def test_poke_log_records_what_a_loader_deposits(self):
        prog = os.path.join(oracle.OUT, 'loader.bas')
        with open(prog, 'w') as f:
            f.write('10 FOR I=0 TO 3:READ D:POKE 32000+I,D:NEXT\n'
                    '20 DATA 62,1,211,255\n')
        got = oracle.run_listing(prog, timeout=20)
        self.assertEqual(oracle.runs_from_pokes(got['pokes']),
                         [(32000, bytes([62, 1, 211, 255]))])

    def test_high_bytes_in_a_listing_survive_a_utf8_locale(self):
        """gawk runs with -b: a byte above 127 is itself, not 3FH.

        String packing is the corpus's dominant loader idiom, and its
        bytes are mostly above 127. Without -b a UTF-8 locale reads each
        of them as '?', and the interpreter's warning never reaches the
        report (run_listing keeps only the '?XX ERROR' lines).
        """
        have = subprocess.run(['locale', '-a'], capture_output=True,
                              text=True).stdout.split()
        utf8 = [n for n in ('en_US.UTF-8', 'C.UTF-8', 'en_US.utf8', 'C.utf8')
                if n in have]
        if not utf8:
            self.skipTest('no UTF-8 locale installed')
        prog = os.path.join(oracle.OUT, 'highbytes.bas')
        with open(prog, 'wb') as f:
            f.write(b'10 A$="\xcd\xc9\x80\xff"\n'
                    b'20 FOR I=1 TO 4:POKE 31999+I,ASC(MID$(A$,I,1)):NEXT\n')
        saved = {k: os.environ.get(k) for k in ('LC_ALL', 'LANG')}
        os.environ['LC_ALL'] = os.environ['LANG'] = utf8[0]
        try:
            got = oracle.run_listing(prog, timeout=20)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        self.assertEqual(oracle.runs_from_pokes(got['pokes']),
                         [(32000, bytes([0xCD, 0xC9, 0x80, 0xFF]))])

    def test_a_listing_that_saves_writes_nothing_beside_itself(self):
        """The corpus is only read: a run's files land in a scratch cwd."""
        d = os.path.join(oracle.OUT, 'readonly')
        os.makedirs(d, exist_ok=True)
        for n in os.listdir(d):
            os.remove(os.path.join(d, n))
        prog = os.path.join(d, 'saver.bas')
        with open(prog, 'w') as f:
            f.write('10 OPEN "O",1,"SCORES.DAT":PRINT#1,7:CLOSE\n'
                    '20 SAVE "COPY.BAS"\n'
                    '30 FOR I=0 TO 3:POKE 32000+I,9:NEXT\n')
        got = oracle.run_listing(prog, timeout=20)
        self.assertEqual(got['rc'], 0, got['reason'])
        self.assertEqual(oracle.runs_from_pokes(got['pokes']),
                         [(32000, bytes([9] * 4))])
        self.assertEqual(sorted(os.listdir(d)), ['saver.bas'])
        oracle.analyse_hang(prog, timeout=20)
        self.assertEqual(sorted(os.listdir(d)), ['saver.bas'])

    def test_a_one_line_spin_leaves_its_trace(self):
        """The line log is flushed: the timeout kill must not take it.

        A line is logged when it changes, so a one-line spin writes a
        single short line that never fills gawk's buffer.
        """
        prog = os.path.join(oracle.OUT, 'spin1.bas')
        with open(prog, 'w') as f:
            f.write('10 X=USR(0):GOTO 10\n')
        got = oracle.analyse_hang(prog, timeout=2)
        self.assertEqual(got['cycle'], ['10'])
        self.assertEqual(got['verdict'], 'unconditional-loop')

    def test_interpreter_answers_the_dos_probe_with_a_ret(self):
        """PEEK(16396) must be 201 -- FINDING 16, now shipped upstream.

        This began life as a gated COUNTERFACTUAL in the oracle: the
        interpreter answered 255 (absent RAM), which sent every listing using
        the am-I-under-Disk-BASIC probe down its DISK branch into CMD.
        The interpreter shipped 201 on 2026-08-14, so the counterfactual is
        retired and this is a cross-repo regression guard instead -- if
        the probe ever goes back to 255, 88 rescued listings quietly
        take the wrong branch again and this test says so.
        """
        prog = os.path.join(oracle.OUT, 'probe.bas')
        with open(prog, 'w') as f:
            f.write('10 POKE 32000,PEEK(16396)\n'
                    '20 POKE 32001,PEEK(16396)\n'
                    '30 POKE 32002,PEEK(16396)\n'
                    '40 POKE 32003,PEEK(16396)\n')
        got = oracle.run_listing(prog, timeout=20)
        self.assertEqual(oracle.runs_from_pokes(got['pokes']),
                         [(32000, bytes([201] * 4))])

    def test_interpreter_accepts_the_spaced_usr_call_form(self):
        """X=USR 0(n) must parse -- FINDING 17, now shipped upstream.

        The loader POKEs come BEFORE the call on purpose: run_listing
        truncates the log at the first USR marker, which is the whole
        point of the oracle, so anything poked afterwards is invisible.
        """
        prog = os.path.join(oracle.OUT, 'spacedusr.bas')
        with open(prog, 'w') as f:
            f.write('10 DEF USR 0=&H7D00\n'
                    '20 FOR I=0 TO 3:POKE 32000+I,9:NEXT\n'
                    '30 V=USR 0(7)\n'
                    '40 END\n')
        got = oracle.run_listing(prog, timeout=20)
        self.assertEqual(got['rc'], 0, 'spaced USR call did not parse')
        self.assertTrue(got['usr_seen'], 'never reached the USR call')
        self.assertEqual(oracle.runs_from_pokes(got['pokes']),
                         [(32000, bytes([9] * 4))])


class TestTheEnvironmentDoesNotLeakIn(unittest.TestCase):
    """The oracle's measurement must not depend on the caller's shell.

    It inherited the environment whole, so TRS80_USR=strict turned every
    un-executed USR into ?FC, a TRS80_Z80 put a real core behind calls the
    oracle believes are stubbed, and TRS80_SOUND started a player -- the
    same corpus gave different numbers to different people (the 2026-09-19
    audit, L-64).
    """

    def test_the_variables_that_would_change_a_measurement_are_gone(self):
        keep = dict(os.environ)
        try:
            os.environ.update({
                'TRS80_USR': 'strict',
                'TRS80_Z80': 'python3 /nonexistent/core.py',
                'TRS80_SOUND': 'auto',
                'TRS80_USR_TRACE': '2',
                'TRS80_EXT': '1',
                'TRS80_PRINTER': '/tmp/lp',
            })
            env = oracle.base_env(TRS80_POKELOG='/tmp/x')
        finally:
            os.environ.clear()
            os.environ.update(keep)
        self.assertEqual(env['TRS80_Z80'], '')        # the stub, always
        self.assertEqual(env['TRS80_DUMB'], '1')
        self.assertEqual(env['TRS80_POKELOG'], '/tmp/x')
        for v in ('TRS80_USR', 'TRS80_SOUND', 'TRS80_USR_TRACE',
                  'TRS80_EXT', 'TRS80_PRINTER'):
            self.assertNotIn(v, env, v)

    def test_a_run_under_a_hostile_environment_measures_the_same(self):
        """The whole point, end to end: one listing, two shells."""
        src = b'10 DEFUSR=32000:X=USR(1)\n20 PRINT "DONE"\n'
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'u.bas')
            with open(p, 'wb') as f:
                f.write(src)
            clean = oracle.run_listing(p)
            keep = dict(os.environ)
            try:
                os.environ['TRS80_USR'] = 'strict'
                os.environ['TRS80_SOUND'] = 'auto'
                hostile = oracle.run_listing(p)
            finally:
                os.environ.clear()
                os.environ.update(keep)
        self.assertEqual(clean['rc'], hostile['rc'])
        self.assertEqual(clean['usr_seen'], hostile['usr_seen'])


if __name__ == '__main__':
    unittest.main()
