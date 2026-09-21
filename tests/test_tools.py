"""The small tools beside the core: render_frames and tick_probe.

Both are scripts rather than modules -- render_frames reads sys.argv at
import -- so they are driven as subprocesses, the way they are used.
"""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


LOG = """Z80 proto=1 name=stub pid=1
V 15360:65,66
RET hl=0 result=0 break=0 writes=0
V 15360:67,68
ERR rom called into ROM space
V 15360:69,70
NEED full
V 15360:71,72
RET hl=0 result=1 break=0 writes=0
"""


class TestRenderFramesCounting(unittest.TestCase):
    """A call ends at its RET *or* at an ERR -- the protocol's two endings.

    render_frames counted only RET, so every call after a failed one was
    numbered one too low and asking for a frame of "call 7" rendered call
    8, or nothing at all (the 2026-09-19 audit, L-67).
    """

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.log = os.path.join(self.d, 'proto.out')
        with open(self.log, 'w') as f:
            f.write(LOG)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.d, ignore_errors=True)

    def render(self, *args):
        r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'render_frames.py'),
                            self.log] + [str(a) for a in args],
                           capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_the_erring_call_is_a_call(self):
        out = self.render(2, 'end')
        self.assertIn('call 2, at ERR', out)

    def test_the_call_after_an_err_keeps_its_number(self):
        out = self.render(3, 'end')
        self.assertIn('call 3, at RET', out)

    def test_the_first_call_is_unchanged(self):
        out = self.render(1, 'end')
        self.assertIn('call 1, at RET', out)

    def test_a_need_is_not_a_new_call(self):
        """The interpreter resends the SAME call as a full frame."""
        out = self.render(4, 'end')
        self.assertEqual(out.strip(), '')

    def test_a_need_restarts_the_run_numbering(self):
        """The V runs before a NEED belong to the attempt thrown away."""
        out = self.render(3, 'end')
        self.assertIn('(1 V runs)', out)


class TestTickProbeWaiting(unittest.TestCase):
    """The wait must not take a dead terminal for the text it awaited.

    On Linux a read from a pty whose child has gone raises OSError(EIO);
    macOS gives a 0-byte read.  The loop caught OSError and broke, which
    is exactly what it does when the text ARRIVES, so an interpreter that
    died during a probe was measured as one that answered and the tick
    numbers were of nothing at all (the 2026-09-19 audit, L-69).
    """

    def tick_probe(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'tick_probe_under_test', os.path.join(ROOT, 'tools', 'tick_probe.py'))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_a_terminal_at_end_of_file_is_not_success(self):
        mod = self.tick_probe()
        r, w = os.pipe()
        os.close(w)                      # nothing will ever be written
        try:
            with self.assertRaises(SystemExit) as e:
                mod.wait_for(r, [b''], b'NEVER APPEARS', 5)
            self.assertIn('exited', str(e.exception))
        finally:
            os.close(r)

    def test_a_timeout_is_still_a_timeout(self):
        mod = self.tick_probe()
        r, w = os.pipe()
        try:
            with self.assertRaises(SystemExit) as e:
                mod.wait_for(r, [b''], b'NEVER APPEARS', 0.2)
            self.assertIn('timeout', str(e.exception))
        finally:
            os.close(r)
            os.close(w)

    def test_text_that_arrives_is_found(self):
        mod = self.tick_probe()
        r, w = os.pipe()
        try:
            os.write(w, b'... READY ...')
            self.assertIsNone(mod.wait_for(r, [b''], b'READY', 2))
        finally:
            os.close(r)
            os.close(w)

    def test_text_already_in_the_buffer_needs_no_read(self):
        mod = self.tick_probe()
        r, w = os.pipe()
        os.close(w)
        try:
            self.assertIsNone(mod.wait_for(r, [b'READY'], b'READY', 2))
        finally:
            os.close(r)


if __name__ == '__main__':
    unittest.main()
