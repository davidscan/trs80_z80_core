#!/bin/sh
# corelog.sh -- run the core with both directions of the protocol logged.
#
#   TRS80_Z80="sh tools/corelog.sh /tmp/demon" ../trs80basic/basic prog.bas
#
# writes /tmp/demon.in (what the interpreter sent: HELLO, CALL, M, GO, K and
# T replies) and /tmp/demon.out (what the core answered: Z80, V, K, T, RET,
# W, ERR).  tools/render_frames.py replays the .out into screen frames.
here=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd) || exit 2
tee "$1.in" | python3 "$here/core.py" | tee "$1.out"
