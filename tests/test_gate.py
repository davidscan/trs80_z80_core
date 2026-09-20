"""phasea.sweep's anchor gate: counts are published only when the anchor
suites RAN and passed. unittest exits 0 for `OK (skipped=14)`, which is
what a checkout without the corpus sibling gives, so exit status alone
is not the gate.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phasea import sweep                                       # noqa: E402

PASSES = 'import unittest\nclass T(unittest.TestCase):\n    def test_a(self): pass\n'
SKIPS = ('import unittest\nclass T(unittest.TestCase):\n'
         '    def test_a(self): pass\n'
         '    @unittest.skip("anchor absent")\n    def test_b(self): pass\n')
FAILS = 'import unittest\nclass T(unittest.TestCase):\n    def test_a(self): self.fail()\n'
EMPTY = 'import unittest\n'


class TestAnchorGate(unittest.TestCase):

    def gate(self, text):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, 'suite_x.py'), 'w') as f:
                f.write(text)
            return sweep.gate_check(suites=['suite_x'], cwd=d)

    def test_a_passing_suite_opens_the_gate(self):
        ok, summary = self.gate(PASSES)
        self.assertTrue(ok, summary)

    def test_a_skipped_anchor_closes_the_gate(self):
        ok, summary = self.gate(SKIPS)
        self.assertIn('skipped=1', summary)
        self.assertFalse(ok)

    def test_a_failure_closes_the_gate(self):
        self.assertFalse(self.gate(FAILS)[0])

    def test_no_tests_at_all_closes_the_gate(self):
        self.assertFalse(self.gate(EMPTY)[0])

    def test_the_gate_names_the_three_anchor_suites(self):
        self.assertEqual(sweep.ANCHOR_SUITES,
                         ('tests.test_table', 'tests.test_anchors',
                          'tests.test_extract'))


if __name__ == '__main__':
    unittest.main()
