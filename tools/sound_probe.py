#!/usr/bin/env python3
"""sound_probe.py -- the 2026-09-13 measurements behind machine-code sound.

    python3 tools/sound_probe.py synth [--wav PATH]
        Prototype synthesizer: T-state-stamped port FFH level changes into
        16-bit PCM, box-filtered and DC-blocked.  Prints the measured pitch
        and the synthesis cost for three tones at 22,050 and 44,100 Hz.
        With --wav, also writes a C-major arpeggio built the same way.

    python3 tools/sound_probe.py sinks
        Silent stream probes (every sample is zero) against ffplay and
        ffmpeg's AudioToolbox output device: how far each buffers ahead of
        a writer that does not pace, the lag while paced, and what happens
        across a one-second pause.  A player that is not installed is
        skipped.  Takes about 40 seconds.

A prototype, not the core: z80/sound.py is the synthesizer built from
it.  Standard library only.
"""
import argparse
import array
import re
import shutil
import subprocess
import sys
import threading
import time
import wave

CLOCK_HZ = 10.6445e6 / 6                      # Model I: 1.77408 MHz
LEVEL = {0: 0.0, 1: 1.0, 2: -1.0, 3: 0.0}     # bits 0-1; 3 is treated as rest


def synth(transitions, total_t, clock_hz, rate, amp=9000, hp=0.995):
    """transitions: sorted (tstate, bits01) pairs; the level before the first is rest."""
    tps = clock_hz / rate                     # T-states per sample
    n = int(total_t / tps)
    out = array.array('h', bytes(2 * n))
    lvl = 0.0
    i = 0
    nt = len(transitions)
    px = py = 0.0
    for s in range(n):
        a = s * tps
        b = a + tps
        acc = 0.0
        pos = a
        while i < nt and transitions[i][0] < b:
            t = transitions[i][0]
            if t > pos:
                acc += lvl * (t - pos)
                pos = t
            lvl = LEVEL[transitions[i][1]]
            i += 1
        acc += lvl * (b - pos)
        x = acc / tps
        y = x - px + hp * py                  # one-pole DC blocker
        px, py = x, y
        out[s] = max(-32767, min(32767, int(y * amp)))
    return out


def square(freq, seconds, clock_hz):
    half = clock_hz / (2 * freq)
    tr = []
    t = 0.0
    k = 0
    end = seconds * clock_hz
    while t < end:
        tr.append((int(round(t)), 1 if k % 2 == 0 else 2))
        t += half
        k += 1
    return tr, int(end)


def pitch(pcm, rate):
    ups = [i for i in range(1, len(pcm)) if pcm[i - 1] < 0 <= pcm[i]]
    return (len(ups) - 1) / ((ups[-1] - ups[0]) / rate) if len(ups) > 2 else 0.0


def cmd_synth(args):
    for rate in (22050, 44100):
        for f in (261.63, 440.0, 2000.0):
            tr, tot = square(f, 5.0, CLOCK_HZ)
            t0 = time.perf_counter()
            pcm = synth(tr, tot, CLOCK_HZ, rate)
            dt = time.perf_counter() - t0
            print('rate %5d  tone %7.2f Hz  measured %8.2f Hz  synth %5.1f ms per audio second'
                  % (rate, f, pitch(pcm, rate), dt * 1000 / 5))
    if args.wav:
        tr = []
        base = 0
        for f in (261.63, 329.63, 392.00, 523.25):
            part, tot = square(f, 0.5, CLOCK_HZ)
            tr += [(t + base, v) for t, v in part]
            base += tot
        tr.append((base, 0))
        base += int(0.3 * CLOCK_HZ)
        pcm = synth(tr, base, CLOCK_HZ, 22050)
        w = wave.open(args.wav, 'wb')
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(pcm.tobytes())
        w.close()
        print('wrote %s: %d samples, %.2f s' % (args.wav, len(pcm), len(pcm) / 22050))


RATE = 22050


def stream(cmd, parse, seconds, pace=True, pause=None):
    """Feed zeros in 10 ms chunks; collect (wall, player time) pairs parsed from stderr."""
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                         stderr=subprocess.PIPE)
    pts = []
    t0 = time.monotonic()

    def reader():
        buf = b''
        for c in iter(lambda: p.stderr.read(1), b''):
            if c in b'\r\n':
                v = parse(buf)
                if v is not None:
                    pts.append((time.monotonic() - t0, v))
                buf = b''
            else:
                buf += c

    th = threading.Thread(target=reader, daemon=True)
    th.start()
    chunk = bytes(2 * RATE // 100)
    written = 0.0
    paused = 0.0
    marks = {}
    while written < seconds:
        if pause and not paused and abs(written - pause[0]) < 0.005:
            time.sleep(pause[1])
            paused = pause[1]
        p.stdin.write(chunk)
        p.stdin.flush()
        written += 0.01
        for m in (2, 4, 6, 8):
            if abs(written - m) < 0.005:
                marks[m] = round(time.monotonic() - t0, 2)
        if pace:
            d = t0 + written + paused - time.monotonic()
            if d > 0:
                time.sleep(d)
    p.stdin.close()
    rc = p.wait()
    th.join(1)
    return pts, marks, rc


def lag(pts, lo, hi, shift=0.0):
    v = sorted(w - c - shift for w, c in pts if lo <= w <= hi and c > 0.05)
    return '%.3f/%.3f/%.3f s over %d samples' % (v[0], v[len(v) // 2], v[-1], len(v)) if v else 'no data'


def cmd_sinks(args):
    fmt = ['-f', 's16le', '-ar', str(RATE), '-ch_layout', 'mono', '-i', '-']
    players = []
    if shutil.which('ffplay'):
        players.append(('ffplay, lag behind its playback clock',
                        ['ffplay', '-nodisp', '-autoexit', '-stats', '-loglevel', 'info'] + fmt,
                        lambda b: (lambda m: float(m.group(1)) if m else None)(
                            re.match(rb'\s*(\d+\.\d+)\s+(?:M-A|A-V|M-V|aq=)', b))))
    else:
        print('ffplay: not installed, skipped')
    devices = subprocess.run(['ffmpeg', '-hide_banner', '-devices'], capture_output=True,
                             text=True).stdout if shutil.which('ffmpeg') else ''
    if 'audiotoolbox' in devices:
        players.append(('ffmpeg audiotoolbox, lag behind samples handed to the device',
                        ['ffmpeg', '-hide_banner', '-nostats', '-loglevel', 'error', '-progress',
                         'pipe:2', '-stats_period', '0.1'] + fmt + ['-f', 'audiotoolbox', '-'],
                        lambda b: (lambda m: int(m.group(1)) / 1e6 if m else None)(
                            re.match(rb'out_time_us=(\d+)', b))))
    else:
        print('ffmpeg audiotoolbox output: not available, skipped')
    for name, cmd, parse in players:
        print(name)
        _, marks, rc = stream(cmd, parse, 8.0, pace=False)
        print('  unpaced writer, wall time when N s of audio was accepted: %s (exit %d)' % (marks, rc))
        pts, _, rc = stream(cmd, parse, 4.0)
        print('  paced lag min/median/max: %s (exit %d)' % (lag(pts, 0.5, 4.0), rc))
        pts, _, rc = stream(cmd, parse, 4.0, pause=(1.5, 1.0))
        during = [round(c, 2) for w, c in pts if 1.6 <= w <= 2.4][::3]
        print('  1 s pause after 1.5 s: lag before %s; player time during the pause %s; '
              'lag after, pause removed %s (exit %d)'
              % (lag(pts, 0.5, 1.5), during, lag(pts, 3.0, 5.0, shift=1.0), rc))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('synth', help='pitch accuracy and cost of the prototype synthesizer')
    s.add_argument('--wav', help='also write a C-major arpeggio to this WAV file')
    sub.add_parser('sinks', help='silent stream probes against the installed players')
    args = ap.parse_args()
    {'synth': cmd_synth, 'sinks': cmd_sinks}[args.cmd](args)


if __name__ == '__main__':
    sys.exit(main())
