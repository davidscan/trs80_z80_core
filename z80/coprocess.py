"""The USR coprocess -- the core's half of PROTOCOL.md, version 3.

`trs80basic` runs this as a `|&` coprocess named by `TRS80_Z80` and
drives it one USR call at a time: a frame of memory in, a write-set back,
video streamed and the keyboard served live during the call.  This
module is the machine around the pure CPU in `z80.cpu`: 64K of RAM that
reads 255 wherever no frame defined a byte, the address-dispatched
handling of program-counter entry into ROM space (the sentinel 2FFDH
ends the call, fifteen documented entry points are served as HLE traps,
anything else is `ERR rom`), ticks for BREAK and pacing, and the
line-oriented transport.

    python3 core.py                # what TRS80_Z80 names
    python3 core.py --fixture      # plus the z80.sh conformance routines

ROM SPACE HOLDS NO BYTES, by the never-commit-ROM rule.  A
routine may CALL the documented services below, and nothing else in
0000H-2FFFH: the trap reimplements the documented effect and performs
the RET the ROM routine would have.

    01C9H  CLS: the screen is filled with spaces and the cursor homed
           (4020H/4021H <- 3C00H).  A is used, as the ROM's is.
    0A7FH  the USR argument as a 16-bit integer in HL (the number the
           frame carried in `arg=`, rounded to a 24-bit single and then
           floored, as the ROM's CINT does -- the reference stub
           converts the same way); the integer and type flag 2 go to
           WRA1, so a plain RET after it makes USR that integer.  WRA1
           that is already an integer is only read: A = FFH.
    0A9AH  HL to WRA1 with type flag 2 (`result=1`), and the trap RETs
           to its caller as the ROM routine does (it ends in a plain
           RET; the ROM itself CALLs it).  The usual exit, JP 0A9AH,
           ends the call because that RET pops the sentinel; after a
           CALL 0A9AH the routine runs on.  The value of the USR
           expression is WRA1 as the routine leaves it, by the type flag
           (PROTOCOL.md "The return"): the write-set carries both.
    1A19H  the ROM's READY entry: the call ends and the reply carries
           `ready=1`, so BASIC ends the program at the prompt.
    002BH  the keyboard scan: A = the ASCII code of a key pressed since
           the last scan, else 0, through the work area at 4036H-403CH
           (Machine.scan_keyboard).  Built 2026-10-12 for Defense
           Command's high-score entry.
    0049H  wait for a key: 002BH until it reports one; A = its code.
    0060H  delay: BC counts ((BC - 1) * 26 + 17) T-states; BC and A
           return 0.
    01D3H  RANDOM: the refresh register R becomes the RND seed's middle
           byte (40ABH), and A.
    14C9H  RND: WRA1 (by the type flag at 40AFH) through CINT; 0 leaves
           a single 0 <= x < 1 in WRA1, n > 0 the integer 1..n, negative
           is ?FC (`ERR fc`).  The seed at 40AA-40ACH steps as BASIC's
           RND steps it, so the two share one sequence.
    05D9H  line input: HL = the buffer, B = its size; echoed on the
           screen at the cursor (4020H); ENTER or BREAK ends it (BREAK
           sets carry), with 0DH stored after the text, HL = the buffer,
           B = the characters typed, C = the size.
           The last five were built 2026-10-14 for Eliminator (Adventure
           International, 1981), from Farvour's chapter 2 descriptions
           and his notes on the routines.
    0033H  the character in A on the video, as BASIC's PRINT puts it
           there (Machine.display): characters, graphics, space
           compression and the control codes; the cursor at 4020H.
    033AH  0033H, and the cursor column to 40A6H.
    2B05H  WRA1 through 0A7FH into DE; HL kept, A = D, flags of OR A.
    0008H  RST 08H: JP 4000H, when something stored a vector there.
    0018H  RST 18H: JP 4006H likewise; with no vector, the ROM's
           compare of HL with DE (Z equal, C when HL < DE).
           These five were built 2026-10-14 for the games/ titles that
           call them (Cyborg, Stellar Escort, Missile Attack, Robot
           Attack, Defense Penetrator), from Farvour's notes on the
           routines (at 0008H, 0018H and 1C90H, 033AH, 0458H-058BH, 2B02H).

Port FFH reads 127 (the 64-character mode value the interpreter's INP
returns) and every other port 255.  OUT (FFH) has two effects and the
rest of the byte is discarded: bit 3 is the 32/64-column latch, reported
to the interpreter as a MODE line; bits 0-1 are the cassette output --
the machine's sound -- and, when a sound variable is set, every change
of them is stamped with its T-state position and rendered by
`z80.sound` to a player, a WAV file, or both.
The interpreter's display mode is not part of the frame, so a routine
reading port FFH in 32-character mode sees 127 here where BASIC's
INP(255) would say 63 -- recorded as the one known divergence.
"""

import math
import os
import signal
import sys
import time

from .cpu import Z80, SZ53, SZ53P, H, P, N, C
from .sound import from_env as sound_from_env

PROTO = '3'
NAME = 'trs80_z80_core'
SENTINEL = 0x2FFD


def csng(x):
    """The ROM's round to a 24-bit single (0796H, half up at the guard):
    a double is a single FIRST on its way to 16 bits (0A7FH -> 0AB9H), so
    CINT(2.9999999#) is 3, not 2 (ZL-7; the interpreter's sround)."""
    if x == 0:
        return 0.0
    ax = abs(x)
    e = math.floor(math.log2(ax))
    if 2.0 ** e > ax:
        e -= 1
    elif 2.0 ** (e + 1) <= ax:
        e += 1
    q = 2.0 ** (e - 23)
    r = math.floor(ax / q + 0.5) * q
    return -r if x < 0 else r
def single_add(a, b):
    """The ROM's single add (0716H) as the interpreter's sadd has it: the
    exact sum rounded, unless the operands are more than 8 binary places
    apart and not both whole numbers below 2^24; then the smaller is cut
    to one guard byte below the larger's 24 bits first, and a smaller one
    25 or more places down is lost.  RND(n) adds its 1 this way."""
    if b == 0:
        return a
    if a == 0:
        return b
    t, ab = abs(a), abs(b)
    if (ab * 256 >= t) if t >= ab else (t * 256 >= ab):
        return csng(a + b)
    if t < 16777216 and ab < 16777216 and a == int(a) and b == int(b):
        return csng(a + b)
    ea, eb = math.frexp(a)[1], math.frexp(b)[1]
    if ea < eb:
        a, b, ea, eb = b, a, eb, ea
    if ea - eb >= 25:
        return a
    g = 2.0 ** (ea - 32)
    cut = math.floor(abs(b) / g) * g
    return csng(a + (-cut if b < 0 else cut))


ROM_TOP = 0x3000
# The ROM entry points rom_entry() serves as traps (the sentinel apart):
# the USR argument and result exchange, CLS, READY and the keyboard scan.
# tools/romcalls.py reads this to say which of a library's ROM calls the
# core answers.
SERVED = (0x0A7F, 0x0A9A, 0x01C9, 0x1A19, 0x002B, 0x0049, 0x0060, 0x01D3,
          0x14C9, 0x05D9, 0x0008, 0x0018, 0x0033, 0x033A, 0x2B05)
# 002BH's last row, (unshifted, shifted): ENTER CLEAR BREAK UP DOWN LEFT
# RIGHT SPACE (scan_keyboard)
KEY_ROW6 = ((0x0D, 0x0D), (0x1F, 0x1F), (0x01, 0x01), (0x5B, 0x1B),
            (0x0A, 0x1A), (0x08, 0x18), (0x09, 0x19), (0x20, 0x20))
KEY_DEBOUNCE = (0x0DAC - 1) * 26 + 17      # 90,991 T-states, ~51 ms
# One idle pass of 0049H's loop (CALL 002BH, test, jump back): a nominal
# cost, so a wait for a key ticks (BREAK, pacing) at the machine's rate.
# An estimate; nothing a routine can observe depends on it.
KEY_WAIT_PASS = 300
# RND (14C9H): the 24-bit generator BASIC's RND uses (the interpreter's
# rnd_next): seed' = seed * 4253261 + 372837, mod 2^24.  The ROM keeps the
# multiplier in RAM at 4090H-4092H; neither side reads it from there.
RND_MUL, RND_ADD = 4253261, 372837
WRA1_LO, WRA1_HI = 0x411D, 0x4124
TYPE_FLAG = 0x40AF
CURSOR = 0x4020
# RST 08H and RST 18H jump through RAM vectors (0008H is JP 4000H, 0018H
# is JP 4006H; Farvour's notes on the restart vectors)
RST_VECTOR = {0x0008: 0x4000, 0x0018: 0x4006}
VIDEO_DRIVER = 0x401E          # the video DCB's driver address (401D-4024H)
ROM_VIDEO_DRIVER = 0x0458      # ... as the ROM sets it, and the interpreter seeds it
VIDEO_LO, VIDEO_HI = 0x3C00, 0x4000
KBD_LO, KBD_HI = 0x3800, 0x3900
TICK_TSTATES = 8870            # ~5 ms of emulated time at 1.774 MHz
TICK_SECONDS = 0.005           # ... and never more wall time than this at a slower clock
CLS_A = 0x1F                   # A after the ROM's CLS: 01CEH LD A,1FH (clear-to-end), 01D0H JP 033AH returns with it (ZM-5's nit; 1CH is the HOME byte it sends first)

# the machine code z80.sh expects to find behind the stub's canned entries
# (PROTOCOL.md "Conformance").  Real code; only the addresses are the
# fixture's business, see `Fixture`.
FIXTURE = {
    # 7000: paint "HI" at the top-left of the screen
    0x7000: bytes.fromhex('21003C' '3648' '23' '3649' 'C9'),
    # 7001: read the whole keyboard matrix, echo it at 3C40H, HL = byte
    0x7001: bytes.fromhex('3AFF38' '32403C' '6F' '2600' 'C39A0A'),
    # 7002: store "ABC" at the argument address
    0x7002: bytes.fromhex('CD7F0A' '3641' '23' '3642' '23' '3643' 'C9'),
    # 7003: HL = 2 * argument, returned as the result
    0x7003: bytes.fromhex('CD7F0A' '29' 'C39A0A'),
    # 7005: HL = the byte at the argument address
    0x7005: bytes.fromhex('CD7F0A' '6E' '2600' 'C39A0A'),
    # 7006: CALL 0000H -- ROM space, no ROM here
    0x7006: bytes.fromhex('CD0000'),
    # 7007: a sustained routine: 65536 turns of a 26 T-state loop
    0x7007: bytes.fromhex('010000' '0B' '78' 'B1' '20FB' 'C9'),
    # 7009: leave 1234H at SP-2/SP-1 and end at the sentinel
    0x7009: bytes.fromhex('D1' '213412' 'E5' 'E1' 'EB' 'E9'),
    # 700A: a video byte and an ordinary byte in one call
    0x700A: bytes.fromhex('3E41' '32283C' '3E01' '323075' 'C9'),
    # 700B: OUT (FFH),08H -- bit 3 set, 32-column mode
    0x700B: bytes.fromhex('3E08' 'D3FF' 'C9'),
    # 700C: OUT (FFH),00H -- bit 3 clear, 64-column mode
    0x700C: bytes.fromhex('3E00' 'D3FF' 'C9'),
    # 700D: OUT (FFH),08H (32-col) then CALL 01C9H (CLS, which restores 64-col)
    0x700D: bytes.fromhex('3E08' 'D3FF' 'CDC901' 'C9'),
    # 700E: store 42 at the argument address, then CALL 0000H: the store
    # reaches the interpreter ahead of the ERR
    0x700E: bytes.fromhex('CD7F0A' '362A' 'CD0000'),
    # 700F: a string argument (proto 3): DE = the descriptor at entry;
    # read length and data address, overwrite the first data byte with
    # 'Z' (5AH), HL = the length through 0A9AH
    0x700F: bytes.fromhex('EB' '46' '23' '5E' '23' '56' '78' 'B7'
                          '2803' '3E5A' '12' '68' '2600' 'C39A0A'),
    # 7010: LD HL,(4121H) -- what WRA1 holds: the seeded argument image,
    # a string's descriptor address, or what 0A7FH stored last
    0x7010: bytes.fromhex('2A2141' 'C39A0A'),
    # anything else the stub answers with a plain RET
    0x7777: bytes.fromhex('C9'),
}
FIXTURE_HANG = 0x7004          # never answers: the timeout path
FIXTURE_FORGET = 0x7008        # loses its state: the NEED full path
FIXTURE_BASE = 0x7100          # where the routines are laid out


class Break(Exception):
    """The interpreter answered a tick with BREAK."""


class CoreError(Exception):
    def __init__(self, code, text):
        Exception.__init__(self, text)
        self.code = code
        self.text = text


class EndCall(Exception):
    """PC reached the sentinel (or the READY entry)."""


class Machine:
    """RAM, devices and the run loop; transport-free so tests can drive it."""

    def __init__(self, send, recv, mhz=0.0, sound=None):
        self.send = send
        self.recv = recv
        self.mhz = mhz
        # A tick is the interpreter's proof of life -- its read guard gives
        # up after 5 s of silence -- and its BREAK poll.  Counted in
        # T-states alone, a paced slow clock stretched it: at `speed 0.001`
        # 8870 T-states are 8.9 s of wall time, so the guard fired in the
        # middle of a healthy routine and the core was declared dead (the
        # 2026-09-19 audit, L-46).  The interval is 5 ms of WALL time at
        # the paced clock, and never more T-states than before.  (Still out
        # of reach: a clock so slow that ONE instruction outlasts the guard,
        # under about 5 T-states a second.)
        self.tick_every = TICK_TSTATES
        if mhz > 0:
            self.tick_every = max(1, min(TICK_TSTATES, int(mhz * 1e6 * TICK_SECONDS)))
        self.sound = sound          # a z80.sound.Sound, or None: no capture at all
        self.bits = 0               # port FFH bits 0-1 as last written; carries across calls
        self.ram = bytearray(b'\xff' * 65536)
        self.known = bytearray(65536)   # see reset_ram
        self.gen = 0
        self.dirty = {}            # addr -> last value written, non-video
        self.video = {}            # addr -> last value written, video
        self.arg = 0
        self.result = 0
        self.ready = 0
        self.cpu = Z80(self.read, self.write, self.port_in, self.port_out)
        self.cycles = 0
        self.since_tick = 0
        self.wide = None
        self.wall0 = 0.0
        self.wra1_moved = False

    # ---- the bus ------------------------------------------------------
    def read(self, a):
        if KBD_LO <= a < KBD_HI:
            self.send('K %d' % (a & 0xFF))
            line = self.recv()
            if line.startswith('K '):
                try:
                    return int(line[2:]) & 0xFF
                except ValueError:
                    pass
            raise CoreError('bad', 'expected K <value>, got %r' % line)
        if a == 0x37E8 or a == 0x37E9:
            # printer status, ready -- the read side's rule 2 (dopeek):
            # the cell was plain RAM here, so a routine that wrote its
            # character to 37E8H read the character back as the status
            # and polled forever (ZL-6).  The write still lands in the
            # write-set, where the interpreter's read-only rule drops it.
            return 63
        return self.ram[a]

    def write(self, a, v):
        # 0000-2FFFH is the ROM: a store there changes nothing on the
        # machine, and PROTOCOL.md has the range holding no bytes on either
        # side.  It used to be kept here and sent back in the write-set,
        # where the interpreter copied it into its own memory (the
        # 2026-09-19 audit, L-45); poke_byte drops it too now.
        if a < ROM_TOP:
            return
        self.ram[a] = v
        self.known[a] = 1
        if WRA1_LO <= a <= WRA1_HI or a == TYPE_FLAG:
            self.wra1_moved = True
        if VIDEO_LO <= a < VIDEO_HI:
            self.video[a] = v
        else:
            self.dirty[a] = v

    def port_in(self, port):
        return 127 if (port & 0xFF) == 0xFF else 255

    def port_out(self, port, v):
        # OUT (FFH) bit 3 is the 32/64-column video latch (the same one
        # CHR$(23) sets from BASIC).  Tell the interpreter when it flips, so
        # a routine that clears 32-column mode for a full-width figure -- the
        # Dancing Demon after its intro text -- is drawn at the right width.
        # self.wide starts None each call, so the first OUT (FFH) always
        # states the mode explicitly (the core cannot know the interpreter's
        # entry width).  Pending video is flushed first so the switch lands
        # between the right frames.
        if (port & 0xFF) == 0xFF:
            # bits 0-1 are the cassette output, the machine's sound.  The
            # stamp is taken before step() adds this OUT's cost, so it marks
            # the START of the instruction: at most 12 T-states early, under
            # a sixth of a sample at 22,050 Hz.  With sound off this is one
            # attribute test.
            if self.sound is not None:
                bits = v & 3
                if bits != self.bits:
                    self.sound.transition(self.cycles, bits)
                    self.bits = bits
            nw = (v >> 3) & 1
            if nw != self.wide:
                self.flush_video()
                self.send('MODE %d' % nw)
                self.wide = nw

    # ---- frames -------------------------------------------------------
    def reset_ram(self):
        self.ram = bytearray(b'\xff' * 65536)
        # which bytes a frame or a routine has ever stored: the difference
        # between "no ROM here" and "no routine here" (FINDING 25: 25 of the
        # sweep's 89 ERRs were calls into memory nothing had written)
        self.known = bytearray(65536)
        self.cpu = Z80(self.read, self.write, self.port_in, self.port_out)

    def apply_run(self, run):
        addr, bs = run.split(':', 1)
        a = int(addr)
        ram, known = self.ram, self.known
        for i, b in enumerate(bs.split(',')):
            ram[(a + i) & 0xFFFF] = int(b)
            known[(a + i) & 0xFFFF] = 1

    # ---- streaming ----------------------------------------------------
    @staticmethod
    def runs(d):
        """Coalesce {addr: value} into ascending 'addr:b,b,b' runs."""
        out = []
        cur = None
        for a in sorted(d):
            if cur is not None and a == cur[0] + len(cur[1]):
                cur[1].append(d[a])
            else:
                cur = [a, [d[a]]]
                out.append(cur)
        return ['%d:%s' % (a, ','.join(str(b) for b in bs)) for a, bs in out]

    def flush_video(self):
        if self.video:
            for r in self.runs(self.video):
                self.send('V ' + r)
            self.video = {}

    def tick(self):
        self.flush_video()
        self.send('T %d' % self.since_tick)
        self.since_tick = 0
        reply = self.recv()
        if reply == 'BREAK':
            raise Break()
        if self.sound is not None:
            self.sound.tick(self.cycles)     # this tick's audio, before the sleep
        if self.mhz > 0:
            ahead = self.cycles / (self.mhz * 1e6) - (time.monotonic() - self.wall0)
            if ahead > 0.0005:
                time.sleep(ahead)

    # ---- ROM space: sentinel, traps, error ---------------------------------
    def rom_entry(self, pc):
        cpu = self.cpu
        if pc == SENTINEL:
            raise EndCall()
        if pc == 0x1A19:
            # the ROM's "READY" entry (022EH is EI / JP 1A19H, and a period
            # program ends with JP 1A19H to hand the machine back to BASIC):
            # the call ends, with no result -- and NOT like a RET: the
            # routine handed the machine to the READY prompt, so the BASIC
            # program that called it is over.  `ready=1` on the RET line
            # says so; without it the interpreter carried on with the next
            # statement as though the routine had returned (the 2026-09-19
            # audit, L-44).  The interpreter's SYSTEM `/` runs whole
            # programs this way, and at the prompt the two endings look the
            # same.  0000H (reset) stays `ERR rom`: it is the conformance
            # suite's canonical no-ROM call.
            self.ready = 1
            raise EndCall()
        if pc == 0x01C9:
            self.cls()
        elif pc == 0x0A7F:
            self.cint_entry()
        elif pc == 0x002B:
            self.scan_keyboard()
        elif pc in RST_VECTOR:
            # RST 08H and RST 18H: the ROM's 0008H is JP 4000H and its
            # 0018H JP 4006H, vectors in RAM (the ROM puts JP 1C96H and
            # JP 1C90H there: BASIC's syntax check, and the compare of HL
            # with DE).  A program that stores its own jump there uses the
            # RST as a one-byte call -- Robot Attack and Stellar Escort
            # (Big Five, 1980-81) do with RST 08H -- so a vector something
            # stored is followed, keeping the return address the RST
            # pushed.  A vector nothing stored is the ROM's own routine:
            # RST 18H's compare is served (Missile Attack, Adventure
            # International, 1980, uses it); RST 08H's syntax check reads
            # BASIC text and is not, so it stays ERR rom.
            vec = RST_VECTOR[pc]
            if self.known[vec]:
                cpu.pc = cpu.wz = vec
                return
            if pc == 0x0008:
                raise CoreError('rom', 'RST 08H jumps to 4000H, and nothing '
                                'stored a routine there (BASIC\'s syntax check is not served)')
            self.compare_hl_de()
        elif pc == 0x0033:
            cpu.a = self.display(cpu.a)
        elif pc == 0x033A:
            # 033AH: write to video -- 0033H, then the cursor COLUMN to
            # 40A6H (0348H: half the column in 32-character mode)
            cpu.a = self.display(cpu.a)
            col = self.cursor() & 0x3F
            self.write(0x40A6, (col >> 1) if self.video_flag() & 8 else col)
        elif pc == 0x2B05:
            # 2B05H, inside the ROM's "evaluate an expression as an
            # integer in DE" (2B02H): WRA1 through 0A7FH into DE, HL kept,
            # A = D with the flags of OR A (Farvour's notes there).  Defense
            # Penetrator (Cosmic, 1982) CALLs 14C9H and 0A7FH, then JP
            # 2B05H for its random numbers.
            hl = cpu.hl
            self.cint_entry()
            cpu.de = cpu.hl
            cpu.hl = hl
            cpu.a = cpu.d
            cpu.f = SZ53P[cpu.a]
        elif pc == 0x0049:
            self.wait_key()
        elif pc == 0x0060:
            self.delay()
        elif pc == 0x01D3:
            # RANDOM (Farvour p.24): the refresh register, as LD A,R reads
            # it, becomes the seed's middle byte at 40ABH
            cpu.a = cpu.r & 0xFF
            self.write(0x40AB, cpu.a)
        elif pc == 0x14C9:
            self.rnd()
        elif pc == 0x05D9:
            self.line_input()
        elif pc == 0x0A9A:
            # HL to the result, then the RET below: JP 0A9AH pops the
            # sentinel and ends the call, CALL 0A9AH returns to the routine.
            # The ROM routine is LD (4121H),HL / LD A,2 / LD (40AFH),A / RET,
            # so the routine that CALLed it finds the value in the
            # accumulator, the integer type flag and A = 2; the stores are
            # ordinary ones and come back in the write-set (both cells are
            # plain RAM on the interpreter's side).
            self.result = 1
            self.result_hl = cpu.hl
            self.write(0x4121, cpu.hl & 0xFF)
            self.write(0x4122, cpu.hl >> 8)
            cpu.a = 2
            self.write(0x40AF, 2)
        else:
            text = 'called %04XH, no ROM here' % pc
            if not self.known[self.entry]:
                # unwritten RAM reads FFH, RST 38H: the loader never ran,
                # or it is a SYSTEM tape the listing expects loaded already
                text += ' -- no routine at %04XH: its memory was never written' % self.entry
            raise CoreError('rom', text)
        # the RET the ROM routine would have done
        sp = cpu.sp
        cpu.pc = cpu.wz = self.ram[sp] | (self.ram[(sp + 1) & 0xFFFF] << 8)
        cpu.sp = (sp + 2) & 0xFFFF

    def cint_entry(self):
        """0A7FH: the USR argument (or WRA1, once a routine has moved it)
        as an integer in HL."""
        cpu = self.cpu
        # the ROM's CINT (0A7F-0AAF): a string is ?TM there (sent as
        # `ERR tm`, proto 3); a number is rounded to single first (a
        # double goes through 0AB9H at 0A87H), then floored, and an
        # exponent past 16 bits goes to 0AA3H, which accepts exactly
        # -32768 and otherwise exits through 07B2H, ?OV.  Sent as
        # `ERR ov`, which the interpreter raises as BASIC's ?OV (the
        # 2026-09-19 audit, L-43; ruled 2026-09-21).  On success the
        # ROM leaves the integer in WRA1 with the type flag 2 and
        # A = 2, ordinary stores that reach the write-set (ZM-4).
        # WRA1 that is ALREADY an integer leaves at 0A83H's RET M: HL =
        # (4121H), nothing stored, and A = FFH with RST 20H's flags
        # (25D9H: 2 - 3, OR A, SCF) (XL-2).
        # Once the routine (or a trap: 14C9H) has stored into WRA1 or
        # the type flag, 0A7FH converts WRA1 as it now stands, which is
        # what the ROM reads; until then the frame's `arg`, as before
        # (the two agree: the frame seeded WRA1 from it).  Eliminator
        # CALLs 14C9H and then 0A7FH to fetch RND's integer.
        if self.ram[TYPE_FLAG] < 3:
            cpu.hl = self.ram[0x4121] | self.ram[0x4122] << 8
            cpu.a = 0xFF
            cpu.f = SZ53P[0xFF] | C
            return
        if self.wra1_moved:
            v = self.cint(self.wra1(0x0A7F), '0A7FH')
        else:
            if self.argtype == 3:
                raise CoreError('tm', 'USR argument is a string at 0A7FH')
            v = int(csng(float(self.arg)) // 1)
            if v < -32768 or v > 32767:
                raise CoreError('ov', 'USR argument %s is outside -32768..32767 at 0A7FH' % self.arg)
        cpu.hl = v & 0xFFFF
        self.write(0x4121, cpu.hl & 0xFF)
        self.write(0x4122, cpu.hl >> 8)
        cpu.a = 2
        self.write(0x40AF, 2)

    def cls(self):
        """01C9H, CLS."""
        cpu = self.cpu
        for a in range(VIDEO_LO, VIDEO_HI):
            self.write(a, 0x20)
        self.write(0x4020, 0x00)
        self.write(0x4021, 0x3C)
        cpu.a = CLS_A
        # CLS returns the display to 64-column mode, as the ROM does and
        # as BASIC's own CLS does (s_cls in the interpreter's p20): the
        # driver clears bit 3 of its port-FFH image at 403DH and writes
        # the byte to the port.  Both halves matter.  The OUT emits
        # MODE 0 (the first OUT of a call always states the mode), so a
        # routine that printed 32-column text then cleared -- the
        # Dancing Demon's intro -- draws its figure at full width.  The
        # image byte reaches the interpreter in the write-set, where it
        # clears the ROM's 32-column PRINT flag: without it the BASIC
        # PRINTs that follow the call (the demon paints its stage that
        # way) still step two bytes and land on every other cell -- the
        # "background not clearing" seen 2026-09-15.
        flag = self.video_flag() & 0xF7
        self.write(0x403D, flag)
        self.port_out(0xFF, flag)
        # ... and zeroes the cursor COLUMN at 40A6H (0342H stores it on
        # the home byte's way through the driver): without this the
        # interpreter's TAB and POS pad from the stale pre-call column
        # (the 2026-09-26 audit, M-18/ZM-5)
        self.write(0x40A6, 0)

    def scan_keyboard(self):
        """002BH, the Level II keyboard scan (Farvour, "Scan Keyboard", p.15,
        and the driver at 03E3H-0457H): one instantaneous pass over rows
        3801H-3840H.  A key counts only when it was up at the previous scan:
        each row's bits are XORed with the copy in the work area at
        4036H-403CH, the row is stored there, and the first row with a new
        key -- lowest bit first -- ends the pass (later rows keep their old
        copies).  No new key: A = 0, and the flags the driver's last RLC C
        leaves (S only).  A new key: A = its code and the flags of CP 01H,
        after the 20 ms debounce the ROM waits.  BREAK (01H) goes through
        RST 28H, which returns at once on a machine without a DOS, so the
        caller gets 01H.  The driver restores BC, DE, HL and IX.

        The code is row * 8 + column + 40H, then:
          @ A-Z      SHIFT adds 20H (lower case); SHIFT with DOWN-ARROW held
                     subtracts 60H more (a control code)
          0-9 : ;    30H-3BH; SHIFT flips bit 4 (SHIFT-0 is a space)
          , - . /    2CH-2FH; SHIFT gives 3CH-3FH (< = > ?)
          last row   ENTER 0DH, CLEAR 1FH, BREAK 01H, UP 5BH, DOWN 0AH,
                     LEFT 08H, RIGHT 09H, SPACE 20H; SHIFT changes only the
                     arrows, to 1BH 1AH 18H 19H (the codes the Level II
                     manual gives; Farvour does not print the table)

        The interpreter's PEEK of 4036H-403CH reads 255 where the machine's
        start-up zeroed it, so the first scan of a session can miss a key
        already down; the stores reach the write-set, and later calls see
        the copies."""
        cpu = self.cpu
        code = None
        for r in range(7):
            row = self.read(0x3800 | (1 << r))
            new = (row ^ self.ram[0x4036 + r]) & row
            self.write(0x4036 + r, row)
            if new:
                col = (new & -new).bit_length() - 1
                code = r * 8 + col + 0x40
                break
        if code is None:
            cpu.a = 0
            cpu.f = 0x80
            return
        shift = self.read(0x3880) & 1
        if code < 0x60:                         # @ A-Z
            if shift:
                code += 0x20
                if self.read(0x3840) & 0x10:    # DOWN-ARROW held
                    code -= 0x60
        elif code < 0x70:                       # 0-9 : ; , - . /
            code -= 0x30
            if code >= 0x3C:
                code ^= 0x10
            if shift:
                code ^= 0x10
        else:                                   # the last row
            code = KEY_ROW6[code - 0x70][shift]
        # the debounce: 0060H with BC = 0DACH, ((BC - 1) * 26 + 17) T-states
        # by Farvour's formula (his comment says 20 ms; the loop is ~51 ms)
        self.cycles += KEY_DEBOUNCE
        self.since_tick += KEY_DEBOUNCE
        cpu.a = code
        r = (code - 1) & 0x1FF
        cpu.f = ((r & 0x80) | (0x40 if (r & 0xFF) == 0 else 0) | 0x02
                 | ((code ^ 1 ^ r) & 0x10) | (0x01 if code < 1 else 0)
                 | (0x04 if ((code ^ 1) & (code ^ r) & 0x80) else 0))

    # ---- time spent inside a trap -------------------------------------------
    def spend(self, t):
        """Charge t T-states the ROM routine would have taken, ticking as the
        run loop does, so BREAK, pacing and the interpreter's read guard see
        a long delay or a wait for a key as they see a loop of code."""
        while t > 0:
            n = min(t, max(1, self.tick_every - self.since_tick))
            self.cycles += n
            self.since_tick += n
            t -= n
            if self.since_tick >= self.tick_every:
                self.tick()

    def wait_key(self):
        """0049H (Farvour p.17): returns as soon as a key is pressed, its
        code in A; uses A, the flags and DE.  002BH, again and again."""
        while True:
            self.scan_keyboard()
            if self.cpu.a:
                return
            self.spend(KEY_WAIT_PASS)

    def delay(self):
        """0060H: a loop of BC passes, ((BC - 1) * 26 + 17) T-states by
        Farvour's note (BC = 0 is 65536 passes); it leaves BC = 0, A = 0
        and the flags of its last OR C (Z and P/V set)."""
        cpu = self.cpu
        n = cpu.bc or 0x10000
        self.spend((n - 1) * 26 + 17)
        cpu.bc = 0
        cpu.a = 0
        cpu.f = 0x44

    # ---- WRA1, the ROM's accumulator ------------------------------------------
    def wra1(self, where):
        """The number in WRA1 (411DH-4124H) as the type flag at 40AFH says:
        2 an integer in 4121/4122H, 4 a single in 4121-4124H, 8 a double in
        all eight (Microsoft binary format: exponent byte last, biased 128,
        0 meaning zero; the top mantissa bit is the sign).  A string is
        ?TM, as the ROM's CINT makes it.  Any other flag falls in RST 20H's
        classes (25D9H): below 3 an integer, 8 and up a double, the rest
        a single."""
        t = self.ram[TYPE_FLAG]
        r = self.ram
        if t < 3:
            v = r[0x4121] | r[0x4122] << 8
            return float(v - 0x10000 if v & 0x8000 else v)
        if t == 3:
            raise CoreError('tm', 'WRA1 holds a string at %04XH' % where)
        lo = 0x411D if t >= 8 else 0x4121
        exp = r[0x4124]
        if exp == 0:
            return 0.0
        bits = (0x4124 - lo) * 8
        mant = 0
        for a in range(0x4123, lo - 1, -1):
            mant = (mant << 8) | r[a]
        sign = mant >> (bits - 1)
        mant |= 1 << (bits - 1)
        v = mant / float(1 << bits) * 2.0 ** (exp - 128)
        return -v if sign else v

    def cint(self, x, where):
        """The ROM's CINT on a number: rounded to single, floored, ?OV
        outside -32768..32767 (as the 0A7FH trap converts `arg`)."""
        v = int(csng(x) // 1)
        if v < -32768 or v > 32767:
            raise CoreError('ov', '%s is outside -32768..32767 at %s' % (x, where))
        return v

    def put_single(self, x):
        """A single 0 <= x < 2^24 into WRA1 (4121-4124H), type flag 4."""
        b = [0, 0, 0, 0]
        if x > 0:
            e = 0
            while x >= 1.0:
                x /= 2.0
                e += 1
            while x < 0.5:
                x *= 2.0
                e -= 1
            m = int(x * (1 << 24) + 0.5)
            if m >= 1 << 24:
                m >>= 1
                e += 1
            b = [m & 0xFF, (m >> 8) & 0xFF, (m >> 16) & 0x7F, e + 128]
        for i in range(4):
            self.write(0x4121 + i, b[i])
        self.write(TYPE_FLAG, 4)

    def rnd(self):
        """14C9H, RND (Farvour p.27): the value in WRA1 through CINT; 0
        gives a single between 0 and 1 in WRA1, n > 0 an integer from 1 to
        n with the type flag 2, a negative one ?FC (`ERR fc`).  The draw is
        BASIC's own (the interpreter's RND, p60/p90): the 24-bit seed at
        40AA-40ACH steps once, x = seed / 2^24, and RND(n) is
        INT(x * n + 1) with the multiply and the add each rounded as a
        single.  The new seed is an ordinary store, so the write-set hands
        it back and BASIC's next RND carries on from it."""
        n = self.cint(self.wra1(0x14C9), '14C9H')
        if n < 0:
            raise CoreError('fc', 'RND of a negative number (%d) at 14C9H' % n)
        seed = self.read(0x40AA) | self.read(0x40AB) << 8 | self.read(0x40AC) << 16
        seed = (seed * RND_MUL + RND_ADD) & 0xFFFFFF
        self.write(0x40AA, seed & 0xFF)
        self.write(0x40AB, (seed >> 8) & 0xFF)
        self.write(0x40AC, seed >> 16)
        x = seed / 16777216.0
        if n == 0:
            self.put_single(x)
            return
        v = int(single_add(csng(x * n), 1.0) // 1)
        self.write(0x4121, v & 0xFF)
        self.write(0x4122, (v >> 8) & 0xFF)
        self.write(TYPE_FLAG, 2)

    def compare_hl_de(self):
        """RST 18H's routine (1C90H): H - D, and if they are equal L - E,
        with A and the flags of that SUB: Z if HL = DE, C if HL < DE."""
        cpu = self.cpu
        x, y = cpu.h, cpu.d
        if x == y:
            x, y = cpu.l, cpu.e
        r = (x - y) & 0xFF
        cpu.a = r
        cpu.f = (SZ53[r] | N | (H if (x & 0x0F) < (y & 0x0F) else 0)
                 | (P if (x ^ y) & (x ^ r) & 0x80 else 0) | (C if x < y else 0))

    # ---- 0033H, the video driver ---------------------------------------------
    def display(self, c):
        """0033H: the character in A on the video, through the ROM's video
        driver (0458H) as Farvour documents it (0458H-058BH), code for code
        with the interpreter's own PRINT (s_putc_drv, its p20), so a
        routine's text and BASIC's land alike:

          20H-BFH   stored at the cursor (as is, as PRINT stores it), which
                    steps on one byte, or two in 32-character mode;
                    past the last line the screen scrolls
          C0H-FFH   space compression: that many blanks, less C0H
          08H       back one (two in 32-character mode), blanking it
          0AH-0DH   to the start of the next line, which is blanked;
                    from the last line the screen scrolls
          0EH 0FH   cursor on, off: the cursor is the terminal's, as it is
                    for BASIC's CHR$(14), so nothing changes here
          17H       32 characters a line (bit 3 of 403DH, and the port)
          18H-1BH   the arrows: left and right stay in the line, up and
                    down wrap; none scrolls
          1CH       home, and back to 64 characters a line
          1DH       start of the line
          1EH 1FH   blank to the end of the line, of the screen
          others    ignored

        The registers the ROM's driver entry (03C2H) saves are kept; A
        comes back as the character.  A program that re-routed the video
        driver (401EH) gets ERR rom: only the ROM's driver is served.
        The Model III's codes 15H and 16H are not Level II's."""
        if self.known[VIDEO_DRIVER] and self.known[VIDEO_DRIVER + 1]:
            drv = self.read(VIDEO_DRIVER) | self.read(VIDEO_DRIVER + 1) << 8
            if drv != ROM_VIDEO_DRIVER:
                raise CoreError('rom', 'called 0033H with the video driver '
                                're-routed to %04XH: only the ROM\'s is served' % drv)
        a = self.cursor()
        wide = self.video_flag() & 8
        if c >= 0xC0:
            for _ in range(c - 0xC0):
                a = self.put_char(a, 0x20, wide)
        elif c >= 0x20:
            a = self.put_char(a, c, wide)
        elif c in (0x0A, 0x0B, 0x0C, 0x0D):
            a = VIDEO_LO + ((a - VIDEO_LO) // 64 + 1) * 64
            if a >= VIDEO_HI:
                a = self.scroll()          # the line scrolled in is blank
            else:
                for b in range(a, a + 64):
                    self.write(b, 0x20)
        elif c == 0x08:
            if a > VIDEO_LO:
                a = max(VIDEO_LO, a - (2 if wide else 1))
                self.write(a, 0x20)
        elif c == 0x17:
            flag = self.video_flag() | 8
            self.write(0x403D, flag)
            self.port_out(0xFF, flag)
            a = VIDEO_LO + ((a - VIDEO_LO + 1) & ~1) % 1024
        elif c == 0x18:
            for _ in range(2 if wide else 1):
                a = a + 63 if (a - VIDEO_LO) % 64 == 0 else a - 1
        elif c == 0x19:
            a += 1
            if (a - VIDEO_LO) % 64 == 0:
                a -= 64
        elif c == 0x1A:
            a = VIDEO_LO + (a - VIDEO_LO + 64) % 1024
        elif c == 0x1B:
            a = VIDEO_LO + (a - VIDEO_LO + 960) % 1024
        elif c == 0x1C:
            a = VIDEO_LO
            flag = self.video_flag() & 0xF7
            self.write(0x403D, flag)
            self.port_out(0xFF, flag)
        elif c == 0x1D:
            a = VIDEO_LO + (a - VIDEO_LO) // 64 * 64
        elif c == 0x1E:
            for b in range(a, VIDEO_LO + (a - VIDEO_LO) // 64 * 64 + 64):
                self.write(b, 0x20)
        elif c == 0x1F:
            for b in range(a, VIDEO_HI):
                self.write(b, 0x20)
        self.write(CURSOR, a & 0xFF)
        self.write(CURSOR + 1, a >> 8)
        return c

    def video_flag(self):
        """403DH, the ROM's image of the port-FFH bits (bit 3: 32 characters
        a line).  The interpreter's frame always carries it; with no frame
        (z80.run) it is 0, as the ROM leaves it at power-up, not the 255 of
        unwritten memory."""
        v = self.read(0x403D)
        return 0 if v == 0xFF and not self.known[0x403D] else v

    def put_char(self, a, c, wide):
        """One display byte at the cursor A; the next cursor.  In 32-character
        mode characters land on even bytes and step two."""
        if wide:
            a &= ~1
        self.write(a, c)
        a += 2 if wide else 1
        if a >= VIDEO_HI:
            a = self.scroll()
        return a

    # ---- 05D9H, a line from the keyboard ----------------------------------
    def cursor(self):
        a = self.read(CURSOR) | self.read(CURSOR + 1) << 8
        return a if VIDEO_LO <= a < VIDEO_HI else VIDEO_LO

    def set_cursor(self, a):
        self.write(CURSOR, a & 0xFF)
        self.write(CURSOR + 1, a >> 8)
        self.write(0x40A6, (a - VIDEO_LO) % 64)       # the column BASIC's POS reads

    def scroll(self):
        for a in range(VIDEO_LO, VIDEO_HI - 64):
            self.write(a, self.ram[a + 64])
        for a in range(VIDEO_HI - 64, VIDEO_HI):
            self.write(a, 0x20)
        return VIDEO_HI - 64

    def echo(self, c):
        """The few display codes line input sends (Farvour p.17): a
        character at the cursor, 08H backspace and erase, 0DH and 0AH to
        the next line, scrolling at the bottom.  Not the 0033H driver: no
        blinking cursor, no 32-column stepping."""
        a = self.cursor()
        if c == 0x08:
            if a > VIDEO_LO:
                a -= 1
                self.write(a, 0x20)
        elif c in (0x0D, 0x0A):
            a = VIDEO_LO + ((a - VIDEO_LO) // 64 + 1) * 64
            if a >= VIDEO_HI:
                a = self.scroll()
        else:
            self.write(a, c)
            a += 1
            if a >= VIDEO_HI:
                a = self.scroll()
        self.set_cursor(a)

    def line_input(self):
        """05D9H (Farvour p.16 and his notes on 05D9H-0673H): a line from
        the keyboard into the buffer at HL, at most B characters, echoed at
        the cursor.  ENTER or BREAK ends it: 0DH is stored after the text
        either way, and the routine returns HL = the buffer, B = the
        characters typed, C = the size, A = 0DH or 01H, carry set for
        BREAK.  CLEAR clears the screen and starts the line again;
        backspace (and SHIFT-left, to the start) erases, never back past a
        line feed; TAB pads with spaces to the next 8-column stop; a full
        buffer takes nothing more but ENTER and BREAK; SHIFT-right selects
        32 characters a line; other control codes are ignored."""
        cpu = self.cpu
        start = p = cpu.hl
        size = left = cpu.b
        while True:
            self.wait_key()
            k = cpu.a
            if k >= 0x20 or k == 0x0A:
                if left:
                    self.write(p, k)
                    p = (p + 1) & 0xFFFF
                    self.echo(k)
                    left -= 1
            elif k in (0x0D, 0x01):
                self.write(p, 0x0D)
                self.echo(0x0D)
                cpu.hl = start
                cpu.b = size - left
                cpu.c = size
                cpu.a = k
                cpu.f = 0x42 | (1 if k == 0x01 else 0)
                return
            elif k == 0x1F:
                self.cls()
                p, left = start, size
            elif k in (0x08, 0x18):
                while left != size and self.read((p - 1) & 0xFFFF) != 0x0A:
                    p = (p - 1) & 0xFFFF
                    self.echo(0x08)
                    left += 1
                    if k == 0x08:
                        break
            elif k == 0x09:
                for _ in range(8 - (self.cursor() - VIDEO_LO) % 8):
                    if not left:
                        break
                    self.write(p, 0x20)
                    p = (p + 1) & 0xFFFF
                    self.echo(0x20)
                    left -= 1
            elif k == 0x19:
                flag = self.read(0x403D) | 0x08
                self.write(0x403D, flag)
                self.port_out(0xFF, flag)

    # ---- one call ------------------------------------------------------------
    def run(self, entry, arg, sp, argtype=4, mbf=(0, 0, 0, 0, 0, 0, 0, 0)):
        cpu = self.cpu
        cpu.reset()
        self.arg = arg
        self.argtype = argtype
        self.entry = entry
        self.result = 0
        self.ready = 0
        self.result_hl = 0
        self.dirty = {}
        self.video = {}
        self.cycles = 0
        self.since_tick = 0
        self.wide = None
        self.wall0 = time.monotonic()
        # the state the ROM's USR dispatch leaves at the jump (27FE-2818,
        # proto 3 / ZM-4): A = the type from 40AFH (2 I, 3 $, 4 S, 8 D),
        # HL = the entry, DE = what HL held before 2814H's EX DE,HL: the
        # string's descriptor address for a string (2810H: 29DAH), and for
        # a number the continuation address 0890H it had just pushed
        # (2806H) (XL-2); the argument's WRA1 image (411D-4124H) and the
        # type flag are its stores, made here so they reach the write-set
        # like the 0A9AH trap's own.
        cpu.hl = entry
        cpu.a = argtype
        cpu.de = (int(float(arg)) & 0xFFFF) if argtype == 3 else 0x0890
        self.write(0x40AF, argtype)
        for i, b in enumerate(mbf[:8]):
            self.write((0x411D + i) & 0xFFFF, b & 0xFF)
        self.wra1_moved = False        # the frame's own seeding: WRA1 is still `arg`
        cpu.sp = sp
        cpu.sp = (cpu.sp - 2) & 0xFFFF
        self.write((cpu.sp + 1) & 0xFFFF, SENTINEL >> 8)
        self.write(cpu.sp, SENTINEL & 0xFF)
        cpu.pc = entry
        brk = 0
        step = cpu.step
        if self.sound is not None:
            self.sound.begin_call()
        try:
            try:
                while True:
                    if cpu.pc < ROM_TOP:
                        self.rom_entry(cpu.pc)
                        continue
                    n = step()
                    self.cycles += n
                    self.since_tick += n
                    if cpu.halted:
                        raise CoreError('halt', 'HALT at %04XH' % ((cpu.pc - 1) & 0xFFFF))
                    if self.since_tick >= self.tick_every:
                        self.tick()
            except EndCall:
                pass
            except Break:
                brk = 1
        finally:
            if self.sound is not None:
                self.sound.end_call(self.cycles)    # the last partial tick, on every exit
        self.flush_video()
        writes = self.runs(self.dirty)
        self.send('RET hl=%d result=%d cycles=%d break=%d writes=%d%s'
                  % (self.result_hl if self.result else cpu.hl,
                     self.result, self.cycles, brk, len(writes),
                     ' ready=1' if self.ready else ''))
        for w in writes:
            self.send('W ' + w)


class Fixture:
    """The z80.sh conformance routines, as machine code the frame never
    carried.  The stub's entry addresses are consecutive bytes, so a
    routine cannot start at each of them: the fixture lays the routines
    out from 7100H and maps each canned entry address to its routine.
    Two of the stub's behaviours are not machine code at all -- 7004H
    never answers (the timeout path) and 7008H forgets its state (the
    NEED path) -- and stay harness hooks here as they are in the stub."""

    def __init__(self):
        self.entry = {}
        self.image = {}
        a = FIXTURE_BASE
        for e in sorted(FIXTURE):
            self.entry[e] = a
            for b in FIXTURE[e]:
                self.image[a] = b
                a += 1

    def load(self, m):
        for a, b in self.image.items():
            m.ram[a] = b
            m.known[a] = 1


def fields(line):
    """The key=value pairs of a header line, by key."""
    return dict(kv.split('=', 1) for kv in line.split()[1:] if '=' in kv)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if '--version' in argv:
        from .version import version_text
        sys.stdout.write(version_text() + '\n')
        return 0
    fixture = Fixture() if '--fixture' in argv else None
    out = sys.stdout

    def send(s):
        out.write(s + '\n')
        out.flush()

    def recv():
        line = sys.stdin.readline()
        if not line:
            sys.exit(0)
        return line.rstrip('\r\n')

    hello = recv()
    if not hello.startswith('HELLO '):
        send('ERR bad expected HELLO')
        return 0
    h = fields(hello)
    proto = PROTO
    if fixture:
        # z80.sh's version-mismatch path uses the stub's knob; honour it
        # here so the same script drives the same path against a core.
        proto = os.environ.get('Z80_STUB_PROTO', PROTO)
    if proto != PROTO or h.get('proto') != PROTO:
        send('Z80 proto=%s name=%s pid=%d' % (proto, NAME, os.getpid()))
        return 0
    try:
        mhz = float(h.get('mhz', '0'))
    except ValueError:
        mhz = 0.0
    # sound, when asked for: the player starts now, at HELLO, so its
    # startup cost never delays the first notes; with a player and no
    # clock the call is paced at 1.77408 MHz (z80.sound).  The interpreter's
    # give-up path kills this process; SIGTERM then closes the sinks (the
    # WAV header, the player's pipe) on the way out.  BYE and EOF exit
    # cleanly through the same finally.
    snd, mhz = sound_from_env(os.environ, mhz)
    if snd is not None:
        try:
            signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
        except (ValueError, OSError, AttributeError):
            pass
    m = Machine(send, recv, mhz, snd)
    send('Z80 proto=%s name=%s pid=%d' % (proto, NAME, os.getpid()))
    try:
        return serve(m, recv, send, fixture)
    finally:
        if snd is not None:
            snd.close()


def serve(m, recv, send, fixture):
    while True:
        line = recv()
        if line == 'BYE':
            return 0
        if not line.startswith('CALL '):
            send('ERR bad expected CALL, got %r' % line[:40])
            continue
        h = fields(line)
        runs = []
        while True:
            l2 = recv()
            if l2 == 'GO':
                break
            if l2.startswith('M '):
                runs.append(l2[2:])
        try:
            gen = int(h['gen'])
            full = h['full'] == '1'
            entry = int(h['entry'])
            arg = float(h['arg'])              # 0A7FH floors it; 2.7 and -2.7 must still differ there
            sp = int(h['sp'])
            argtype = int(h.get('argtype', '4'))
            mbf = tuple(int(b) for b in h.get('mbf', '0,0,0,0,0,0,0,0').split(','))
        except (KeyError, ValueError) as e:
            send('ERR bad CALL header: %s' % e)
            continue
        if not math.isfinite(arg):
            # no BASIC number is one; nan reached 0A7FH and crashed the core
            send('ERR bad CALL header: arg=%s is not a number' % h['arg'])
            continue
        if not (0 <= entry <= 0xFFFF and 0 <= sp <= 0xFFFF):
            # an address off the map crashed the core with IndexError (ZL-5)
            send('ERR bad CALL header: entry/sp out of range: %d/%d' % (entry, sp))
            continue
        if not full and gen != m.gen + 1:
            send('NEED full')
            continue
        if full:
            m.reset_ram()
        m.gen = gen
        try:
            for r in runs:
                m.apply_run(r)
        except ValueError as e:
            send('ERR bad M line: %s' % e)
            continue
        if fixture:
            if entry == FIXTURE_HANG:
                time.sleep(30)
                continue
            if entry == FIXTURE_FORGET:
                m.gen = 0
                m.reset_ram()
                send('RET hl=0 result=0 cycles=0 break=0 writes=0')
                continue
            fixture.load(m)
            entry = fixture.entry.get(entry, entry)
        try:
            m.run(entry, arg, sp, argtype, mbf)
        except CoreError as e:
            # The routine's stores up to the error stay in this RAM, and the
            # next frame is a delta of what the INTERPRETER changed: unsent,
            # they would never be corrected and the two memories would
            # disagree for the rest of the session.  So they go out first,
            # as W lines, and the ERR ends the call (PROTOCOL.md, Errors).
            m.flush_video()
            for w in m.runs(m.dirty):
                send('W ' + w)
            m.dirty = {}
            send('ERR %s %s' % (e.code, e.text))


if __name__ == '__main__':
    sys.exit(main())
