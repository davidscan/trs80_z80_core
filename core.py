#!/usr/bin/env python3
"""The Z80 core as the interpreter's USR coprocess -- what TRS80_Z80 names.

    TRS80_Z80="python3 /path/to/trs80_z80_core/core.py" ../trs80basic/basic prog.bas

Speaks PROTOCOL.md version 1 on stdin/stdout (see z80/coprocess.py).
`--fixture` adds the machine-code routines behind the stub's canned entry
addresses so trs80basic's `sh programs/tests/z80.sh` can run against a
real core (DD-17).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from z80.coprocess import main   # noqa: E402

if __name__ == '__main__':
    sys.exit(main())
