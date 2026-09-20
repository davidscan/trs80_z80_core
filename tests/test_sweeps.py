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


if __name__ == '__main__':
    unittest.main()
