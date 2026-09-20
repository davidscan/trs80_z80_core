"""The USR coprocess -- the core's half of PROTOCOL.md, version 1.

`trs80basic` runs this as a `|&` coprocess named by `TRS80_Z80` and
drives it one USR call at a time: a frame of memory in, a write-set back,
video streamed and the keyboard served live during the call.  This
module is the machine around the pure CPU in `z80.cpu`: 64K of RAM that
reads 255 wherever no frame defined a byte, the address-dispatched
handling of program-counter entry into ROM space (the sentinel 2FFDH
ends the call, three documented entry points are served as HLE traps,
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
           frame carried in `arg=`, truncated toward zero exactly as the
           reference stub truncates it).
    0A9AH  HL becomes the value of the USR expression (`result=1`), and
           the trap RETs to its caller as the ROM routine does (it ends
           in a plain RET; the ROM itself CALLs it).  The usual exit,
           JP 0A9AH, ends the call because that RET pops the sentinel;
           after a CALL 0A9AH the routine runs on, and the value stays
           the HL it handed over -- the last one, if it calls twice.

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

import os
import signal
import sys
import time

from .cpu import Z80
from .sound import from_env as sound_from_env

PROTO = '1'
NAME = 'trs80_z80_core'
SENTINEL = 0x2FFD
ROM_TOP = 0x3000
# The ROM entry points rom_entry() serves as traps (the sentinel apart):
# the USR argument and result exchange, CLS, and READY.  tools/romcalls.py
# reads this to say which of a library's ROM calls the core answers.
SERVED = (0x0A7F, 0x0A9A, 0x01C9, 0x1A19)
VIDEO_LO, VIDEO_HI = 0x3C00, 0x4000
KBD_LO, KBD_HI = 0x3800, 0x3900
TICK_TSTATES = 8870            # ~5 ms of emulated time at 1.774 MHz
CLS_A = 0x1C                   # the clear-screen control character

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
        self.sound = sound          # a z80.sound.Sound, or None: no capture at all
        self.bits = 0               # port FFH bits 0-1 as last written; carries across calls
        self.ram = bytearray(b'\xff' * 65536)
        self.known = bytearray(65536)   # see reset_ram
        self.gen = 0
        self.dirty = {}            # addr -> last value written, non-video
        self.video = {}            # addr -> last value written, video
        self.arg = 0
        self.result = 0
        self.cpu = Z80(self.read, self.write, self.port_in, self.port_out)
        self.cycles = 0
        self.since_tick = 0
        self.wide = None
        self.wall0 = 0.0

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
        return self.ram[a]

    def write(self, a, v):
        self.ram[a] = v
        self.known[a] = 1
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
            # the call ends like a RET, with no result.  The interpreter's
            # SYSTEM `/` runs whole programs this way.  0000H (reset) stays
            # `ERR rom`: it is the conformance suite's canonical no-ROM call.
            raise EndCall()
        if pc == 0x01C9:
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
            flag = self.read(0x403D) & 0xF7
            self.write(0x403D, flag)
            self.port_out(0xFF, flag)
        elif pc == 0x0A7F:
            cpu.hl = int(self.arg) & 0xFFFF
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

    # ---- one call ------------------------------------------------------------
    def run(self, entry, arg, sp):
        cpu = self.cpu
        cpu.reset()
        self.arg = arg
        self.entry = entry
        self.result = 0
        self.result_hl = 0
        self.dirty = {}
        self.video = {}
        self.cycles = 0
        self.since_tick = 0
        self.wide = None
        self.wall0 = time.monotonic()
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
                    if self.since_tick >= TICK_TSTATES:
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
        self.send('RET hl=%d result=%d cycles=%d break=%d writes=%d'
                  % (self.result_hl if self.result else cpu.hl,
                     self.result, self.cycles, brk, len(writes)))
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
            arg = int(float(h['arg']))
            sp = int(h['sp'])
        except (KeyError, ValueError) as e:
            send('ERR bad CALL header: %s' % e)
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
            m.run(entry, arg, sp)
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
