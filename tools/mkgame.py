#!/usr/bin/env python3
"""mkgame.py -- CATCH, a machine-language arcade game in a BASIC wrapper.

    python3 tools/mkgame.py [--out demo/catch.bas] [--org N] [--fps N]
    python3 tools/mkgame.py --disasm            # the routine, disassembled
    python3 tools/mkgame.py --selftest [--frames N]

A reflex test for the interactive path: a block falls, arrows slide a
paddle along the bottom row, catching it scores and speeds the next one
up, three misses end the game.  Everything -- the keyboard, the screen,
the timing -- is machine code, so what it exercises is exactly what an
arcade program exercises: a keyboard-matrix read at 3840H once a frame,
video stores into 3C00H-3FFFH, and a T-state delay loop for the frame.
The score comes back through 0A9AH, so `S=USR(0)` returns it and the
same game at the same clock scores worse when input lags: a number, not
an impression.

It plays at the interpreter's clock, so set one before RUN -- `speed
1.77` at the prompt -- or the frame delay runs as fast as the host can.

The bytes are assembled here, not hand-counted: `Asm` looks every
instruction up in `z80.table.INVERSE` (signature -> encoding), resolves
labels in a second pass, and checks each instruction's length against
the table's own `length`.  The frame delay is derived from the table's
cycle column.  That exercises the assembler seam -- one declarative
opcode table, three consumers -- on something small, well before the
assembler itself.

Output is a listing whose DATA block carries a checksum, the way the
magazines did, so a damaged copy says so instead of crashing.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from z80.table import INVERSE                                  # noqa: E402

VIDEO = 0x3C00
ROWLEN = 64
ROWS = 16
PADROW = VIDEO + 15 * ROWLEN         # 3FC0H, the bottom row
BALLROW = VIDEO + ROWLEN             # 3C40H, row 1
KBD_ROW6 = 0x3840                    # ENTER CLEAR BREAK UP DOWN LEFT RIGHT SPACE
K_LEFT, K_RIGHT, K_SPACE = 32, 64, 128
CLS, ARG_HL, HL_RESULT = 0x01C9, 0x0A7F, 0x0A9A     # the three served ROM traps
SOLID, HALF_LOW, BLANK, DASH = 191, 176, 32, 45     # 191 = all six pixels, 176 = lower half
PAD_WIDTH = 4
PAD_STEP = 2
LIVES = 3
FALL_START = 8                       # frames a row, at the start
FALL_FLOOR = 2                       # fastest it gets
RAMP_EVERY = 3                       # catches between speed-ups
MHZ = 1.77408

TITLE = 'CATCH   ARROWS MOVE   SPACE QUITS   LIVES '
LIVE_OFF = len(TITLE)                # where the three markers start
HUD = TITLE + '*' * LIVES


class Asm:
    """A two-pass assembler over the opcode table's inverse index.

    `op('LD', ('A', '(nn)'), 0x3840)` looks up the signature, emits the
    encoding, then the immediates in operand order.  A string where an
    address or displacement belongs is a label, resolved in pass two.
    """

    def __init__(self, org):
        self.org = org
        self.out = bytearray()
        self.labels = {}
        self.fixups = []            # (offset, kind, label)
        self.listing = []

    @property
    def pc(self):
        return self.org + len(self.out)

    def label(self, name):
        if name in self.labels:
            raise KeyError('duplicate label %s' % name)
        self.labels[name] = self.pc
        return name

    def op(self, mnem, operands=(), *values):
        sig = (mnem, tuple(operands))
        if sig not in INVERSE:
            raise KeyError('no such instruction: %s %s' % (mnem, ','.join(operands)))
        enc, entry = INVERSE[sig]
        start = len(self.out)
        self.out += bytes(enc)
        vi = 0
        for o in entry.operands:
            if o.kind in ('imm8', 'port_imm'):
                self.out.append(values[vi] & 0xFF)
                vi += 1
            elif o.kind in ('imm16', 'aimm16'):
                v = values[vi]
                vi += 1
                if isinstance(v, str):
                    self.fixups.append((len(self.out), 'abs', v))
                    self.out += b'\0\0'
                else:
                    self.out += bytes((v & 0xFF, (v >> 8) & 0xFF))
            elif o.kind == 'rel':
                self.fixups.append((len(self.out), 'rel', values[vi]))
                vi += 1
                self.out.append(0)
            elif o.kind == 'idx':
                d = values[vi] & 0xFF
                vi += 1
                if len(enc) == 3 and enc[1] == 0xCB:      # DD CB d op: the displacement
                    self.out.insert(start + 2, d)         # sits before the last byte
                else:
                    self.out.append(d)
        if vi != len(values):
            raise ValueError('%s %s: %d values for %d operands needing one'
                             % (mnem, operands, len(values), vi))
        if len(self.out) - start != entry.length:
            raise AssertionError('%s %s: emitted %d bytes, the table says %d'
                                 % (mnem, operands, len(self.out) - start, entry.length))
        self.listing.append((self.org + start, bytes(self.out[start:]), mnem, operands))
        return self

    def db(self, *vals):
        for v in vals:
            if isinstance(v, str):
                self.out += v.encode('ascii')
            else:
                self.out.append(v & 0xFF)
        return self

    def dw(self, *vals):
        for v in vals:
            self.out += bytes((v & 0xFF, (v >> 8) & 0xFF))
        return self

    def space(self, n):
        self.out += bytes(n)
        return self

    def assemble(self):
        for off, kind, name in self.fixups:
            if name not in self.labels:
                raise KeyError('undefined label %s' % name)
            target = self.labels[name]
            if kind == 'abs':
                self.out[off] = target & 0xFF
                self.out[off + 1] = (target >> 8) & 0xFF
            else:
                disp = target - (self.org + off + 1)
                if not -128 <= disp <= 127:
                    raise ValueError('%s is %d bytes away, too far for a relative jump'
                                     % (name, disp))
                self.out[off] = disp & 0xFF
        return bytes(self.out)


def cycles_of(mnem, operands, taken=True):
    """The table's cost for one instruction, for the delay calibration."""
    c = INVERSE[(mnem, tuple(operands))][1].cycles
    return c[0] if taken or len(c) == 1 else c[1]


def delay_count(fps, overhead):
    """DE iterations for one frame: the loop costs 26 T-states a turn
    (DEC DE 6, LD A,D 4, OR E 4, JR NZ 12), read from the table."""
    per_turn = (cycles_of('DEC', ('DE',)) + cycles_of('LD', ('A', 'D'))
                + cycles_of('OR', ('E',)) + cycles_of('JR', ('NZ', 'd')))
    frame = MHZ * 1e6 / fps
    n = int((frame - overhead) / per_turn)
    return max(1, n), per_turn


def build(org, fps, scan=0):
    a = Asm(org)
    delay, per_turn = delay_count(fps, overhead=400)

    # ---- set up ---------------------------------------------------------
    a.op('CALL', ('nn',), CLS)
    a.op('LD', ('A', 'R'))                     # a seed with no ROM and no clock
    a.op('OR', ('A',))
    a.op('JR', ('NZ', 'd'), 'seeded')
    a.op('LD', ('A', 'n'), 0x5A)               # never let the LFSR sit at zero
    a.label('seeded')
    a.op('LD', ('(nn)', 'A'), 'SEED')
    a.op('LD', ('HL', 'nn'), 'HUDTEXT')        # the heads-up line into row 0
    a.op('LD', ('DE', 'nn'), VIDEO)
    a.op('LD', ('BC', 'nn'), len(HUD))
    a.op('LDIR', ())
    a.op('LD', ('A', 'n'), LIVES)
    a.op('LD', ('(nn)', 'A'), 'LIVES')
    a.op('LD', ('HL', 'nn'), 0)
    a.op('LD', ('(nn)', 'HL'), 'SCORE')
    a.op('LD', ('A', 'n'), (ROWLEN - PAD_WIDTH) // 2)
    a.op('LD', ('(nn)', 'A'), 'PADCOL')
    a.op('LD', ('(nn)', 'A'), 'OLDPAD')
    a.op('LD', ('A', 'n'), FALL_START)
    a.op('LD', ('(nn)', 'A'), 'FALLMAX')
    a.op('XOR', ('A',))
    a.op('LD', ('(nn)', 'A'), 'RAMP')
    a.op('LD', ('C', 'n'), HALF_LOW)
    a.op('LD', ('A', '(nn)'), 'PADCOL')
    a.op('CALL', ('nn',), 'PADDRAW')
    a.op('CALL', ('nn',), 'SPAWN')

    # ---- one frame ------------------------------------------------------
    a.label('FRAME')
    a.op('LD', ('A', '(nn)'), KBD_ROW6)        # the whole row in one read
    a.op('LD', ('B', 'A'))
    a.op('AND', ('n',), K_SPACE)
    a.op('JR', ('NZ', 'd'), 'QUIT')
    a.op('LD', ('A', 'B'))
    a.op('AND', ('n',), K_LEFT)
    a.op('JR', ('Z', 'd'), 'NOLEFT')
    a.op('LD', ('A', '(nn)'), 'PADCOL')
    a.op('CP', ('n',), PAD_STEP)
    a.op('JR', ('C', 'd'), 'NOLEFT')
    a.op('SUB', ('n',), PAD_STEP)
    a.op('LD', ('(nn)', 'A'), 'PADCOL')
    a.label('NOLEFT')
    a.op('LD', ('A', 'B'))
    a.op('AND', ('n',), K_RIGHT)
    a.op('JR', ('Z', 'd'), 'NORIGHT')
    a.op('LD', ('A', '(nn)'), 'PADCOL')
    a.op('CP', ('n',), ROWLEN - PAD_WIDTH - PAD_STEP + 1)
    a.op('JR', ('NC', 'd'), 'NORIGHT')
    a.op('ADD', ('A', 'n'), PAD_STEP)
    a.op('LD', ('(nn)', 'A'), 'PADCOL')
    a.label('NORIGHT')

    if scan:                                   # extra matrix rows, as a game
        a.op('LD', ('B', 'n'), scan)           # watching several keys would read
        a.label('SCANLOOP')
        a.op('LD', ('A', '(nn)'), 0x38FF)
        a.op('DJNZ', ('d',), 'SCANLOOP')

    # redraw only when it moved: four cells out, four cells in
    a.op('LD', ('A', '(nn)'), 'PADCOL')
    a.op('LD', ('HL', 'nn'), 'OLDPAD')
    a.op('CP', ('(HL)',))
    a.op('JR', ('Z', 'd'), 'PADOK')
    a.op('LD', ('C', 'n'), BLANK)
    a.op('LD', ('A', '(nn)'), 'OLDPAD')
    a.op('CALL', ('nn',), 'PADDRAW')
    a.op('LD', ('A', '(nn)'), 'PADCOL')
    a.op('LD', ('(nn)', 'A'), 'OLDPAD')
    a.op('LD', ('C', 'n'), HALF_LOW)
    a.op('CALL', ('nn',), 'PADDRAW')
    a.label('PADOK')

    a.op('LD', ('HL', 'nn'), 'FALLCNT')        # one row per FALLMAX frames
    a.op('DEC', ('(HL)',))
    a.op('JR', ('NZ', 'd'), 'NOFALL')
    a.op('LD', ('A', '(nn)'), 'FALLMAX')
    a.op('LD', ('(nn)', 'A'), 'FALLCNT')
    a.op('CALL', ('nn',), 'BALLSTEP')
    a.label('NOFALL')

    a.op('LD', ('DE', 'nn'), delay)            # the frame's own clock
    a.label('DLY')
    a.op('DEC', ('DE',))
    a.op('LD', ('A', 'D'))
    a.op('OR', ('E',))
    a.op('JR', ('NZ', 'd'), 'DLY')
    a.op('JP', ('nn',), 'FRAME')

    a.label('QUIT')
    a.op('LD', ('HL', '(nn)'), 'SCORE')
    a.op('JP', ('nn',), HL_RESULT)             # HL becomes the value of USR(0)

    # ---- the paddle: A = column, C = character ---------------------------
    a.label('PADDRAW')
    a.op('LD', ('HL', 'nn'), PADROW)
    a.op('LD', ('D', 'n'), 0)
    a.op('LD', ('E', 'A'))
    a.op('ADD', ('HL', 'DE'))
    a.op('LD', ('B', 'n'), PAD_WIDTH)
    a.label('PD1')
    a.op('LD', ('(HL)', 'C'))
    a.op('INC', ('HL',))
    a.op('DJNZ', ('d',), 'PD1')
    a.op('RET', ())

    # ---- the ball -------------------------------------------------------
    a.label('BALLSTEP')
    a.op('LD', ('HL', '(nn)'), 'BALLPTR')
    a.op('LD', ('(HL)', 'n'), BLANK)
    a.op('LD', ('DE', 'nn'), ROWLEN)
    a.op('ADD', ('HL', 'DE'))
    a.op('LD', ('(nn)', 'HL'), 'BALLPTR')
    a.op('LD', ('DE', 'nn'), PADROW)
    a.op('OR', ('A',))                         # clear carry for the compare
    a.op('SBC', ('HL', 'DE'))
    a.op('JR', ('NC', 'd'), 'LANDED')
    a.op('LD', ('HL', '(nn)'), 'BALLPTR')
    a.op('LD', ('(HL)', 'n'), SOLID)
    a.op('RET', ())

    a.label('LANDED')
    a.op('LD', ('A', '(nn)'), 'BALLCOL')
    a.op('LD', ('HL', 'nn'), 'PADCOL')
    a.op('CP', ('(HL)',))
    a.op('JR', ('C', 'd'), 'MISSED')           # left of the paddle
    a.op('SUB', ('(HL)',))
    a.op('CP', ('n',), PAD_WIDTH)
    a.op('JR', ('NC', 'd'), 'MISSED')          # right of it

    a.op('LD', ('HL', '(nn)'), 'SCORE')        # caught
    a.op('INC', ('HL',))
    a.op('LD', ('(nn)', 'HL'), 'SCORE')
    a.op('LD', ('HL', 'nn'), 'RAMP')
    a.op('INC', ('(HL)',))
    a.op('LD', ('A', '(HL)'))
    a.op('CP', ('n',), RAMP_EVERY)
    a.op('JR', ('C', 'd'), 'RESPAWN')
    a.op('LD', ('(HL)', 'n'), 0)
    a.op('LD', ('HL', 'nn'), 'FALLMAX')
    a.op('LD', ('A', '(HL)'))
    a.op('CP', ('n',), FALL_FLOOR + 1)
    a.op('JR', ('C', 'd'), 'RESPAWN')
    a.op('DEC', ('(HL)',))
    a.label('RESPAWN')
    a.op('CALL', ('nn',), 'SPAWN')
    a.op('RET', ())

    a.label('MISSED')
    a.op('LD', ('HL', 'nn'), 'LIVES')
    a.op('DEC', ('(HL)',))
    a.op('JR', ('Z', 'd'), 'GAMEOVER')
    a.op('LD', ('A', '(HL)'))                  # blank the marker just spent
    a.op('LD', ('HL', 'nn'), VIDEO + LIVE_OFF)
    a.op('LD', ('D', 'n'), 0)
    a.op('LD', ('E', 'A'))
    a.op('ADD', ('HL', 'DE'))
    a.op('LD', ('(HL)', 'n'), DASH)
    a.op('CALL', ('nn',), 'SPAWN')
    a.op('RET', ())

    a.label('GAMEOVER')
    a.op('LD', ('HL', 'nn'), VIDEO + LIVE_OFF)
    a.op('LD', ('(HL)', 'n'), DASH)
    a.op('LD', ('HL', '(nn)'), 'SCORE')
    a.op('JP', ('nn',), HL_RESULT)

    # ---- spawn and the random column -------------------------------------
    a.label('SPAWN')
    a.op('CALL', ('nn',), 'RND')
    a.op('AND', ('n',), ROWLEN - 1)
    a.op('LD', ('(nn)', 'A'), 'BALLCOL')
    a.op('LD', ('HL', 'nn'), BALLROW)
    a.op('LD', ('D', 'n'), 0)
    a.op('LD', ('E', 'A'))
    a.op('ADD', ('HL', 'DE'))
    a.op('LD', ('(nn)', 'HL'), 'BALLPTR')
    a.op('LD', ('(HL)', 'n'), SOLID)
    a.op('LD', ('A', '(nn)'), 'FALLMAX')
    a.op('LD', ('(nn)', 'A'), 'FALLCNT')
    a.op('RET', ())

    a.label('RND')                             # 8-bit Galois LFSR, x^8+x^4+x^3+x^2+1
    a.op('LD', ('A', '(nn)'), 'SEED')
    a.op('ADD', ('A', 'A'))
    a.op('JR', ('NC', 'd'), 'RND1')
    a.op('XOR', ('n',), 0x1D)
    a.label('RND1')
    a.op('LD', ('(nn)', 'A'), 'SEED')
    a.op('RET', ())

    # ---- data -------------------------------------------------------------
    a.label('HUDTEXT')
    a.db(HUD)
    a.label('SEED')
    a.db(0)
    a.label('PADCOL')
    a.db(0)
    a.label('OLDPAD')
    a.db(0)
    a.label('BALLCOL')
    a.db(0)
    a.label('BALLPTR')
    a.dw(0)
    a.label('FALLCNT')
    a.db(1)
    a.label('FALLMAX')
    a.db(FALL_START)
    a.label('RAMP')
    a.db(0)
    a.label('LIVES')
    a.db(LIVES)
    a.label('SCORE')
    a.dw(0)
    return a, a.assemble(), delay, per_turn


def listing(code, org, delay, fps):
    """The BASIC wrapper: a DATA loader with a checksum, in period style."""
    total = sum(code)
    out = ['10 REM CATCH -- A MACHINE-LANGUAGE REFLEX TEST FOR THE Z80 CORE',
           '20 REM ARROWS MOVE THE PADDLE, SPACE QUITS, THREE MISSES END IT',
           '30 REM SET THE CLOCK FIRST AT THE PROMPT:  speed 1.77',
           '40 E=%d : C=0' % org,
           '50 FOR I=0 TO %d : READ B : POKE E+I,B : C=C+B : NEXT' % (len(code) - 1),
           '60 IF C<>%d THEN PRINT "BAD DATA -- CHECK THE DATA LINES" : END' % total,
           '70 DEFUSR=E',
           '80 CLS : PRINT @ 540, "CATCH -- PRESS ENTER TO PLAY";',
           '90 INPUT A$',
           '100 S = USR(0)',
           '110 CLS : PRINT : PRINT "SCORE:"; S',
           '120 PRINT "RUN AGAIN TO PLAY AGAIN."',
           '130 END']
    ln = 1000
    for i in range(0, len(code), 16):
        out.append('%d DATA %s' % (ln, ','.join(str(b) for b in code[i:i + 16])))
        ln += 10
    return '\n'.join(out) + '\n'


def disasm(code, org):
    from z80.disasm import listing as dis_listing
    return dis_listing(code, base=org)


def selftest(code, org, labels, frames):
    """Play it headlessly in the core with a scripted keyboard.

    No interpreter and no terminal: this checks the routine's own logic
    at full speed, before anyone plays it by hand.
    """
    from z80.coprocess import Machine
    last, polls = {'line': ''}, {'n': 0}

    def send(s):
        last['line'] = s

    def recv():
        if not last['line'].startswith('K '):
            return 'OK'
        polls['n'] += 1
        n = polls['n']
        if n > frames:
            return 'K %d' % K_SPACE                     # quit, so run() returns
        # a bot that tracks the ball, so the catch path is exercised
        ball, pad = m.ram[labels['BALLCOL']], m.ram[labels['PADCOL']]
        want = max(0, min(ROWLEN - PAD_WIDTH, ball - PAD_WIDTH // 2))
        if pad + 1 < want:
            return 'K %d' % K_RIGHT
        if pad > want + 1:
            return 'K %d' % K_LEFT
        return 'K 0'

    m = Machine(send, recv, 0.0)
    for i, b in enumerate(code):
        m.ram[org + i] = b
        m.known[org + i] = 1
    m.run(org, 0, 0xFF00)
    scr = m.ram[VIDEO:VIDEO + ROWLEN * ROWS]
    print('+' + '-' * ROWLEN + '+')
    for r in range(ROWS):
        row = scr[r * ROWLEN:(r + 1) * ROWLEN]
        print('|' + ''.join(chr(b) if 32 <= b < 127 else ('#' if b >= 128 else ' ')
                            for b in row) + '|')
    print('+' + '-' * ROWLEN + '+')
    peek = lambda n: m.ram[labels[n]]
    print('%d frames played: score %d, lives %d, paddle col %d, ball col %d, a row every %d frames'
          % (polls['n'], m.cpu.hl, peek('LIVES'), peek('PADCOL'), peek('BALLCOL'), peek('FALLMAX')))
    print('result=%d (1 = score returned through 0A9AH); %d T-states, %.1f s emulated, %.0f T a frame'
          % (m.result, m.cycles, m.cycles / (MHZ * 1e6), m.cycles / max(1, polls['n'])))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--out', default=os.path.join(ROOT, 'demo', 'catch.bas'),
                    help='where the listing goes (default demo/catch.bas)')
    ap.add_argument('--org', type=int, default=32000,
                    help='where the routine is POKEd (default 32000)')
    ap.add_argument('--fps', type=int, default=30, help='frames a second (default 30)')
    ap.add_argument('--scan', type=int, default=0,
                    help='extra keyboard reads a frame, the stress knob (default 0)')
    ap.add_argument('--disasm', action='store_true', help='print the routine instead')
    ap.add_argument('--selftest', action='store_true',
                    help='play it headlessly in the core with a scripted keyboard')
    ap.add_argument('--frames', type=int, default=400, help='frames for --selftest')
    a = ap.parse_args()

    asm, code, delay, per_turn = build(a.org, a.fps, a.scan)
    if a.disasm:
        print(disasm(code, a.org))
        return 0
    if a.selftest:
        return selftest(code, a.org, asm.labels, a.frames)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, 'w') as f:
        f.write(listing(code, a.org, delay, a.fps))
    print('%s: %d bytes at %d, checksum %d, %d DATA values'
          % (a.out, len(code), a.org, sum(code), len(code)))
    print('%d keyboard reads a frame, %d a second at %d fps'
          % (1 + a.scan, (1 + a.scan) * a.fps, a.fps))
    print('frame delay %d turns of %d T-states = %.1f ms at %g MHz (%d fps)'
          % (delay, per_turn, delay * per_turn / (MHZ * 1e6) * 1e3, MHZ, a.fps))
    return 0


if __name__ == '__main__':
    sys.exit(main())
