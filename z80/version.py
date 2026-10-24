"""The core's own version (the 2026-09-30 audit, ZL-10).

VERSION is the release this tree is: bumped by the commit that is the
release, beside its annotated tag of the same name.  Between tags a
checkout names its exact build as git describes it ("v2.1.1-50-gabc1234",
"-dirty" with edits), so a bug report says which core ran.  The
handshake carries only `name` and `proto` (PROTOCOL.md); this is what
`core.py --version` and the z80 command-line tools' --version print.
"""
import os
import subprocess

VERSION = 'v2.1.1'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build_id():
    """git describe of this tree, or '' when it is not itself a checkout:
    from an unpacked release inside some other repository git would walk
    up and describe THAT one, so the top level must be this directory
    (compared physically: /tmp is /private/tmp on macOS)."""
    try:
        top = subprocess.run(['git', '-C', ROOT, 'rev-parse', '--show-toplevel'],
                             capture_output=True, text=True, timeout=10)
        if top.returncode or os.path.realpath(top.stdout.strip()) != os.path.realpath(ROOT):
            return ''
        d = subprocess.run(['git', '-C', ROOT, 'describe', '--tags', '--always', '--dirty'],
                           capture_output=True, text=True, timeout=10)
        return d.stdout.strip() if d.returncode == 0 else ''
    except (OSError, subprocess.TimeoutExpired):
        return ''


def version_text():
    from .coprocess import NAME, PROTO
    bid = build_id()
    return '%s %s%s, protocol %s' % (NAME, VERSION,
                                     ' (build %s)' % bid if bid and bid != VERSION else '', PROTO)


def add_version_argument(ap):
    """--version on a z80 command line, computed only when asked for (git
    is not run on every invocation)."""
    import argparse

    class Version(argparse.Action):
        def __call__(self, parser, namespace, values, option_string=None):
            import sys
            sys.stdout.write(version_text() + '\n')
            parser.exit()

    ap.add_argument('--version', action=Version, nargs=0, default=argparse.SUPPRESS,
                    help="print the core's version and exit")
