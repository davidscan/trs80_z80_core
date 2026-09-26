"""Machine-code sound (z80/sound.py), without speakers.

Synth: pitch of synthetic square waves within 0.1%, sample counts, the
level map, the box filter at a window boundary, the DC blocker settling,
silence with no transitions, and chunked output equal to one-shot output
byte for byte -- across ticks and across calls.  Machine: a self-written
OUT/DJNZ/OUT/DJNZ routine (never a listing's bytes) for several delay
values, the WAV's pitch equal to clock / (26*D + 38) within 0.5% and its
bytes identical paced and unpaced.  LiveSink: the lead policy checked
byte for byte with a scripted clock and `cat` as the player, and a dead
player dropping out without failing the call.  Transport: core.py's
protocol lines byte-identical with and without the sound variables.
"""

import array
import os
import subprocess
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from z80.sound import (Synth, Sound, WavSink, LiveSink, from_env, default_player,   # noqa: E402
                       DEFAULT_MHZ, AMP, LEAD, FLOOR, GRAIN)
from z80.coprocess import Machine   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, 'core.py')
CLOCK = 1774080          # 1.77408 MHz, the literal
RATE = 22050


def square(freq, seconds, clock=CLOCK):
    """(transitions, total T-states) of a square wave: bits 1, 2, 1, 2 ..."""
    half = clock / (2 * freq)
    tr, t, k = [], 0.0, 0
    end = seconds * clock
    while t < end:
        tr.append((int(round(t)), 1 if k % 2 == 0 else 2))
        t += half
        k += 1
    return tr, int(end)


def pitch(pcm, rate=RATE):
    a = array.array('h', pcm)
    if sys.byteorder == 'big':
        a.byteswap()
    ups = [i for i in range(1, len(a)) if a[i - 1] < 0 <= a[i]]
    return (len(ups) - 1) / ((ups[-1] - ups[0]) / rate) if len(ups) > 2 else 0.0


def samples(pcm):
    a = array.array('h', pcm)
    if sys.byteorder == 'big':
        a.byteswap()
    return a


def one_shot(tr, total, rate=RATE, clock=CLOCK):
    sy = Synth(clock, rate)
    sy.begin_call()
    for t, b in tr:
        sy.transition(t, b)
    return sy.end_call(total)


def routine(d, passes=1):
    """LD D,d / LD C,FFH / LD HL,0201H / LD A,passes / LD E,0 /
    loop: OUT (C),H / LD B,D / DJNZ $ / OUT (C),L / LD B,D / DJNZ $ /
    DEC E / JR NZ,loop / DEC A / JR NZ,loop / RET -- one cycle of the
    wave costs 26*D + 38 T-states, the Dancing Demon's shape."""
    return bytes([0x16, d, 0x0E, 0xFF, 0x21, 0x01, 0x02, 0x3E, passes, 0x1E, 0x00,
                  0xED, 0x61, 0x42, 0x10, 0xFE, 0xED, 0x69, 0x42, 0x10, 0xFE, 0x1D, 0x20, 0xF3,
                  0x3D, 0x20, 0xF0, 0xC9])


class TestSynth(unittest.TestCase):

    def test_square_wave_pitch_within_0_1_percent(self):
        for rate in (22050, 44100):
            for f in (261.63, 440.0, 2000.0):
                tr, total = square(f, 2.0)
                got = pitch(one_shot(tr, total, rate), rate)
                self.assertAlmostEqual(got / f, 1.0, delta=0.001, msg='%d Hz at %d' % (f, rate))

    def test_a_clock_slower_than_the_sample_rate_renders(self):
        """Below `rate` Hz two sample boundaries fall on one T-state and the
        sample between them spans no time: it takes the level in force.  It
        used to divide by zero and kill the core -- `speed 0.01` with a WAV
        set (the 2026-09-19 audit, L-46)."""
        s = Synth(10000, RATE)
        s.begin_call()
        s.transition(3, 1)
        s.transition(40, 2)
        pcm = s.end_call(100)
        # boundaries are whole T-states, (s * clock) // rate, so at a clock
        # this coarse the count runs a sample or two past the exact 220.5
        self.assertAlmostEqual(len(pcm) // 2, 100 * RATE / 10000, delta=3)

    def test_sample_count_is_floor_of_emulated_time(self):
        self.assertEqual(len(one_shot([], CLOCK)), 2 * RATE)
        self.assertEqual(len(one_shot([], CLOCK - 1)), 2 * (RATE - 1))
        self.assertEqual(len(one_shot([], 0)), 0)

    def test_level_map(self):
        n = 1000
        self.assertEqual(samples(one_shot([(0, 1)], n))[0], AMP)
        self.assertEqual(samples(one_shot([(0, 2)], n))[0], -AMP)
        self.assertEqual(one_shot([(0, 3)], n), bytes(2 * (n * RATE // CLOCK)))   # 3 is rest
        self.assertEqual(one_shot([(0, 0)], n), bytes(2 * (n * RATE // CLOCK)))

    def test_box_filter_at_a_window_boundary(self):
        # the first window is [0, 80): a level change at 40 averages to half
        self.assertEqual((1 * CLOCK) // RATE, 80)
        self.assertEqual(samples(one_shot([(40, 1)], 160))[0], AMP // 2)
        self.assertEqual(samples(one_shot([(20, 1)], 160))[0], AMP * 3 // 4)   # high for 60 of 80
        self.assertEqual(samples(one_shot([(80, 1)], 160))[0], 0)

    def test_dc_blocker_settles(self):
        s = samples(one_shot([(0, 1)], CLOCK))       # level held for one second
        self.assertEqual(s[0], AMP)
        self.assertLess(abs(s[-1]), 1)
        self.assertLess(abs(s[RATE // 2]), AMP // 100)

    def test_silence_with_no_transitions(self):
        self.assertEqual(one_shot([], CLOCK // 10), bytes(2 * (CLOCK // 10 * RATE // CLOCK)))

    def test_chunked_equals_one_shot_across_ticks(self):
        tr, total = square(440.0, 0.5)
        ref = one_shot(tr, total)
        sy = Synth(CLOCK, RATE)
        sy.begin_call()
        for t, b in tr:
            sy.transition(t, b)
        out = b''
        for mark in list(range(8870, total, 8870)) + [total // 3 + 37, total - 1]:
            out += sy.render(mark)               # marks inside samples, and out of order
        out += sy.end_call(total)
        self.assertEqual(out, ref)

    def test_chunked_equals_one_shot_across_calls(self):
        tr, total = square(700.0, 0.4)
        ref = one_shot(tr, total)
        cut = total * 2 // 5 + 13                # not on a sample boundary
        sy = Synth(CLOCK, RATE)
        sy.begin_call()
        for t, b in tr:
            if t < cut:
                sy.transition(t, b)
        out = sy.render(cut // 2) + sy.end_call(cut)
        sy.begin_call()
        for t, b in tr:
            if t >= cut:
                sy.transition(t - cut, b)
        out += sy.render(cut) + sy.end_call(total - cut)
        self.assertEqual(out, ref)

    def test_cost_is_a_small_fraction_of_real_time(self):
        import time
        tr, total = square(672.0, 2.0)
        t0 = time.perf_counter()
        one_shot(tr, total)
        self.assertLess(time.perf_counter() - t0, 1.0)     # 2 s of audio in under 1 s


def wav_pcm(path):
    w = wave.open(path, 'rb')
    try:
        self_check = (w.getnchannels(), w.getsampwidth(), w.getframerate())
        return self_check, w.readframes(w.getnframes())
    finally:
        w.close()


class TestMachine(unittest.TestCase):

    def run_wav(self, code, mhz, replies=None):
        fd, path = tempfile.mkstemp(suffix='.wav')
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.unlink(path))
        rep = list(replies or [])
        snd = Sound(Synth(CLOCK, RATE), [WavSink(path, RATE)])
        m = Machine(lambda s: None, lambda: rep.pop(0) if rep else 'OK', mhz, snd)
        m.ram[0x7100:0x7100 + len(code)] = code
        m.run(0x7100, 0, 0xFF00)
        snd.close()
        hdr, pcm = wav_pcm(path)
        self.assertEqual(hdr, (1, 2, RATE))
        return m, pcm

    def test_routine_pitch_and_paced_equals_unpaced(self):
        for d in (50, 100, 200):
            m0, pcm0 = self.run_wav(routine(d), 0.0)
            m1, pcm1 = self.run_wav(routine(d), DEFAULT_MHZ)
            self.assertEqual(pcm0, pcm1, 'D=%d' % d)
            self.assertEqual(m0.cycles, m1.cycles)
            self.assertEqual(len(pcm0), 2 * (m0.cycles * RATE // CLOCK))
            want = CLOCK / (26 * d + 38)
            self.assertAlmostEqual(pitch(pcm0) / want, 1.0, delta=0.005, msg='D=%d' % d)

    def test_break_still_renders_every_tick(self):
        m, pcm = self.run_wav(routine(100), 0.0, replies=['OK', 'OK', 'BREAK'])
        self.assertEqual(len(pcm), 2 * (m.cycles * RATE // CLOCK))
        self.assertGreater(len(pcm), 0)

    def test_no_sound_means_no_capture(self):
        m = Machine(lambda s: None, lambda: 'OK')
        m.ram[0x7100:0x7100 + 28] = routine(50)
        m.run(0x7100, 0, 0xFF00)
        self.assertIsNone(m.sound)

    def test_level_carries_across_calls(self):
        fd, path = tempfile.mkstemp(suffix='.wav')
        os.close(fd)
        self.addCleanup(os.unlink, path)
        snd = Sound(Synth(CLOCK, RATE), [WavSink(path, RATE)])
        m = Machine(lambda s: None, lambda: 'OK', 0.0, snd)
        # OUT (FFH),1 ; RET  -- then a second call that outputs 1 again (no change)
        m.ram[0x7100:0x7104] = bytes.fromhex('3E01' 'D3FF' 'C9')
        m.run(0x7100, 0, 0xFF00)
        n1 = len(snd.synth.tr)
        m.run(0x7100, 0, 0xFF00)
        self.assertEqual(m.bits, 1)
        self.assertEqual(len(snd.synth.tr), n1)      # the same level: no new transition
        snd.close()


class TestLiveSink(unittest.TestCase):

    def cat_sink(self, clock):
        fd, path = tempfile.mkstemp(suffix='.pcm')
        os.close(fd)
        self.addCleanup(os.unlink, path)
        return LiveSink('cat > %s' % path, RATE, clock=clock, thread=False), path

    def test_lead_policy_byte_for_byte(self):
        now = [100.0]
        sink, path = self.cat_sink(lambda: now[0])
        pcm_a = b'\x01\x00' * 110
        pcm_b = b'\x02\x00' * 110
        # between calls, an empty stream is filled to LEAD
        sink.pump(now[0])
        fill1 = int(LEAD * RATE)
        self.assertEqual(sink.written, fill1)
        # topped up only once it has fallen more than GRAIN below LEAD
        now[0] += GRAIN / 2
        sink.pump(now[0])
        self.assertEqual(sink.written, fill1)
        now[0] += GRAIN
        sink.pump(now[0])
        fill2 = int((LEAD - (fill1 / RATE - 1.5 * GRAIN)) * RATE)
        self.assertEqual(sink.written, fill1 + fill2)
        # a call: PCM within the lead goes out with nothing inserted
        sink.in_call = True
        now[0] += 0.005
        sink.write(pcm_a)
        sink.pump(now[0])
        self.assertEqual(sink.written, fill1 + fill2 + 110)
        # a stall longer than LEAD - FLOOR: silence to FLOOR + GRAIN, then the late PCM as is
        now[0] += LEAD
        sink.pump(now[0])
        ahead = (fill1 + fill2 + 110) / RATE - (now[0] - 100.0)
        self.assertLess(ahead, FLOOR)
        gap = int((FLOOR + GRAIN - ahead) * RATE)
        self.assertEqual(sink.written, fill1 + fill2 + 110 + gap)
        sink.write(pcm_b)
        sink.pump(now[0])
        sink.close()
        self.assertEqual(sink.p.returncode, 0)
        with open(path, 'rb') as f:
            got = f.read()
        self.assertEqual(got, bytes(2 * fill1) + bytes(2 * fill2) + pcm_a + bytes(2 * gap) + pcm_b)

    def test_dead_player_drops_out_and_the_call_completes(self):
        sink = LiveSink('cat > /dev/null', RATE, thread=False)
        sink.p.kill()
        sink.p.wait()
        snd = Sound(Synth(CLOCK, RATE), [sink])
        out = []
        m = Machine(out.append, lambda: 'OK', 0.0, snd)
        m.ram[0x7100:0x7100 + 28] = routine(50)
        m.run(0x7100, 0, 0xFF00)
        self.assertTrue(any(l.startswith('RET ') for l in out))
        sink.pump(0.0)                        # the writer's pass (no thread here): broken pipe
        self.assertTrue(sink.dead)
        m.run(0x7100, 0, 0xFF00)              # the next audio drops the dead sink
        self.assertEqual(len([l for l in out if l.startswith('RET ')]), 2)
        self.assertEqual(snd.sinks, [])
        self.assertFalse(snd.live)
        snd.close()

    def test_close_sends_eof_and_the_player_exits(self):
        sink = LiveSink('cat > /dev/null', RATE)
        sink.write(b'\x00\x00' * 100)
        sink.close()
        self.assertEqual(sink.p.returncode, 0)


class TestFromEnv(unittest.TestCase):

    def test_nothing_set_means_none(self):
        self.assertEqual(from_env({}, 0.0), (None, 0.0))
        self.assertEqual(from_env({'TRS80_SOUND': '', 'TRS80_SOUND_WAV': ' '}, 1.5), (None, 1.5))

    def test_wav_only_leaves_pacing_alone(self):
        fd, path = tempfile.mkstemp(suffix='.wav')
        os.close(fd)
        self.addCleanup(os.unlink, path)
        snd, mhz = from_env({'TRS80_SOUND_WAV': path, 'TRS80_SOUND_RATE': 'x'}, 0.0)
        self.assertEqual(mhz, 0.0)
        self.assertEqual((snd.synth.clock, snd.synth.rate), (CLOCK, RATE))
        self.assertFalse(snd.live)
        snd.close()

    def test_an_unwritable_wav_is_said_not_dropped(self):
        # L-49: a directory, and a file in a directory that does not exist
        import io
        d = tempfile.mkdtemp()
        self.addCleanup(os.rmdir, d)
        for path in (d, os.path.join(d, 'no', 'such.wav')):
            err = io.StringIO()
            self.assertEqual(from_env({'TRS80_SOUND_WAV': path}, 0.0, err), (None, 0.0))
            self.assertIn('z80 core: WAV %s: ' % path, err.getvalue())
            self.assertIn('no capture', err.getvalue())

    def test_a_wav_path_under_tilde_is_the_home_directory(self):
        d = tempfile.mkdtemp()
        self.addCleanup(os.rmdir, d)
        path = os.path.join(d, 'cap.wav')
        self.addCleanup(lambda: os.path.exists(path) and os.unlink(path))
        old = os.environ.get('HOME')
        os.environ['HOME'] = d
        try:
            snd, _ = from_env({'TRS80_SOUND_WAV': '~/cap.wav'}, 0.0)
        finally:
            if old is None:
                del os.environ['HOME']
            else:
                os.environ['HOME'] = old
        self.assertIsNotNone(snd)
        snd.close()
        self.assertTrue(os.path.exists(path))

    def test_player_forces_the_default_clock_and_gets_the_rate(self):
        snd, mhz = from_env({'TRS80_SOUND': 'cat > /dev/null # {rate}', 'TRS80_SOUND_RATE': '44100'}, 0.0)
        self.assertEqual(mhz, DEFAULT_MHZ)
        self.assertTrue(snd.live)
        self.assertEqual(snd.synth.rate, 44100)
        self.assertIn('# 44100', snd.sinks[0].p.args)
        snd.close()
        snd, mhz = from_env({'TRS80_SOUND': 'cat > /dev/null'}, 1.5)
        self.assertEqual(mhz, 1.5)
        self.assertEqual(snd.synth.clock, 1500000)
        snd.close()

    def test_unwritable_wav_is_skipped(self):
        self.assertEqual(from_env({'TRS80_SOUND_WAV': '/nonexistent-dir/x.wav'}, 0.0), (None, 0.0))

    def test_default_player_names_an_installed_one(self):
        import shutil
        cmd = default_player(RATE)
        if shutil.which('ffmpeg') or shutil.which('ffplay') or shutil.which('aplay'):
            self.assertIn('22050', cmd)
        else:
            self.assertIsNone(cmd)


class TestWavSinkAcrossRestarts(unittest.TestCase):
    """The interpreter restarts the core for `speed`, `sound` and a REM META
    line; a capture must not start over each time."""

    def path(self):
        fd, path = tempfile.mkstemp(suffix='.wav')
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.unlink(path))
        return path

    def test_append_carries_the_capture_on(self):
        path = self.path()
        a, b = b'\x01\x00' * 300, b'\x02\x00' * 500
        k = WavSink(path, RATE); k.write(a); k.close()
        k = WavSink(path, RATE, append=True); k.write(b); k.close()
        self.assertEqual(wav_pcm(path), ((1, 2, RATE), a + b))       # wave reads it: the header is right
        k = WavSink(path, RATE, append=True); k.close()              # a core that makes no sound
        self.assertEqual(wav_pcm(path)[1], a + b)

    def test_a_first_start_is_a_new_file(self):
        path = self.path()
        k = WavSink(path, RATE); k.write(b'\x01\x00' * 300); k.close()
        k = WavSink(path, RATE); k.close()
        self.assertEqual(wav_pcm(path), ((1, 2, RATE), b''))

    def test_append_onto_something_else_starts_over(self):
        path = self.path()
        for junk in (b'', b'not a wav file at all, but longer than a header is........'):
            with open(path, 'wb') as f:
                f.write(junk)
            k = WavSink(path, RATE, append=True); k.write(b'\x03\x00' * 10); k.close()
            self.assertEqual(wav_pcm(path), ((1, 2, RATE), b'\x03\x00' * 10))
        k = WavSink(path, 11025, append=True); k.close()            # another rate: not this capture
        self.assertEqual(wav_pcm(path), ((1, 2, 11025), b''))
        os.unlink(path)
        k = WavSink(path, RATE, append=True); k.close()              # nothing there
        self.assertEqual(wav_pcm(path), ((1, 2, RATE), b''))

    def test_an_odd_byte_left_by_a_kill_is_dropped(self):
        path = self.path()
        k = WavSink(path, RATE); k.write(b'\x01\x00' * 4); k.close()
        with open(path, 'ab') as f:
            f.write(b'\x7f')
        k = WavSink(path, RATE, append=True); k.write(b'\x02\x00'); k.close()
        self.assertEqual(wav_pcm(path)[1], b'\x01\x00' * 4 + b'\x02\x00')

    def test_from_env_reads_the_switch(self):
        path = self.path()
        k = WavSink(path, RATE); k.write(b'\x01\x00' * 8); k.close()
        snd, _ = from_env({'TRS80_SOUND_WAV': path, 'TRS80_SOUND_WAV_APPEND': '1'}, 0.0)
        snd.close()
        self.assertEqual(len(wav_pcm(path)[1]), 16)
        snd, _ = from_env({'TRS80_SOUND_WAV': path}, 0.0)
        snd.close()
        self.assertEqual(len(wav_pcm(path)[1]), 0)


class TestTransport(unittest.TestCase):

    def talk(self, lines, env=None):
        e = dict(os.environ)
        for k in ('TRS80_SOUND', 'TRS80_SOUND_WAV', 'TRS80_SOUND_RATE'):
            e.pop(k, None)
        e.update(env or {})
        p = subprocess.Popen([sys.executable, CORE], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, env=e)
        out, err = p.communicate('\n'.join(lines) + '\n', timeout=30)
        self.assertEqual(err, '')
        self.assertEqual(p.returncode, 0)
        return [l for l in out.splitlines() if not l.startswith('Z80 ')]   # the pid differs

    def test_protocol_identical_with_and_without_sound(self):
        code = routine(100)
        lines = ['HELLO proto=2 mhz=0 ramtop=65535',
                 'CALL gen=1 full=1 slot=0 entry=28928 arg=0 sp=65280 himem=65535 ramtop=65535 runs=1',
                 'M 28928:' + ','.join(str(b) for b in code),
                 'GO',
                 'BYE']
        plain = self.talk(lines)
        fd, path = tempfile.mkstemp(suffix='.wav')
        os.close(fd)
        self.addCleanup(os.unlink, path)
        self.assertEqual(self.talk(lines, {'TRS80_SOUND_WAV': path}), plain)
        hdr, pcm = wav_pcm(path)
        self.assertEqual(hdr, (1, 2, RATE))
        self.assertAlmostEqual(pitch(pcm) / (CLOCK / 2638), 1.0, delta=0.005)
        fd, raw = tempfile.mkstemp(suffix='.pcm')
        os.close(fd)
        self.addCleanup(os.unlink, raw)
        self.assertEqual(self.talk(lines, {'TRS80_SOUND': 'cat > ' + raw}), plain)   # paced, same lines
        self.assertGreaterEqual(os.path.getsize(raw), len(pcm))

    def test_eof_closes_the_wav(self):
        fd, path = tempfile.mkstemp(suffix='.wav')
        os.close(fd)
        self.addCleanup(os.unlink, path)
        self.talk(['HELLO proto=2 mhz=0 ramtop=65535',
                   'CALL gen=1 full=1 slot=0 entry=28928 arg=0 sp=65280 himem=65535 ramtop=65535 runs=1',
                   'M 28928:62,1,211,255,201', 'GO'], {'TRS80_SOUND_WAV': path})   # no BYE: EOF
        hdr, pcm = wav_pcm(path)
        self.assertEqual(hdr, (1, 2, RATE))


if __name__ == '__main__':
    unittest.main()
