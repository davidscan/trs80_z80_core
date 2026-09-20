#!/usr/bin/env python3
"""Fetch the single-step Z80 test vectors -- fetched, never committed.

    Third-party data. NEVER committed. Fetch script + gitignore, per
    the interpreter repo's no-third-party-material practice.

The suite is SingleStepTests/z80 (MIT): 1604 JSON files, 1000 test
cases each, ~1.6M cases, 1.37 GB extracted. Each case is one
instruction executed from a fully-specified random state --

    (registers, ram) -> (registers', ram')

-- which is exactly the shape the core is built to (a
pure library with no TRS-80 knowledge and no devices). The test format
and the architecture ruling agree; that is not a coincidence.

WHAT THIS VALIDATES THAT PHASE A COULD NOT. FINDING 1 validated the
table's STRUCTURE -- 185 hand-authored vectors (six lists in
tests/test_table.py; the count read 176 until 2026-09-11), mnemonics,
declared-length-equals-consumed, inverse round-trip -- and recorded
that cycle costs are carried but UNVALIDATED. These vectors validate
execution semantics, every flag bit, and (via len(cycles)) the cost
column.

PINNED TO A SHA. The upstream repo is live and its tests get corrected
over time ("Re-generate the tests." is the pinned commit's own
message). An unpinned fetch would make a passing suite unreproducible
and a silent upstream change indistinguishable from our own
regression. The SHA lives in tools/vectors.lock, which IS committed --
it is metadata about the data, not the data.

CONTENT-VERIFIED (2026-09-20). The lock also pins `v1_tree`, the git
tree SHA of upstream's v1/ directory at that commit. A git tree object
is the list of its entries' names and blob SHAs, so the fetched file
list is accepted only if it hashes to the pinned tree, and a fetched
file only if it hashes to its blob SHA in that list: every byte is
checked against a committed hash, and nothing rests on the transport.
The tarball is unpacked by that same list -- a member it does not name
is not written, so no member name can reach outside tests/vectors.

Usage:
    python3 tools/fetch_vectors.py                  # status, no network
    python3 tools/fetch_vectors.py --all            # full suite (tarball)
    python3 tools/fetch_vectors.py --pages main,cb  # just those pages
    python3 tools/fetch_vectors.py --pages ed --limit 8   # smoke test
    python3 tools/fetch_vectors.py --coverage       # vectors vs our table
    python3 tools/fetch_vectors.py --update-lock    # re-pin to upstream main
"""

import argparse
import binascii
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

LOCK = os.path.join(ROOT, 'tools', 'vectors.lock')
DEST = os.path.join(ROOT, 'tests', 'vectors')
V1 = os.path.join(DEST, 'v1')
MANIFEST = os.path.join(DEST, '.manifest.json')   # cached upstream tree

REPO = 'SingleStepTests/z80'
API = 'https://api.github.com/repos/' + REPO
RAW = 'https://raw.githubusercontent.com/' + REPO
CODELOAD = 'https://codeload.github.com/' + REPO

# Upstream page names are literal filename prefixes ('dd cb __ 06.json');
# the CLI takes the compact keys on the left.
PAGES = {
    'main': '',
    'cb': 'cb ',
    'dd': 'dd ',
    'ed': 'ed ',
    'fd': 'fd ',
    'ddcb': 'dd cb __ ',
    'fdcb': 'fd cb __ ',
}


# --------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------

UA = 'trs80_z80_core-fetch'
HAVE_CURL = shutil.which('curl') is not None


def _get(url, timeout=60):
    """Fetch a URL to bytes.

    curl first, deliberately. A stock python.org build on macOS ships
    without a CA bundle, so urllib raises CERTIFICATE_VERIFY_FAILED on
    a machine where curl is perfectly happy -- exactly this machine.
    curl uses the system trust store and gives us retries for free;
    urllib is the fallback for a box without curl.
    """
    if HAVE_CURL:
        p = subprocess.run(
            ['curl', '-fsSL', '--retry', '3', '--retry-delay', '1',
             '--max-time', str(timeout), '-A', UA, url],
            capture_output=True)
        if p.returncode != 0:
            raise RuntimeError('curl failed (%d) on %s: %s'
                               % (p.returncode, url, p.stderr.decode()[:200]))
        return p.stdout
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _download(url, dest, timeout=1800):
    """Stream a large URL to a file -- resumable, with a progress bar.

    The tarball is ~200 MB; holding it in memory and losing it to a
    dropped connection are both avoidable.
    """
    if HAVE_CURL:
        cmd = ['curl', '-fL', '--retry', '3', '--retry-delay', '2',
               '--max-time', str(timeout), '-A', UA, '-C', '-',
               '-o', dest, '--progress-bar', url]
        if subprocess.run(cmd).returncode != 0:
            raise RuntimeError('curl failed downloading %s' % url)
        return dest
    with open(dest, 'wb') as f:
        f.write(_get(url, timeout))
    return dest


def _human(n):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return '%.1f %s' % (n, unit) if unit != 'B' else '%d B' % n
        n /= 1024.0


def load_lock():
    with open(LOCK) as f:
        return json.load(f)


def name_to_encoding(name):
    """'dd cb __ 06.json' -> (0xDD, 0xCB, 0x06).

    The '__' is upstream's placeholder for the DDCB/FDCB displacement
    byte, which is runtime data rather than part of the encoding -- so
    it is dropped, matching how z80/table.py keys those pages.
    """
    stem = name[:-5] if name.endswith('.json') else name
    return tuple(int(tok, 16) for tok in stem.split(' ') if tok != '__')


def page_of(name):
    for key in ('ddcb', 'fdcb', 'cb', 'dd', 'ed', 'fd'):
        if name.startswith(PAGES[key]):
            return key
    return 'main'


# --------------------------------------------------------------------
# upstream file list (cached; one API call, pinned to the locked SHA)
# --------------------------------------------------------------------

def blob_sha(data):
    """The git blob SHA-1 of a file's bytes."""
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


def v1_tree_sha(files):
    """The git tree SHA-1 of v1/ as `files` describes it: a tree object is
    its entries, sorted by name, each `<mode> <name>\\0<20-byte blob SHA>`.
    v1/ holds ordinary files only, so every mode is 100644."""
    body = b''.join(b'100644 ' + name + b'\0' + binascii.unhexlify(sha)
                    for name, sha in sorted((p[3:].encode(), h) for p, _, h in files))
    return hashlib.sha1(b'tree %d\0' % len(body) + body).hexdigest()


def check_manifest(lock, files, where):
    """The file list is trusted only when it hashes to the pinned tree."""
    for path, _, _ in files:
        name = path[3:]
        if not path.startswith('v1/') or not name or '/' in name or name in ('.', '..'):
            sys.exit('%s: %r is not a plain file name under v1/' % (where, path))
    if 'v1_tree' not in lock:
        sys.exit('tools/vectors.lock has no v1_tree hash; run --update-lock '
                 '(and commit the lock) before fetching')
    got = v1_tree_sha(files)
    if got != lock['v1_tree']:
        sys.exit('%s: the v1/ file list hashes to %s, the lock pins %s -- refusing it'
                 % (where, got, lock['v1_tree']))


def upstream_files(lock, refresh=False):
    """[(path, size, blob sha), ...] for v1/, from the pinned tree, checked
    against the lock's v1_tree hash whether fetched or cached."""
    files = None if refresh else cached_files(lock)
    if files is not None:
        return files

    data = json.loads(_get('%s/git/trees/%s?recursive=1' % (API, lock['sha'])))
    if data.get('truncated'):
        sys.exit('upstream tree came back truncated; refusing to guess at it')
    files = sorted((e['path'], e['size'], e['sha']) for e in data['tree']
                   if e['type'] == 'blob' and e['path'].startswith('v1/'))
    check_manifest(lock, files, 'upstream tree')
    os.makedirs(DEST, exist_ok=True)
    with open(MANIFEST, 'w') as f:
        json.dump({'sha': lock['sha'], 'files': files}, f)
    return files


def cached_files(lock):
    """The pinned file list from the cache alone (no network), or None when
    no list for THIS pin is cached.  Checked against v1_tree like any other."""
    if not os.path.exists(MANIFEST):
        return None
    with open(MANIFEST) as f:
        cached = json.load(f)
    if cached.get('sha') != lock['sha'] or not all(len(e) == 3 for e in cached['files']):
        return None
    files = [tuple(e) for e in cached['files']]
    check_manifest(lock, files, 'cached manifest')
    return files


def local_state(files, dest_root=None):
    """(good, bad, missing, strays) for the local copy against the pinned list.

    PRESENT MEANS HASHED.  A name, or a name and a size, says nothing about
    which pin a file came from: after --update-lock the old pin's vectors
    are all still there under the same names, and an interrupted fetch
    leaves files that exist.  So a local file counts only if its bytes hash
    to its pinned blob SHA (1.3 GB hashes in about a second).  `strays` are
    .json files in v1/ the pin does not name -- an older pin's leftovers,
    which the test runner would execute with the rest."""
    dest_root = DEST if dest_root is None else dest_root
    good, bad, missing = [], [], []
    for path, _size, sha in files:
        dest = os.path.join(dest_root, path)
        try:
            with open(dest, 'rb') as f:
                ok = blob_sha(f.read()) == sha
        except OSError:
            missing.append(path)
            continue
        (good if ok else bad).append(path)
    v1 = os.path.join(dest_root, 'v1')
    named = set(os.path.basename(path) for path, _, _ in files)
    strays = sorted(n for n in (os.listdir(v1) if os.path.isdir(v1) else [])
                    if n.endswith('.json') and n not in named)
    return good, bad, missing, strays


def drop_strays(strays, dest_root=None):
    """Remove v1/*.json files the pin does not name (fetched data, never ours)."""
    dest_root = DEST if dest_root is None else dest_root
    for n in strays:
        os.remove(os.path.join(dest_root, 'v1', n))
    if strays:
        print('  removed %d file(s) the pinned list does not name' % len(strays))


# --------------------------------------------------------------------
# verification -- a fetch is not done until it is checked
# --------------------------------------------------------------------

REQUIRED_INITIAL = {'pc', 'sp', 'a', 'f', 'b', 'c', 'd', 'e', 'h', 'l',
                    'i', 'r', 'ix', 'iy', 'af_', 'bc_', 'de_', 'hl_',
                    'wz', 'q', 'p', 'ram'}


def verify(paths, sample=5):
    """Parse a sample of fetched files and assert the documented shape.

    Cheap insurance against the failure mode that actually happens: a
    truncated download, or an HTML error page saved under a .json name.
    """
    checked = 0
    for p in paths[:sample]:
        with open(p) as f:
            cases = json.load(f)
        if not isinstance(cases, list) or not cases:
            sys.exit('%s: expected a non-empty list of cases' % p)
        if len(cases) != 1000:
            print('  NOTE %s has %d cases, expected 1000'
                  % (os.path.basename(p), len(cases)))
        c = cases[0]
        missing = REQUIRED_INITIAL - set(c.get('initial', {}))
        if missing:
            sys.exit('%s: initial state missing %s' % (p, sorted(missing)))
        for key in ('name', 'final', 'cycles'):
            if key not in c:
                sys.exit('%s: case missing %r' % (p, key))
        checked += 1
    return checked


# --------------------------------------------------------------------
# fetch modes
# --------------------------------------------------------------------

def fetch_pages(lock, pages, limit=None, force=False):
    """Per-file fetch of selected pages -- downloads only what is asked.

    The tarball is one request but ~200 MB; a single page is 80-256
    small files. For day-to-day core work on one page, this is the
    cheaper door.
    """
    files = upstream_files(lock)
    want = [f for f in files if page_of(os.path.basename(f[0])) in pages]
    if limit is not None:
        byp = {}
        capped = []
        for f in want:
            k = page_of(os.path.basename(f[0]))
            byp[k] = byp.get(k, 0) + 1
            if byp[k] <= limit:
                capped.append(f)
        want = capped

    os.makedirs(V1, exist_ok=True)
    good = set() if force else set(local_state(want)[0])
    todo = [(path, size, sha, os.path.join(DEST, path))
            for path, size, sha in want if path not in good]

    have = len(want) - len(todo)
    if not todo:
        print('all %d file(s) for %s already present' % (len(want), ','.join(sorted(pages))))
        return [os.path.join(DEST, f[0]) for f in want]

    total = sum(t[1] for t in todo)
    print('fetching %d file(s) (%s), %d already present, sha %s'
          % (len(todo), _human(total), have, lock['sha'][:12]))

    done = [0]

    def one(item):
        path, size, sha, dest = item
        url = '%s/%s/%s' % (RAW, lock['sha'], urllib.parse.quote(path))
        blob = _get(url)
        if len(blob) != size:
            raise RuntimeError('%s: got %d bytes, expected %d' % (path, len(blob), size))
        if blob_sha(blob) != sha:
            raise RuntimeError('%s: content does not hash to the pinned blob %s' % (path, sha))
        tmp = dest + '.part'
        with open(tmp, 'wb') as f:
            f.write(blob)
        os.replace(tmp, dest)
        done[0] += 1
        if done[0] % 25 == 0 or done[0] == len(todo):
            print('  %d/%d' % (done[0], len(todo)))
        return dest

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(one, todo))

    return [os.path.join(DEST, f[0]) for f in want]


def fetch_all(lock, force=False):
    """Full suite via one tarball -- 1604 files, 1.37 GB extracted."""
    files = upstream_files(lock)
    if not force and os.path.isdir(V1):
        good, bad, missing, strays = local_state(files)
        if not bad and not missing:
            drop_strays(strays)
            print('full suite already present (%d files, each hashed against the pin); '
                  '--force to refetch' % len(good))
            return [os.path.join(DEST, path) for path in good]
        print('local copy: %d file(s) match the pin, %d do not, %d missing'
              % (len(good), len(bad), len(missing)))

    url = '%s/tar.gz/%s' % (CODELOAD, lock['sha'])
    os.makedirs(V1, exist_ok=True)
    tarball = os.path.join(DEST, '.tarball.tar.gz')
    print('downloading %s' % url)
    _download(url, tarball)
    print('  got %s, extracting %d file(s) to %s'
          % (_human(os.path.getsize(tarball)), len(files),
             os.path.relpath(V1, ROOT)))

    written = unpack(tarball, files)
    os.remove(tarball)
    if len(written) != len(files):
        sys.exit('the tarball held %d of the %d pinned files: the fetch is not complete'
                 % (len(written), len(files)))
    drop_strays(local_state(files)[3])
    return written


def unpack(tarball, files, dest_root=None):
    """Write the tarball's v1/ members under dest_root (tests/vectors).

    The pinned file list is the whitelist: a member it does not name is
    not written, whatever its name says (`v1/../../x` went straight into
    os.path.join before 2026-09-20), and a member whose bytes do not hash
    to its pinned blob SHA stops the fetch.  check_manifest has already
    established that every listed path is a plain name under v1/."""
    dest_root = DEST if dest_root is None else dest_root
    pinned = {path: sha for path, _, sha in files}
    written = []
    with tarfile.open(tarball, mode='r:gz') as tf:
        for member in tf:
            if not member.isfile():
                continue
            # strip the '<repo>-<sha>/' prefix github wraps the tree in
            rel = member.name.split('/', 1)[1] if '/' in member.name else member.name
            if rel not in pinned:
                if rel.startswith('v1/'):
                    print('  SKIPPED %r: not in the pinned file list' % member.name)
                continue
            blob = tf.extractfile(member).read()
            if blob_sha(blob) != pinned[rel]:
                sys.exit('%s: content does not hash to the pinned blob %s' % (rel, pinned[rel]))
            dest = os.path.join(dest_root, rel)
            with open(dest + '.part', 'wb') as f:
                f.write(blob)
            os.replace(dest + '.part', dest)
            written.append(dest)
            if len(written) % 200 == 0:
                print('  %d/%d' % (len(written), len(files)))
    print('  %d/%d' % (len(written), len(files)))
    return written


# --------------------------------------------------------------------
# coverage: which of our 1780 encodings do the vectors actually reach?
# --------------------------------------------------------------------

def coverage(lock):
    """Cross-check the vector file list against z80/table.py.

    Phase A's discipline applied to the next stage: report the gap
    BEFORE relying on the suite, so 'the vectors pass' is never
    mistaken for 'the table is validated'. A silent gap is the whole
    failure mode the anchors rule exists to prevent.
    """
    from z80.table import TABLE

    files = upstream_files(lock)
    vec = set()
    for path, _, _ in files:
        try:
            vec.add(name_to_encoding(os.path.basename(path)))
        except ValueError:
            continue

    ours = set(TABLE)
    real = {e for e in ours if TABLE[e].kind != 'invalid'}
    covered = real & vec
    uncovered = real - vec
    extra = vec - ours

    print('vector coverage of z80/table.py')
    print('  table encodings          %5d  (%d non-invalid)' % (len(ours), len(real)))
    print('  vector files             %5d' % len(vec))
    print('  covered                  %5d  (%.1f%% of non-invalid)'
          % (len(covered), 100.0 * len(covered) / max(1, len(real))))
    print('  NOT covered by vectors   %5d' % len(uncovered))
    print('  vectors with no entry    %5d' % len(extra))

    if uncovered:
        undoc = sum(1 for e in uncovered if TABLE[e].undoc)
        print('    of the uncovered: %d undocumented, %d documented'
              % (undoc, len(uncovered) - undoc))
        docd = sorted(e for e in uncovered if not TABLE[e].undoc)
        for enc in docd[:12]:
            print('      %-14s %s' % (' '.join('%02X' % b for b in enc),
                                      TABLE[enc].mnemonic))
        if len(docd) > 12:
            print('      ... and %d more' % (len(docd) - 12))
    if extra:
        for enc in sorted(extra)[:8]:
            print('    no table entry: %s' % ' '.join('%02X' % b for b in enc))
    return uncovered, extra


# --------------------------------------------------------------------
# status / lock maintenance
# --------------------------------------------------------------------

def status(lock):
    print('suite   %s' % lock['repo'])
    print('pinned  %s  (%s)' % (lock['sha'], lock['pinned_date']))
    print('license %s -- third-party, never committed'
          % lock['license'])
    print('expect  %d files, %s extracted'
          % (lock['file_count'], _human(lock['total_bytes'])))
    if not os.path.isdir(V1):
        print('local   NOT FETCHED -- run with --all, or --pages main,cb')
        return
    names = [n for n in os.listdir(V1) if n.endswith('.json')]
    files = cached_files(lock)
    if files is None:
        # no file list for THIS pin here (a fresh --update-lock, or a copied
        # tree): the names on disk say nothing about which pin they are from
        print('local   %d file(s) on disk, NOT CHECKED against this pin -- '
              'run with --all or --pages to fetch and check' % len(names))
        return
    good, bad, missing, strays = local_state(files)
    size = sum(os.path.getsize(os.path.join(DEST, p)) for p in good)
    bypage = {}
    for p in good:
        k = page_of(os.path.basename(p))
        bypage[k] = bypage.get(k, 0) + 1
    print('local   %d/%d files match the pin, %s' % (len(good), lock['file_count'], _human(size)))
    if bad or strays:
        print('        %d file(s) do NOT hash to the pin, %d are not named by it -- '
              'run with --all' % (len(bad), len(strays)))
    for k in ('main', 'cb', 'ed', 'dd', 'fd', 'ddcb', 'fdcb'):
        if k in bypage:
            print('          %-5s %d' % (k, bypage[k]))


def update_lock():
    """Re-pin to upstream main. Deliberate and visible -- a lock bump is
    its own commit, so an upstream test correction can never be
    confused with one of our regressions."""
    head = json.loads(_get(API + '/commits/main'))
    sha = head['sha']
    tree = json.loads(_get('%s/git/trees/%s?recursive=1' % (API, sha)))
    v1 = [e for e in tree['tree'] if e['type'] == 'blob' and e['path'].startswith('v1/')]
    meta = json.loads(_get(API))
    lock = {
        'repo': REPO,
        'url': 'https://github.com/' + REPO,
        'sha': sha,
        'pinned_date': head['commit']['committer']['date'],
        'license': (meta.get('license') or {}).get('spdx_id', 'UNKNOWN'),
        'file_count': len(v1),
        'total_bytes': sum(e['size'] for e in v1),
        'cases_per_file': 1000,
        # the git tree SHA of v1/: what every fetched list and file is checked against
        'v1_tree': v1_tree_sha([(e['path'], e['size'], e['sha']) for e in v1]),
    }
    with open(LOCK, 'w') as f:
        json.dump(lock, f, indent=2)
        f.write('\n')
    print('pinned %s to %s (%d files, %s)'
          % (REPO, sha[:12], lock['file_count'], _human(lock['total_bytes'])))
    return lock


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--all', action='store_true', help='full suite via tarball')
    ap.add_argument('--pages', help='comma-separated: %s' % ','.join(PAGES))
    ap.add_argument('--limit', type=int, help='cap files per page (smoke tests)')
    ap.add_argument('--coverage', action='store_true', help='vectors vs z80/table.py')
    ap.add_argument('--update-lock', action='store_true', help='re-pin to upstream main')
    ap.add_argument('--force', action='store_true', help='refetch what is present')
    args = ap.parse_args()

    if args.update_lock:
        update_lock()
        return 0

    lock = load_lock()

    if args.all or args.pages:
        if args.pages:
            pages = [p.strip() for p in args.pages.split(',') if p.strip()]
            bad = [p for p in pages if p not in PAGES]
            if bad:
                sys.exit('unknown page(s) %s; known: %s' % (bad, ','.join(PAGES)))
            got = fetch_pages(lock, set(pages), args.limit, args.force)
        else:
            got = fetch_all(lock, args.force)
        n = verify(got)
        print('verified %d sampled file(s): 1000 cases, documented shape' % n)
        print()

    if args.coverage or args.all or args.pages:
        coverage(lock)
        print()

    status(lock)
    return 0


if __name__ == '__main__':
    sys.exit(main())
