"""tools/fetch_vectors.py: what is fetched is checked against committed
hashes, and nothing is written outside tests/vectors.

No network: the file list and the tarball are made here.  The tree hash is
checked against git's own (`git mktree`), so the pinning in
tools/vectors.lock means what git means by it.
"""

import io
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools import fetch_vectors as fv   # noqa: E402

GOOD = {'v1/00.json': b'[{"name": "00"}]\n', 'v1/dd cb __ 06.json': b'[]\n'}


def manifest(contents=GOOD):
    return sorted((p, len(b), fv.blob_sha(b)) for p, b in contents.items())


def tarball(path, members):
    with tarfile.open(path, 'w:gz') as tf:
        for name, data in members:
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))


class TestHashes(unittest.TestCase):
    def test_blob_and_tree_hashes_are_gits(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(['git', 'init', '-q', d], check=True)
            lines = []
            for path, data in sorted(GOOD.items()):
                sha = subprocess.run(['git', '-C', d, 'hash-object', '-w', '--stdin'], input=data,
                                     capture_output=True, check=True).stdout.decode().strip()
                self.assertEqual(sha, fv.blob_sha(data))
                lines.append('100644 blob %s\t%s' % (sha, path[3:]))
            tree = subprocess.run(['git', '-C', d, 'mktree'], input=('\n'.join(lines) + '\n').encode(),
                                  capture_output=True, check=True).stdout.decode().strip()
        self.assertEqual(tree, fv.v1_tree_sha(manifest()))

    def test_the_committed_lock_pins_a_tree(self):
        self.assertRegex(fv.load_lock().get('v1_tree', ''), r'^[0-9a-f]{40}$')

    def test_a_list_that_does_not_hash_to_the_lock_is_refused(self):
        files = manifest()
        lock = {'v1_tree': fv.v1_tree_sha(files)}
        fv.check_manifest(lock, files, 'test')                       # the pinned list passes
        other = manifest(dict(GOOD, **{'v1/00.json': b'[{"name": "tampered"}]\n'}))
        with self.assertRaises(SystemExit):
            fv.check_manifest(lock, other, 'test')                   # one blob SHA differs
        with self.assertRaises(SystemExit):
            fv.check_manifest({}, files, 'test')                     # a lock with no tree hash
        for bad in ('v1/../../x.json', 'v1/sub/x.json', 'v1/..', 'v2/00.json'):
            with self.assertRaises(SystemExit, msg=bad):
                fv.check_manifest(lock, files + [(bad, 1, '0' * 40)], 'test')


class TestUnpack(unittest.TestCase):
    def test_only_pinned_members_are_written_and_none_outside(self):
        with tempfile.TemporaryDirectory() as d:
            dest = os.path.join(d, 'a', 'vectors')
            os.makedirs(os.path.join(dest, 'v1'))
            tb = os.path.join(d, 't.tar.gz')
            tarball(tb, [('z80-abc/v1/00.json', GOOD['v1/00.json']),
                         ('z80-abc/v1/../../escaped.json', b'outside'),
                         ('z80-abc/v1/not-pinned.json', b'[]'),
                         ('z80-abc/README.md', b'x'),
                         ('z80-abc/v1/dd cb __ 06.json', GOOD['v1/dd cb __ 06.json'])])
            written = fv.unpack(tb, manifest(), dest)
            self.assertEqual(sorted(os.path.relpath(w, dest) for w in written),
                             ['v1/00.json', 'v1/dd cb __ 06.json'])
            found = sorted(os.path.relpath(os.path.join(r, f), d)
                           for r, _, fs in os.walk(d) for f in fs)
            self.assertEqual(found, ['a/vectors/v1/00.json', 'a/vectors/v1/dd cb __ 06.json', 't.tar.gz'])

    def test_a_member_with_other_bytes_stops_the_fetch(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, 'v1'))
            tb = os.path.join(d, 't.tar.gz')
            tarball(tb, [('z80-abc/v1/00.json', b'[{"name": "substituted"}]\n')])
            with self.assertRaises(SystemExit):
                fv.unpack(tb, manifest(), d)
            self.assertEqual(os.listdir(os.path.join(d, 'v1')), [])


class TestPresentMeansHashed(unittest.TestCase):
    """A local file counts only if it hashes to the pin: names and sizes
    survive a re-pin and an interrupted fetch, content does not."""

    # the OLD pin's copy: the same names, the same sizes, other bytes
    STALE = {'v1/00.json': b'[{"name": "XX"}]\n', 'v1/dd cb __ 06.json': b'[]\n'}

    def seed(self, d, contents, stray=True):
        os.makedirs(os.path.join(d, 'v1'))
        for path, data in contents.items():
            with open(os.path.join(d, path), 'wb') as f:
                f.write(data)
        if stray:
            with open(os.path.join(d, 'v1', 'gone upstream.json'), 'wb') as f:
                f.write(b'[]\n')

    def test_local_state_tells_them_apart(self):
        self.assertEqual(len(self.STALE['v1/00.json']), len(GOOD['v1/00.json']))
        with tempfile.TemporaryDirectory() as d:
            self.seed(d, {'v1/00.json': self.STALE['v1/00.json']})
            good, bad, missing, strays = fv.local_state(manifest(), d)
            self.assertEqual((good, bad, missing, strays),
                             ([], ['v1/00.json'], ['v1/dd cb __ 06.json'],
                              ['gone upstream.json']))

    def test_fetch_all_refetches_another_pins_vectors(self):
        with tempfile.TemporaryDirectory() as d:
            self.seed(d, self.STALE)
            saved = (fv.DEST, fv.V1, fv.upstream_files, fv._download)
            fetched = []

            def download(url, dest, timeout=1800):
                fetched.append(url)
                tarball(dest, [('z80-abc/' + p, b) for p, b in GOOD.items()])
            fv.DEST, fv.V1 = d, os.path.join(d, 'v1')
            fv.upstream_files = lambda lock, refresh=False: manifest()
            fv._download = download
            try:
                fv.fetch_all({'sha': 'abc'})
                state = fv.local_state(manifest(), d)
                fv.fetch_all({'sha': 'abc'})             # now it IS present
            finally:
                fv.DEST, fv.V1, fv.upstream_files, fv._download = saved
            self.assertEqual(len(fetched), 1)
            self.assertEqual(state, (sorted(GOOD), [], [], []))

    def test_a_short_tarball_is_not_a_fetch(self):
        with tempfile.TemporaryDirectory() as d:
            saved = (fv.DEST, fv.V1, fv.upstream_files, fv._download)
            fv.DEST, fv.V1 = d, os.path.join(d, 'v1')
            fv.upstream_files = lambda lock, refresh=False: manifest()
            fv._download = lambda url, dest, timeout=1800: tarball(
                dest, [('z80-abc/v1/00.json', GOOD['v1/00.json'])])
            try:
                with self.assertRaises(SystemExit):
                    fv.fetch_all({'sha': 'abc'})
            finally:
                fv.DEST, fv.V1, fv.upstream_files, fv._download = saved

    def test_status_does_not_vouch_for_files_it_cannot_check(self):
        """After --update-lock no list for the new pin is cached."""
        with tempfile.TemporaryDirectory() as d:
            self.seed(d, self.STALE, stray=False)
            saved = (fv.DEST, fv.V1, fv.MANIFEST)
            fv.DEST, fv.V1, fv.MANIFEST = d, os.path.join(d, 'v1'), os.path.join(d, '.manifest.json')
            out = io.StringIO()
            stdout, sys.stdout = sys.stdout, out
            try:
                fv.status(dict(fv.load_lock(), file_count=2))
            finally:
                sys.stdout = stdout
                fv.DEST, fv.V1, fv.MANIFEST = saved
            self.assertIn('NOT CHECKED against this pin', out.getvalue())
            self.assertNotIn('2/2', out.getvalue())


if __name__ == '__main__':
    unittest.main()
