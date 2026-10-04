"""PROTOCOL.md agrees with the code, and the interpreter beside this repo.

The 2026-09-30 audit (XM-4a) found that nothing opened PROTOCOL.md: a
stale `proto=` in either copy, or a mirror that drifted from trs80basic's,
passed every suite.  These tests read it.

  * the version the handshake lines state is this core's PROTO;
  * with trs80basic checked out beside this repo, its PROTOCOL.md is
    byte-identical to this mirror and its Z80PROTO is the same number;
  * Z80_INTERP_REQUIRE=1 (CI sets it) makes the interpreter's absence a
    FAILURE, so the tests that need it (test_oracle's anchors, test_asm's
    BASIC loader) cannot skip unseen (XM-3).
"""

import os
import re
import shutil
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from z80 import coprocess                                     # noqa: E402

DOC = os.path.join(ROOT, 'PROTOCOL.md')
INTERP_REPO = os.path.join(os.path.dirname(ROOT), 'trs80basic')
REQUIRE = os.environ.get('Z80_INTERP_REQUIRE') == '1'


def doc_versions(text):
    hello = re.findall(r'^interpreter -> core   HELLO proto=(\d+) ', text, re.M)
    reply = re.findall(r'^core -> interpreter   Z80 proto=(\d+) ', text, re.M)
    return hello, reply


class TestProtocolDoc(unittest.TestCase):

    def test_the_handshake_states_this_cores_version(self):
        with open(DOC) as f:
            hello, reply = doc_versions(f.read())
        self.assertEqual(hello, [coprocess.PROTO], 'HELLO line vs PROTO')
        self.assertEqual(reply, [coprocess.PROTO], 'Z80 reply line vs PROTO')


class TestTheInterpreterBeside(unittest.TestCase):

    def setUp(self):
        if not os.path.isdir(INTERP_REPO):
            if REQUIRE:
                self.fail('Z80_INTERP_REQUIRE=1 and no trs80basic at %s' % INTERP_REPO)
            self.skipTest('no trs80basic beside this repo')

    def test_the_mirror_is_byte_identical(self):
        with open(DOC, 'rb') as f:
            mine = f.read()
        with open(os.path.join(INTERP_REPO, 'PROTOCOL.md'), 'rb') as f:
            theirs = f.read()
        self.assertTrue(mine == theirs,
                        "PROTOCOL.md differs from trs80basic's; the owner's copy wins")

    def test_the_interpreter_speaks_the_same_version(self):
        with open(os.path.join(INTERP_REPO, 'src', 'p77_z80.awk')) as f:
            m = re.search(r'^\s*Z80PROTO = (\d+)$', f.read(), re.M)
        self.assertIsNotNone(m, 'no Z80PROTO in p77_z80.awk')
        self.assertEqual(m.group(1), coprocess.PROTO)

    def test_what_the_skipping_tests_need_is_here(self):
        """Under Z80_INTERP_REQUIRE the oracle and loader tests must run:
        their skip conditions are the interpreter's sources, its launcher
        and gawk."""
        if not REQUIRE:
            self.skipTest('Z80_INTERP_REQUIRE not set')
        self.assertTrue(os.path.isdir(os.path.join(INTERP_REPO, 'src')))
        self.assertTrue(os.access(os.path.join(INTERP_REPO, 'basic'), os.X_OK))
        self.assertIsNotNone(shutil.which('gawk'), 'gawk not on PATH')


if __name__ == '__main__':
    unittest.main()
