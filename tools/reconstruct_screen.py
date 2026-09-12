"""Reconstruct the TRS-80 grid the interpreter actually drew, from a raw
capture of its terminal output.

The interpreter draws the 64x16 grid with absolute ANSI cursor moves
(ESC[row;colH) and clears with ESC[2J / ESC[0J; CHR$ control codes reach
the screen the same way.  Capture the terminal bytes (a pty driver, or
`script`), pass the file here, and it replays the moves and clears into a
16-row view -- what a person sees, not the raw video buffer (for that use
render_frames.py on a protocol log).  This is how the Dancing Demon's
display bugs were pinned on 2026-09-12 without a person at the terminal.

    python3 tools/reconstruct_screen.py capture.raw
"""
import sys


def reconstruct(data):
    rows = [[' '] * 80 for _ in range(24)]
    cr = cc = 0
    i, n = 0, len(data)
    while i < n:
        c = data[i]
        if c == '\x1b' and i + 1 < n and data[i + 1] == '[':
            j = i + 2
            while j < n and not (0x40 <= ord(data[j]) <= 0x7e):
                j += 1
            seq, cmd = data[i + 2:j], (data[j] if j < n else '')
            if cmd == 'H':
                p = seq.split(';')
                cr = int(p[0]) - 1 if p and p[0] else 0
                cc = int(p[1]) - 1 if len(p) > 1 and p[1] else 0
            elif cmd == 'J':
                if seq in ('', '0'):
                    for x in range(cc, 80):
                        rows[cr][x] = ' '
                    for y in range(cr + 1, 24):
                        rows[y] = [' '] * 80
                elif seq == '2':
                    rows = [[' '] * 80 for _ in range(24)]
            elif cmd == 'K' and seq in ('', '0'):
                for x in range(cc, 80):
                    rows[cr][x] = ' '
            i = j + 1
            continue
        if c == '\r':
            cc = 0; i += 1; continue
        if c == '\n':
            cr += 1; i += 1; continue
        o = ord(c)
        if o < 0x80:
            ch, adv = c, 1
        elif o < 0xE0:
            ch, adv = data[i:i + 2].encode('latin-1').decode('utf-8', 'replace'), 2
        elif o < 0xF0:
            ch, adv = data[i:i + 3].encode('latin-1').decode('utf-8', 'replace'), 3
        else:
            ch, adv = data[i:i + 4].encode('latin-1').decode('utf-8', 'replace'), 4
        if 0 <= cr < 24 and 0 <= cc < 80:
            rows[cr][cc] = ch
        cc += 1
        i += adv
    return rows


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit('usage: reconstruct_screen.py capture.raw')
    data = open(sys.argv[1], 'rb').read().decode('latin-1')
    for r in reconstruct(data)[:16]:
        print('|' + ''.join(r)[:64] + '|')
