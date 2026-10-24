#!/usr/bin/env python3
"""tools/check_skips.py -- name every skipped test, and fail on one CI must run.

    python3 -m unittest discover -s tests -v 2>&1 | tee test.log
    python3 tools/check_skips.py test.log

unittest reports only "OK (skipped=17)", so a test that stopped running
because its input went missing looked like one that passed (the
2026-09-30 audit's silent-skip sweep; trs80basic's run_all does the same
since BL-36).  This prints each skipped test with its reason and exits 1
when a reason is not one of EXPECTED: the inputs CI cannot have, which
are private and local (the corpus archive and the ocr transcriptions).
Everything else -- the vectors, the interpreter checkout, gawk, the tags
-- CI provides, so a skip for want of it is a failure there.
"""
import re
import sys

EXPECTED = (
    'the corpus is not linked beside this repo',
    'the ocr transcriptions are not present',
    'raw transcription absent',
)

# `test_x (module.Class.test_x) ... skipped 'why'`, or, for a test with a
# docstring, the docstring's first line between the name and the verdict
SKIP_RE = re.compile(r"^(?P<test>\S+ \([^)]*\))?.*?\.\.\. skipped '(?P<why>.*)'$")


def skips(lines):
    """[(test or '', reason)] for every skipped test in a -v log."""
    out, last = [], ''
    for line in lines:
        line = line.rstrip('\n')
        m = re.match(r'^(\S+ \([^)]*\))', line)
        if m:
            last = m.group(1)
        s = SKIP_RE.match(line)
        if s:
            out.append((s.group('test') or last, s.group('why')))
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        sys.stderr.write('usage: python3 tools/check_skips.py TEST_LOG\n')
        return 2
    with open(argv[0], errors='replace') as f:
        found = skips(f)
    bad = [(t, w) for t, w in found if w not in EXPECTED]
    for t, w in found:
        print('%s %s: %s' % ('UNEXPECTED SKIP' if (t, w) in bad else 'skipped', t, w))
    print('%d skipped, %d unexpected' % (len(found), len(bad)))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
