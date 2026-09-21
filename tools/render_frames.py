"""Replay the core's V lines from a protocol log (tools/corelog.sh) into a
64x16 screen and render chosen moments at PIXEL level: each cell is 2x3
semigraphics pixels (bits 0-5), text cells show their character over three
sub-rows.  This is how "the demon dances" was verified on 2026-09-12
without a person at the terminal: the streamed video, replayed.

    python3 tools/render_frames.py proto.out CALL RUN [RUN ...]   # frames of that call
    python3 tools/render_frames.py proto.out CALL end             # the screen at its RET
"""
import sys

log, call_want = sys.argv[1], int(sys.argv[2])
marks = sys.argv[3:]
scr = [32] * 1024
call = 1
run = 0


def render(tag, rows=range(0, 16), cols=range(0, 64)):
    print('---- %s ----' % tag)
    for r in rows:
        for sub in range(3):
            line = ''
            for c in cols:
                b = scr[r * 64 + c]
                if b >= 128:
                    bits = b & 0x3F
                    l = bits >> (sub * 2) & 1
                    rr = bits >> (sub * 2 + 1) & 1
                    line += ('#' if l else ' ') + ('#' if rr else ' ')
                elif 32 < b < 127:
                    line += (chr(b) + ' ') if sub == 1 else '  '
                else:
                    line += '  '
            print('|' + line.rstrip() + '|')


for l in open(log).read().splitlines():
    if l.startswith('V '):
        a, bs = l[2:].split(':', 1)
        a = int(a)
        for i, b in enumerate(bs.split(',')):
            if 0 <= a - 15360 + i < 1024:
                scr[a - 15360 + i] = int(b)
        run += 1
        if call == call_want and str(run) in marks:
            render('call %d, V run %d' % (call, run))
    elif l.startswith('RET') or l.startswith('ERR'):
        # A call ends at its RET *or* at an ERR -- the protocol's two
        # endings.  Counting only RET left every call after a failed one
        # numbered one too low, so asking for "call 7" of a log with an
        # earlier ERR rendered call 8 (the 2026-09-19 audit, L-67).
        if call == call_want and 'end' in marks:
            render('call %d, at %s (%d V runs)' % (call, l.split()[0], run))
        call += 1
        run = 0
    elif l.startswith('NEED'):
        # NOT a new call: the interpreter resends this same one as a full
        # frame.  But the V runs so far belong to the attempt thrown away,
        # so the run numbers start again with it.
        run = 0
