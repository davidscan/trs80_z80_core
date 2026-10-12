"""tools/usr_sweep.py and tools/usr_pty_sweep.py count THIS run's protocol
log.  The interpreter starts the core at the first USR call, so a listing
that never reaches one leaves no log; the one a previous sweep left under
the same name must not be read in its place (the 2026-09-19 audit, H-22).
No corpus and no interpreter are needed: the runs are stood in for."""

import contextlib
import hashlib
import io
import os
import stat
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools import usr_sweep, usr_pty_sweep   # noqa: E402
from phasea import sweep                     # noqa: E402

STALE_IN = 'HELLO proto=1\nCALL gen=1 full=1 slot=0 entry=32000 arg=0 sp=1 himem=1 ramtop=1 runs=0\nGO\n'
STALE_OUT = 'Z80 proto=1\nERR rom called 0033H, no ROM here\n'


def seed(runs, tag):
    os.makedirs(runs)
    with open(os.path.join(runs, tag + '.in'), 'w') as f:
        f.write(STALE_IN)
    with open(os.path.join(runs, tag + '.out'), 'w') as f:
        f.write(STALE_OUT)


class TestStaleLogs(unittest.TestCase):
    def test_batch_sweep_does_not_count_an_earlier_sweeps_log(self):
        with tempfile.TemporaryDirectory() as d:
            saved = (usr_sweep.CORPUS, usr_sweep.RUNS, usr_sweep.run)
            usr_sweep.CORPUS, usr_sweep.RUNS = os.path.join(d, 'corpus'), os.path.join(d, 'runs')
            # a run that never reaches USR: the core is not started, nothing is logged
            usr_sweep.run = lambda path, z80, cwd: dict(rc=0, timeout=False, out='HELLO\n', err='', secs=0.0)
            try:
                seed(usr_sweep.RUNS, 'runnable__x.bas')
                r = usr_sweep.one(os.path.join(usr_sweep.CORPUS, 'runnable', 'x.bas'))
            finally:
                usr_sweep.CORPUS, usr_sweep.RUNS, usr_sweep.run = saved
        self.assertEqual((r['cls'], r['calls'], r['errs']), ('no-usr-reached', 0, []))

    def test_pty_sweep_does_not_count_an_earlier_sweeps_log(self):
        with tempfile.TemporaryDirectory() as d:
            fake = os.path.join(d, 'basic')             # an interpreter that leaves at once
            with open(fake, 'w') as f:
                f.write('#!/bin/sh\nexit 0\n')
            os.chmod(fake, os.stat(fake).st_mode | stat.S_IXUSR)
            m = usr_pty_sweep
            saved = (m.CORPUS, m.RUNS, m.CWD, m.BASIC, m.SPAN)
            m.CORPUS, m.RUNS, m.CWD, m.BASIC, m.SPAN = (os.path.join(d, 'corpus'), os.path.join(d, 'runs'),
                                                        d, d, 0.0)
            try:
                seed(m.RUNS, 'runnable__x.bas')
                r = m.drive(os.path.join(m.CORPUS, 'runnable', 'x.bas'))
            finally:
                m.CORPUS, m.RUNS, m.CWD, m.BASIC, m.SPAN = saved
        self.assertEqual((r['cls'], r['calls'], r['errs']), ('not-reached', 0, []))


class TestPtyLaunch(unittest.TestCase):

    def test_pty_sweep_child_that_cannot_exec_ends_there(self):
        """No interpreter at BASIC: the forked child must _exit, not return
        into the sweep as a second driver, and the run is not 'not-reached'."""
        with tempfile.TemporaryDirectory() as d:
            m = usr_pty_sweep
            saved = (m.CORPUS, m.RUNS, m.CWD, m.BASIC, m.SPAN)
            m.CORPUS, m.RUNS, m.CWD, m.BASIC, m.SPAN = (os.path.join(d, 'corpus'), os.path.join(d, 'runs'),
                                                        d, os.path.join(d, 'nowhere'), 0.0)
            parent = os.getpid()
            try:
                os.makedirs(m.RUNS)
                r = m.drive(os.path.join(m.CORPUS, 'runnable', 'x.bas'))
            finally:
                if os.getpid() != parent:       # the old code: the child is back
                    os._exit(3)
                m.CORPUS, m.RUNS, m.CWD, m.BASIC, m.SPAN = saved
        self.assertEqual(r['cls'], 'launch-failed')


class TestTheSweepEnvironmentIsItsOwn(unittest.TestCase):
    """A sweep is a measurement, so the caller's shell must not reach it.

    Both sweeps inherited the environment whole, so a TRS80_USR=strict
    left over from a debugging session turned every un-executed USR into
    ?FC, TRS80_SOUND started a player per listing, and TRS80_PRINTER
    collected every LPRINT in the corpus into one file (the 2026-09-19
    audit, L-65).
    """

    HOSTILE = {'TRS80_USR': 'strict', 'TRS80_USR_TRACE': '2',
               'TRS80_SOUND': 'auto', 'TRS80_SOUND_WAV': '/tmp/w.wav',
               'TRS80_PRINTER': '/tmp/lp', 'TRS80_EXT': '1',
               'TRS80_MHZ': '1.77', 'TRS80_MANFILE': '/tmp/man.txt',
               # ZL-8's own variable, and one no interpreter has yet: the
               # scrub is categorical, not a list (ZM-5)
               'TRS80_MEMORY': 'host', 'TRS80_NOT_A_KNOB_YET': '1'}

    def envs(self):
        keep = dict(os.environ)
        try:
            os.environ.update(self.HOSTILE)
            return (usr_sweep.sweep_env(TRS80_Z80='c', TRS80_DUMB='1'),
                    usr_pty_sweep.sweep_env(TRS80_Z80='c'))
        finally:
            os.environ.clear()
            os.environ.update(keep)

    def test_nothing_hostile_survives_into_either_sweep(self):
        for env in self.envs():
            for v in self.HOSTILE:
                self.assertNotIn(v, env, v)

    def test_what_the_sweep_sets_itself_is_kept(self):
        a, b = self.envs()
        self.assertEqual(a['TRS80_Z80'], 'c')
        self.assertEqual(a['TRS80_DUMB'], '1')
        self.assertEqual(b['TRS80_Z80'], 'c')
        self.assertEqual(a['LC_ALL'], 'C')

    def test_the_rest_of_the_environment_still_comes_through(self):
        """PATH and HOME are not the sweep's business to remove."""
        for env in self.envs():
            self.assertIn('PATH', env)


class TestEachRunHasAFreshCwd(unittest.TestCase):
    """A file a listing wrote reached the next run under a shared cwd, so
    the stub/core/control comparison measured leftovers (ZL-9; ZM-5: no
    test failed without the fix)."""

    def test_a_run_never_sees_the_last_runs_files(self):
        with tempfile.TemporaryDirectory() as d:
            fake = os.path.join(d, 'basic')
            with open(fake, 'w') as f:
                f.write('#!/bin/sh\n[ -e left ] && echo LEFTOVER\n: > left\n')
            os.chmod(fake, 0o755)
            saved = usr_sweep.BASIC
            usr_sweep.BASIC = fake
            try:
                cwd = os.path.join(d, 'cwd')
                first = usr_sweep.run('x.bas', '', cwd)
                second = usr_sweep.run('x.bas', '', cwd)
            finally:
                usr_sweep.BASIC = saved
        self.assertEqual(first['out'], '')
        self.assertEqual(second['out'], '')


class TestTheSweepSaysHowARunStopped(unittest.TestCase):
    """ZM-8: no-usr-reached hid 194 interpreter error stops, and nothing
    recorded which build or load produced the classes."""

    def test_the_stop_line_skips_diagnostics(self):
        r = dict(err='gawk: warning: x\nUSR STUB: 0 CALLS\n?OV ERROR IN 12\n')
        self.assertEqual(usr_sweep.stop(r), '?OV ERROR IN 12')
        self.assertEqual(usr_sweep.stop(dict(err='')), '')

    def test_an_error_stop_is_its_own_class(self):
        for line in ('?OV ERROR IN 12', '?SN ERROR', '?/0 ERROR IN 5'):
            self.assertTrue(usr_sweep.BASIC_ERROR_RE.match(line), line)
        self.assertFalse(usr_sweep.BASIC_ERROR_RE.match('BREAK IN 20'))

    def test_the_inputs_name_both_builds_and_the_set(self):
        with tempfile.TemporaryDirectory() as d:
            progs = tree(d, ['runnable/usr1.bas'])
            files = [os.path.join(progs, 'runnable/usr1.bas')]
            saved = usr_sweep.CORPUS
            usr_sweep.CORPUS = progs
            try:
                meta = usr_sweep.inputs(files, files)
            finally:
                usr_sweep.CORPUS = saved
            fp = sweep.fingerprint(files, progs)
        for k in ('core', 'interpreter', 'interpreter_version', 'corpus', 'input_set',
                  'listings', 'population', 'timeout_s', 'workers', 'load_start'):
            self.assertIn(k, meta)
        self.assertEqual(meta['input_set'], fp)

    def test_the_pty_sweep_reads_the_new_results_shape(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, 'out', 'usr_sweep')
            os.makedirs(out)
            with open(os.path.join(out, 'results.json'), 'w') as f:
                f.write('{"inputs": {}, "results": [{"file": "runnable/a.bas", "cls": "no-usr-reached"},'
                        ' {"file": "runnable/b.bas", "cls": "err"}]}')
            saved = usr_pty_sweep.HERE, usr_pty_sweep.CORPUS
            usr_pty_sweep.HERE, usr_pty_sweep.CORPUS = d, '/c'
            try:
                pop = usr_pty_sweep.population('no-usr-reached', None)
            finally:
                usr_pty_sweep.HERE, usr_pty_sweep.CORPUS = saved
        self.assertEqual(pop, ['/c/runnable/a.bas'])


def tree(d, names):
    """A stand-in corpus programs/ holding these listings."""
    for n in names:
        path = os.path.join(d, n)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write('10 X=USR(0)\n' if 'usr' in n else '10 PRINT 1\n')
    return d


class TestTheInputSetIsPinned(unittest.TestCase):
    """One stray file in runnable/ moved every published F28 number and
    the sweep printed them with exit 0 (XM-13, the 2026-09-30 audit); a
    tree with no listings gave usr_sweep population 0, DONE, exit 0 and
    an emptied results.json (ZM-11)."""

    NAMES = ['runnable/a.bas', 'runnable/usr1.bas', 'blocked/gfx/usr2.bas']

    def test_the_fingerprint_is_the_shells(self):
        with tempfile.TemporaryDirectory() as d:
            tree(d, self.NAMES)
            paths = [os.path.join(d, n) for n in self.NAMES]
            lines = ''
            for n in sorted(self.NAMES):
                with open(os.path.join(d, n), 'rb') as f:
                    lines += hashlib.sha1(f.read()).hexdigest() + '  ' + n + '\n'
            self.assertEqual(sweep.fingerprint(paths, d),
                             hashlib.sha1(lines.encode()).hexdigest())

    def test_a_stray_file_or_an_empty_tree_is_named(self):
        with tempfile.TemporaryDirectory() as d:
            tree(d, self.NAMES)
            paths = [os.path.join(d, n) for n in self.NAMES]
            pin = (3, sweep.fingerprint(paths, d))
            self.assertIsNone(sweep.input_set_problem(paths, d, pin))
            tree(d, ['runnable/GLOBE.bas'])
            self.assertIn('not the pinned',
                          sweep.input_set_problem(paths + [os.path.join(d, 'runnable/GLOBE.bas')], d, pin))
            self.assertIn('empty', sweep.input_set_problem([], d, pin))

    def test_the_sweep_refuses_a_changed_set(self):
        with tempfile.TemporaryDirectory() as d:
            progs = tree(os.path.join(d, 'programs'), self.NAMES)
            saved = sweep.PROGRAMS, sweep.INPUT_SET
            sweep.PROGRAMS, sweep.INPUT_SET = progs, (3, 'f' * 40)
            out = io.StringIO()
            try:
                with contextlib.redirect_stdout(out):
                    rc = sweep.main(['--skip-gate', '--json', os.path.join(d, 'm.json')])
            finally:
                sweep.PROGRAMS, sweep.INPUT_SET = saved
            self.assertEqual(rc, 2)
            self.assertIn('REFUSING TO PUBLISH COUNTS', out.getvalue())
            self.assertFalse(os.path.exists(os.path.join(d, 'm.json')))

    def run_usr_sweep(self, d, names):
        """usr_sweep.main on a stand-in corpus, with a results.json already
        in place; returns (rc, the output, results.json afterwards)."""
        m = usr_sweep
        saved = m.CORPUS, m.OUT, m.RUNS, m.CWD
        m.CORPUS = tree(os.path.join(d, 'programs'), names)
        os.makedirs(m.CORPUS, exist_ok=True)
        m.OUT = os.path.join(d, 'out')
        m.RUNS, m.CWD = m.OUT + '/runs', m.OUT + '/cwd'
        os.makedirs(m.OUT)
        with open(m.OUT + '/results.json', 'w') as f:
            f.write('[{"file": "earlier"}]')
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                rc = m.main([])
        finally:
            with open(m.OUT + '/results.json') as f:
                kept = f.read()
            m.CORPUS, m.OUT, m.RUNS, m.CWD = saved
        return rc, out.getvalue(), kept

    def test_usr_sweep_refuses_an_empty_population_and_keeps_its_results(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out, kept = self.run_usr_sweep(d, [])
        self.assertEqual(rc, 2)
        self.assertIn('REFUSING', out)
        self.assertNotIn('DONE', out)
        self.assertEqual(kept, '[{"file": "earlier"}]')

    def test_usr_sweep_refuses_a_set_that_is_not_the_pinned_one(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out, kept = self.run_usr_sweep(d, self.NAMES)
        self.assertEqual(rc, 2)
        self.assertIn('not the pinned', out)
        self.assertEqual(kept, '[{"file": "earlier"}]')

    def test_both_sweeps_take_the_extractors_usr_population(self):
        """ZM-9: USR in a DATA keyword table is no USR program; ZM-5: no
        test failed when either sweep's population() took every listing."""
        with tempfile.TemporaryDirectory() as d:
            progs = tree(d, self.NAMES)
            table = os.path.join(progs, 'runnable', 'kwtable.bas')
            with open(table, 'w') as f:
                f.write('10 READ K$\n900 DATA PEEK,POKE,USR,VARPTR\n')
            want = sorted(os.path.join(progs, n) for n in self.NAMES if 'usr' in n)
            files = sorted(os.path.join(progs, n) for n in self.NAMES) + [table]
            self.assertEqual(sorted(usr_sweep.population(files)), want)
            saved = usr_pty_sweep.CORPUS
            usr_pty_sweep.CORPUS = progs
            try:
                self.assertEqual(sorted(usr_pty_sweep.population('all', None)), want)
            finally:
                usr_pty_sweep.CORPUS = saved

    def test_pty_sweep_refuses_an_empty_population(self):
        self.assertIn('empty', usr_pty_sweep.population_problem('no-usr-reached', None, []))
        self.assertIsNone(usr_pty_sweep.population_problem('x', ['a.bas'], ['a']))


if __name__ == '__main__':
    unittest.main()
