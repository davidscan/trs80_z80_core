"""tools/usr_sweep.py and tools/usr_pty_sweep.py count THIS run's protocol
log.  The interpreter starts the core at the first USR call, so a listing
that never reaches one leaves no log; the one a previous sweep left under
the same name must not be read in its place (the 2026-09-19 audit, H-22).
No corpus and no interpreter are needed: the runs are stood in for."""

import os
import stat
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools import usr_sweep, usr_pty_sweep   # noqa: E402

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
            usr_sweep.run = lambda path, z80: dict(rc=0, timeout=False, out='HELLO\n', err='', secs=0.0)
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
               'TRS80_MHZ': '1.77', 'TRS80_MANFILE': '/tmp/man.txt'}

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


if __name__ == '__main__':
    unittest.main()
