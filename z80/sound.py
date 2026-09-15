"""Machine-code sound: port FFH bits 0-1 rendered as audio.

The cassette output latch, bits 0-1 of port FFH, is the Model I's only
sound: a routine writes 1 and 2 alternately around delay loops and the
owner listened on the cassette AUX line (Barden, *Programming Techniques
for Level II BASIC*, figure 12-9; *More TRS-80 BASIC*, chapter 8).
`Machine.port_out` stamps every change of those two bits with its T-state
position; `Synth` here turns the stamped transitions into 16-bit mono
PCM; `WavSink` writes a file and `LiveSink` feeds a player command;
`Sound` is the coordinator the machine talks to.  With none of the sound
variables set nothing here runs and every protocol line is unchanged.

Levels: 0 is rest, 1 one polarity, 2 the other; 3 is treated as rest,
since no library text describes it (DESIGN.md decision 7).

Time base.  T-states convert to seconds at the clock from HELLO, or at
the LITERAL 1.77408 MHz when the interpreter sent 0, so an unpaced run
keeps true pitch and produces the same bytes as a paced one.  Every
sample boundary is an integer T-state, `(s * clock) // rate` for the
global sample index s, and the box filter integrates the level over that
window in integer arithmetic, so the output is byte-identical however
the rendering is chunked: a tick renders the complete samples up to its
T-state mark and leaves the partial one for the next.  The timeline is
EMULATED time only, calls butted together with no gap for the BASIC that
ran between them; the level, the sample phase and the DC blocker's state
carry across ticks and calls.

Configuration, read from the environment by `from_env`:

    TRS80_SOUND       player command, run through `sh -c`, fed raw
                      s16le mono PCM on stdin, stdout and stderr to
                      /dev/null; `{rate}` in it is replaced with the
                      sample rate; `auto` picks an installed player;
                      unset or empty means no live sound
    TRS80_SOUND_WAV   path of a WAV file to write; unset means none
    TRS80_SOUND_RATE  sample rate, default 22050

Live sound needs the core paced, since both players buffer seconds
ahead of a writer that does not: with a player set and `mhz` 0 the
coprocess paces at 1.77408 MHz.  A player that cannot be started or that
dies turns live sound off for the session, silently -- the core may not
write to the terminal, which the interpreter owns -- while emulation and
the WAV sink carry on.
"""

import array
import collections
import shutil
import subprocess
import sys
import threading
import time
import wave

DEFAULT_MHZ = 1.77408        # the literal, not 10.6445e6/6: awk's %.6g sends it exactly
DEFAULT_RATE = 22050
AMP = 9000                   # fixed amplitude with headroom: |y| stays under 2
LEVEL = (0, 1, -1, 0)        # bits 0-1 -> level

# the live writer's lead policy (seconds), see LiveSink
LEAD = 0.06                  # the stream runs this far ahead of wall-clock between calls
FLOOR = 0.015                # inside a call, silence is inserted only below this
GRAIN = 0.005                # and only enough to get back above it by this much


class Synth:
    """T-state-stamped level transitions to 16-bit mono PCM."""

    def __init__(self, clock, rate, amp=AMP):
        self.clock = int(clock)
        self.rate = int(rate)
        self.amp = amp
        self.hp = 1.0 - 110.0 / self.rate    # one-pole DC blocker, ~17 Hz corner
        self.s = 0                           # the next sample to render (global index)
        self.a = 0                           # its start T-state: (s * clock) // rate
        self.t0 = 0                          # the current call's origin in the global timeline
        self.total = 0                       # T-states of the calls completed so far
        self.tr = []                         # pending (global T-state, level), ascending
        self.lvl = 0                         # the level in force before tr[0]
        self.px = 0.0
        self.py = 0.0

    def begin_call(self):
        self.t0 = self.total

    def transition(self, cycles, bits):
        self.tr.append((self.t0 + cycles, LEVEL[bits & 3]))

    def render(self, cycles):
        """PCM for every complete sample up to `cycles` into the current call."""
        return self._render(self.t0 + cycles)

    def end_call(self, cycles):
        pcm = self._render(self.t0 + cycles)
        self.total = self.t0 + cycles
        return pcm

    def _render(self, upto):
        clock, rate = self.clock, self.rate
        tr = self.tr
        i, n = 0, len(tr)
        s, a, lvl = self.s, self.a, self.lvl
        px, py, hp, amp = self.px, self.py, self.hp, self.amp
        out = array.array('h')
        append = out.append
        while True:
            b = ((s + 1) * clock) // rate
            if b > upto:
                break
            acc = 0
            pos = a
            while i < n and tr[i][0] < b:
                t, l = tr[i]
                if t > pos:
                    acc += lvl * (t - pos)
                    pos = t
                lvl = l
                i += 1
            acc += lvl * (b - pos)
            x = acc / (b - a)
            y = x - px + hp * py
            px, py = x, y
            v = int(y * amp)
            if v > 32767:
                v = 32767
            elif v < -32767:
                v = -32767
            append(v)
            s += 1
            a = b
        del tr[:i]
        self.s, self.a, self.lvl, self.px, self.py = s, a, lvl, px, py
        if sys.byteorder == 'big':
            out.byteswap()
        return out.tobytes()


class WavSink:
    """A WAV file of the emulated timeline.  The header is patched after
    every write, so the file is valid however the session ends."""

    dead = False

    def __init__(self, path, rate):
        self.f = open(path, 'wb')            # opened here, so a bad path raises before wave holds it
        self.w = wave.open(self.f, 'wb')
        self.w.setnchannels(1)
        self.w.setsampwidth(2)
        self.w.setframerate(rate)

    def write(self, pcm):
        self.w.writeframes(pcm)

    def close(self):
        self.w.close()
        self.f.close()


class LiveSink:
    """A player command fed raw PCM by a writer thread.

    THE LEAD POLICY.  The stream position (samples handed to the player)
    is kept LEAD seconds ahead of wall-clock, measured from the moment the
    player started.  Between calls the writer tops the stream up with
    silence whenever it has fallen more than GRAIN below LEAD, so a call
    always starts with the same lead.  Inside a call the core's ticks
    supply real time's worth of PCM in 5 ms bursts, which the lead
    absorbs; the writer inserts silence only if the stream falls below
    FLOOR -- a stall longer than LEAD - FLOOR -- and then only enough to
    reach FLOOR + GRAIN, because every sample of silence inserted mid-call
    pushes the rest of that call's audio out permanently.  Silence is never
    written merely because the queue is empty.

    The player runs through `sh -c` in its own session, with stdout and
    stderr on /dev/null, and exits on EOF when the pipe closes.  A broken
    pipe marks the sink dead; the caller drops it and carries on.
    `clock` and `thread` are for tests: a scripted clock and calling
    `pump` by hand make the policy checkable byte for byte."""

    def __init__(self, cmd, rate, clock=time.monotonic, thread=True):
        self.rate = rate
        self.clock = clock
        self.dead = False
        self.in_call = False
        self.stopping = False
        self.written = 0                     # samples handed to the player
        self.q = collections.deque()
        self.cv = threading.Condition()
        self.p = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  start_new_session=True)
        self.t0 = clock()
        self.th = None
        if thread:
            self.th = threading.Thread(target=self._loop, name='sound-writer', daemon=True)
            self.th.start()

    def write(self, pcm):
        with self.cv:
            self.q.append(pcm)
            self.cv.notify()

    def pump(self, now):
        """One writer pass.  Pending PCM goes out as it is; otherwise silence
        restores the lead by the policy above.  Returns the seconds until
        the stream next needs attention (0 = again as soon as possible)."""
        with self.cv:
            pending = b''.join(self.q)
            self.q.clear()
        if pending:
            self._out(pending)
            return 0.0
        ahead = self.written / self.rate - (now - self.t0)
        if self.in_call:
            if ahead < FLOOR:
                self._out(bytes(2 * int((FLOOR + GRAIN - ahead) * self.rate)))
                return 0.0
            return ahead - FLOOR
        if ahead < LEAD - GRAIN:
            self._out(bytes(2 * int((LEAD - ahead) * self.rate)))
            return 0.0
        return ahead - (LEAD - GRAIN)

    def _out(self, data):
        if self.dead or not data:
            return
        try:
            self.p.stdin.write(data)
            self.p.stdin.flush()
        except (OSError, ValueError):         # broken pipe, or a closed stdin
            self.dead = True
            return
        self.written += len(data) // 2

    def _loop(self):
        while not self.stopping and not self.dead:
            wait = self.pump(self.clock())
            with self.cv:
                if self.q or self.stopping:
                    continue
                self.cv.wait(min(max(wait, 0.001), 0.02))

    def close(self):
        self.stopping = True
        with self.cv:
            self.cv.notify()
        if self.th is not None:
            self.th.join(1.0)
        try:
            self.p.stdin.close()
        except OSError:
            pass
        try:
            self.p.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            self.p.kill()
            self.p.wait()


class Sound:
    """The synthesizer and its sinks, as the machine sees them."""

    def __init__(self, synth, sinks):
        self.synth = synth
        self.sinks = list(sinks)

    @property
    def live(self):
        return any(isinstance(k, LiveSink) and not k.dead for k in self.sinks)

    def begin_call(self):
        self.synth.begin_call()
        for k in self.sinks:
            k.in_call = True

    def transition(self, cycles, bits):
        self.synth.transition(cycles, bits)

    def tick(self, cycles):
        self._emit(self.synth.render(cycles))

    def end_call(self, cycles):
        self._emit(self.synth.end_call(cycles))
        for k in self.sinks:
            k.in_call = False

    def _emit(self, pcm):
        if not pcm:
            return
        for k in self.sinks:
            k.write(pcm)
        if any(k.dead for k in self.sinks):
            for k in self.sinks:
                if k.dead:
                    k.close()
            self.sinks = [k for k in self.sinks if not k.dead]

    def close(self):
        for k in self.sinks:
            k.close()
        self.sinks = []


def default_player(rate):
    """The `auto` player: ffplay wherever it is installed (the cross-platform
    choice; S-9 on 2026-09-15 heard it in step with the picture), else
    ffmpeg's AudioToolbox device on macOS, aplay or pw-play; None if none
    is installed."""
    fmt = '-f s16le -ar %d -ch_layout mono -i -' % rate
    if shutil.which('ffplay'):
        return 'ffplay -nodisp -autoexit -loglevel quiet %s' % fmt
    if sys.platform == 'darwin' and shutil.which('ffmpeg'):
        return 'ffmpeg -hide_banner -loglevel quiet %s -f audiotoolbox -' % fmt
    if shutil.which('aplay'):
        return 'aplay -q -f S16_LE -r %d -c 1' % rate
    if shutil.which('pw-play'):
        return 'pw-play --rate %d --channels 1 --format s16 -' % rate
    return None


def from_env(env, mhz):
    """(Sound or None, the clock to pace at) from the three variables."""
    player = env.get('TRS80_SOUND', '').strip()
    wav = env.get('TRS80_SOUND_WAV', '').strip()
    if not player and not wav:
        return None, mhz
    try:
        rate = int(env.get('TRS80_SOUND_RATE', '').strip() or DEFAULT_RATE)
    except ValueError:
        rate = DEFAULT_RATE
    if not 8000 <= rate <= 192000:
        rate = DEFAULT_RATE
    sinks = []
    if wav:
        try:
            sinks.append(WavSink(wav, rate))
        except (OSError, wave.Error):
            pass
    if player:
        cmd = default_player(rate) if player == 'auto' else player.replace('{rate}', str(rate))
        if cmd:
            try:
                sinks.append(LiveSink(cmd, rate))
            except OSError:
                pass
    if not sinks:
        return None, mhz
    if mhz <= 0 and any(isinstance(k, LiveSink) for k in sinks):
        mhz = DEFAULT_MHZ                    # live sound needs pacing
    clock = int(round((mhz if mhz > 0 else DEFAULT_MHZ) * 1e6))
    return Sound(Synth(clock, rate), sinks), mhz
