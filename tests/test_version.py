"""The core names its own version (the 2026-09-30 audit): HEAD
past a release and the release itself were indistinguishable to a user
or a bug report, since the handshake says only name and proto."""
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from z80 import version                                       # noqa: E402
from z80.coprocess import NAME, PROTO                         # noqa: E402


def git(*args, cwd=ROOT):
    return subprocess.run(['git', '-C', cwd] + list(args), capture_output=True, text=True)


class TestVersion(unittest.TestCase):

    def test_core_py_prints_it_without_waiting_for_hello(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, 'core.py'), '--version'],
                           stdin=subprocess.PIPE, capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith('%s %s' % (NAME, version.VERSION)), r.stdout)
        self.assertTrue(r.stdout.rstrip().endswith('protocol %s' % PROTO), r.stdout)

    def test_every_z80_command_line_has_it(self):
        from z80 import asm, disasm, run, trace
        for mod in (asm, disasm, run, trace):
            with self.subTest(mod.__name__):
                out = io.StringIO()
                with redirect_stdout(out), self.assertRaises(SystemExit) as e:
                    mod.main(['--version'])
                self.assertEqual(e.exception.code, 0)
                self.assertIn('%s %s' % (NAME, version.VERSION), out.getvalue())

    def test_version_is_the_latest_release_tag(self):
        """VERSION is bumped by the release commit: a checkout's newest tag
        reachable from HEAD must be it (CI fetches the tags for this)."""
        r = git('describe', '--tags', '--abbrev=0')
        if r.returncode:
            self.skipTest('no tags in this checkout')
        self.assertEqual(r.stdout.strip(), version.VERSION)

    def test_the_build_is_described_only_in_its_own_checkout(self):
        with tempfile.TemporaryDirectory() as d:
            d = os.path.realpath(d)
            for args in (['init', '-q'], ['-c', 'user.name=t', '-c', 'user.email=t@t',
                                          'commit', '-q', '--allow-empty', '-m', 'x'],
                         ['tag', 'v9.9']):
                self.assertEqual(git(*args, cwd=d).returncode, 0)
            sub = os.path.join(d, 'unpacked')
            os.makedirs(sub)
            saved = version.ROOT
            try:
                version.ROOT = d
                self.assertEqual(version.build_id(), 'v9.9')
                version.ROOT = sub          # a release unpacked inside another repository
                self.assertEqual(version.build_id(), '')
                self.assertNotIn('build', version.version_text())
            finally:
                version.ROOT = saved


if __name__ == '__main__':
    unittest.main()
