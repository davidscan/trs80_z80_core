#!/usr/bin/env python3
"""Fetch the single-step Z80 test vectors -- DESIGN.md decision 4.

    Third-party data. NEVER committed. Fetch script + gitignore, per
    the parent repo's no-third-party-material practice.

The suite is SingleStepTests/z80 (MIT): 1604 JSON files, 1000 test
cases each, ~1.6M cases, 1.37 GB extracted. Each case is one
instruction executed from a fully-specified random state --

    (registers, ram) -> (registers', ram')

-- which is exactly the shape DESIGN.md seam 1 requires of the core (a
pure library with no TRS-80 knowledge and no devices). The test format
and the architecture ruling agree; that is not a coincidence.

WHAT THIS VALIDATES THAT PHASE A COULD NOT. FINDING 1 validated the
table's STRUCTURE -- 176 hand-authored vectors, mnemonics,
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

Usage:
    python3 tools/fetch_vectors.py                  # status, no network
    python3 tools/fetch_vectors.py --all            # full suite (tarball)
    python3 tools/fetch_vectors.py --pages main,cb  # just those pages
    python3 tools/fetch_vectors.py --pages ed --limit 8   # smoke test
    python3 tools/fetch_vectors.py --coverage       # vectors vs our table
    python3 tools/fetch_vectors.py --update-lock    # re-pin to upstream main
"""

import argparse
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

def upstream_files(lock, refresh=False):
    """[(path, size), ...] for v1/, from the pinned tree. Cached."""
    if not refresh and os.path.exists(MANIFEST):
        with open(MANIFEST) as f:
            cached = json.load(f)
        if cached.get('sha') == lock['sha']:
            return [tuple(e) for e in cached['files']]

    data = json.loads(_get('%s/git/trees/%s?recursive=1' % (API, lock['sha'])))
    if data.get('truncated'):
        sys.exit('upstream tree came back truncated; refusing to guess at it')
    files = sorted((e['path'], e['size']) for e in data['tree']
                   if e['type'] == 'blob' and e['path'].startswith('v1/'))
    os.makedirs(DEST, exist_ok=True)
    with open(MANIFEST, 'w') as f:
        json.dump({'sha': lock['sha'], 'files': files}, f)
    return files


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
    want = [(p, s) for (p, s) in files if page_of(os.path.basename(p)) in pages]
    if limit is not None:
        byp = {}
        capped = []
        for p, s in want:
            k = page_of(os.path.basename(p))
            byp[k] = byp.get(k, 0) + 1
            if byp[k] <= limit:
                capped.append((p, s))
        want = capped

    os.makedirs(V1, exist_ok=True)
    todo = []
    for path, size in want:
        dest = os.path.join(DEST, path)
        if not force and os.path.exists(dest) and os.path.getsize(dest) == size:
            continue
        todo.append((path, size, dest))

    have = len(want) - len(todo)
    if not todo:
        print('all %d file(s) for %s already present' % (len(want), ','.join(sorted(pages))))
        return [os.path.join(DEST, p) for p, _ in want]

    total = sum(s for _, s, _ in todo)
    print('fetching %d file(s) (%s), %d already present, sha %s'
          % (len(todo), _human(total), have, lock['sha'][:12]))

    done = [0]

    def one(item):
        path, size, dest = item
        url = '%s/%s/%s' % (RAW, lock['sha'], urllib.parse.quote(path))
        blob = _get(url)
        if len(blob) != size:
            raise RuntimeError('%s: got %d bytes, expected %d' % (path, len(blob), size))
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

    return [os.path.join(DEST, p) for p, _ in want]


def fetch_all(lock, force=False):
    """Full suite via one tarball -- 1604 files, 1.37 GB extracted."""
    files = upstream_files(lock)
    if not force and os.path.isdir(V1):
        present = len([n for n in os.listdir(V1) if n.endswith('.json')])
        if present >= len(files):
            print('full suite already present (%d files); --force to refetch' % present)
            return sorted(os.path.join(V1, n) for n in os.listdir(V1)
                          if n.endswith('.json'))

    url = '%s/tar.gz/%s' % (CODELOAD, lock['sha'])
    os.makedirs(V1, exist_ok=True)
    tarball = os.path.join(DEST, '.tarball.tar.gz')
    print('downloading %s' % url)
    _download(url, tarball)
    print('  got %s, extracting %d file(s) to %s'
          % (_human(os.path.getsize(tarball)), len(files),
             os.path.relpath(V1, ROOT)))

    written = []
    with tarfile.open(tarball, mode='r:gz') as tf:
        for member in tf:
            if not member.isfile():
                continue
            # strip the '<repo>-<sha>/' prefix github wraps the tree in
            rel = member.name.split('/', 1)[1] if '/' in member.name else member.name
            if not rel.startswith('v1/'):
                continue
            dest = os.path.join(DEST, rel)
            src = tf.extractfile(member)
            with open(dest, 'wb') as f:
                f.write(src.read())
            written.append(dest)
            if len(written) % 200 == 0:
                print('  %d/%d' % (len(written), len(files)))
    print('  %d/%d' % (len(written), len(files)))
    os.remove(tarball)
    return written


# --------------------------------------------------------------------
# coverage: which of our 1780 encodings do the vectors actually reach?
# --------------------------------------------------------------------

def coverage(lock):
    """Cross-check the vector file list against z80/table.py.

    Phase A's discipline applied to the next stage: report the gap
    BEFORE relying on the suite, so 'the vectors pass' is never
    mistaken for 'the table is validated'. A silent gap is the whole
    failure mode CLAUDE.md's anchors rule exists to prevent.
    """
    from z80.table import TABLE

    files = upstream_files(lock)
    vec = set()
    for path, _ in files:
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
    print('license %s -- third-party, never committed (DESIGN.md decision 4)'
          % lock['license'])
    print('expect  %d files, %s extracted'
          % (lock['file_count'], _human(lock['total_bytes'])))
    if not os.path.isdir(V1):
        print('local   NOT FETCHED -- run with --all, or --pages main,cb')
        return
    names = [n for n in os.listdir(V1) if n.endswith('.json')]
    size = sum(os.path.getsize(os.path.join(V1, n)) for n in names)
    bypage = {}
    for n in names:
        k = page_of(n)
        bypage[k] = bypage.get(k, 0) + 1
    print('local   %d/%d files, %s' % (len(names), lock['file_count'], _human(size)))
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
