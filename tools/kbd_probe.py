#!/usr/bin/env python3
"""kbd_probe.py -- what one keyboard read costs through trs80basic, in batch and at a terminal.

    python3 tools/kbd_probe.py [--basic PATH] [--reads N] [--tty-reads N]
                               [--loops N] [--pipe-runs N] [--work DIR]
    python3 tools/kbd_probe.py --listing FILE [--seconds N] [--basic PATH] [--work DIR]
    python3 tools/kbd_probe.py --rates R,R... [--seconds N] [--basic PATH] [--work DIR]

At a terminal, trs80basic answers a keyboard read that finds no byte
queued -- the core's `K` line, a BASIC PEEK of 3800H-38FFH, an INKEY$ --
by reading the tty itself (src/p30_kbd.awk, kb_fill_tty; until
2026-09-16 it ran `dd if=/dev/tty | od` through the shell on every such
read, which this tool was written to measure).  In batch mode the same
read takes a byte from stdin.  Without --listing this measures both,
unpaced (TRS80_MHZ=0):

  0. the old pipeline alone, run from inside a pseudo-terminal (the
     reference the 2026-09-16 change is measured against);
  1. the core alone: a 12-byte routine reading 38FFH in a loop (LD BC,n /
     LD A,(38FFH) / DEC BC / LD A,B / OR C / JR NZ / RET) with a stub
     transport;
  2. the routine POKEd and called by BASIC in batch mode, stdin a file of
     keys, with a logging proxy timing every K -> K round trip;
  3. the same at a pseudo-terminal with no key pressed;
  4. the same with a key held (a byte every 33 ms, as auto-repeat sends);
  5. BASIC alone at the pseudo-terminal: PEEK(14591) and INKEY$ loops
     against the same loops without the keyboard, wall time per pass.

With --listing it runs that BASIC listing instead, one whose USR routine
keeps running, and measures --seconds of it after start-up four ways:
batch unpaced (stdin lines of "_", a byte with no key on the matrix), and
at the terminal unpaced with plain output, unpaced with the screen drawn,
and paced at 1.77408 MHz with the screen drawn.  It reports the emulated
speed as a share of the machine, keyboard reads, ticks and video lines a
second, and the share of the time the core spent waiting on the
interpreter's answer to a K and to a T.

With --rates it runs, at the terminal and paced at 1.77408 MHz, a routine
that reads the keyboard at each given rate per emulated second (LD
A,(3840H) and a delay loop), to find where a program starts to fall
behind real time.

A pseudo-terminal is what a terminal emulator gives the interpreter, so
the terminal runs are what a user at a terminal gets.  --basic is the
trs80basic checkout (default: ../trs80basic beside this repo).  Standard
library only.  Timings vary by host; the shape does not.

Internal: `--proxy LOG -- CMD...` is the logging proxy the interpreter is
pointed at.
"""
import argparse
import json
import os
import platform
import pty
import select
import signal
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MHZ = 1.77408
PIPELINE = 'dd if=/dev/tty bs=256 count=1 2>/dev/null | od -A n -t u1 -v'   # kb_fill's command until 2026-09-16
ENTRY = 32000


def routine(n):
    """LD BC,n / loop: LD A,(38FFH) / DEC BC / LD A,B / OR C / JR NZ,loop / RET"""
    return bytes([0x01, n & 0xFF, n >> 8, 0x3A, 0xFF, 0x38,
                  0x0B, 0x78, 0xB1, 0x20, 0xF8, 0xC9])


def usr_program(n):
    code = routine(n)
    return ['10 FOR I=0 TO %d:READ B:POKE %d+I,B:NEXT' % (len(code) - 1, ENTRY),
            '20 DATA ' + ','.join(str(b) for b in code),
            '30 DEFUSR=%d:X=USR(0)' % ENTRY,
            '40 PRINT "FIN";"ISHED"']


def ms(x):
    return '%.3f ms' % (x * 1e3)


def versus(rate, machine):
    if rate >= machine:
        return '%.1fx the machine' % (rate / machine)
    return '1/%.0f of the machine' % (machine / rate)


def fresh(path):
    if os.path.exists(path):
        os.remove(path)


# ---- the proxy -------------------------------------------------------------------
def proxy(log, cmd):
    """Forward the protocol both ways, timing each K -> K and T -> OK round
    trip.  Counters go to LOG every quarter second, so a session that is
    killed still leaves them; the round-trip statistics are added when the
    interpreter closes the pipe (`final`)."""
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    pending = [None]
    rtts = {'K': [], 'T': []}
    count = {'cycles': 0, 'V': 0, 'ends': 0, 'Ksum': 0.0, 'Tsum': 0.0}
    done = threading.Event()

    def snapshot(final):
        d = dict(count, at=time.monotonic(), final=final,
                 Kn=len(rtts['K']), Tn=len(rtts['T']))
        if final:
            for kind, r in rtts.items():
                if r:
                    r = sorted(r)
                    n = len(r)
                    d[kind] = {'n': n, 'p50': r[n // 2], 'p99': r[min(n - 1, int(n * .99))],
                               'max': r[-1], 'sum': sum(r)}
        with open(log + '.tmp', 'w') as f:
            json.dump(d, f)
        os.replace(log + '.tmp', log)

    def core_to_interp():
        for line in iter(p.stdout.readline, b''):
            head = line[:2]
            if head in (b'K ', b'T '):
                if head == b'T ':
                    count['cycles'] += int(line[2:])
                pending[0] = (line[:1].decode(), time.monotonic())
            elif head == b'V ':
                count['V'] += 1
            elif line.startswith((b'RET ', b'ERR ')):
                count['ends'] += 1
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()

    def ticker():
        while not done.wait(0.25):
            snapshot(False)

    threading.Thread(target=core_to_interp, daemon=True).start()
    tick = threading.Thread(target=ticker, daemon=True)
    tick.start()
    for line in iter(sys.stdin.buffer.readline, b''):
        if pending[0] is not None:
            kind, t0 = pending[0]
            pending[0] = None
            dt = time.monotonic() - t0
            rtts[kind].append(dt)
            count[kind + 'sum'] += dt
        p.stdin.write(line)
        p.stdin.flush()
    try:
        p.stdin.close()
    except OSError:
        pass
    p.wait()
    done.set()
    tick.join(1)
    snapshot(True)


def load(log, wait=10.0):
    """The proxy's final statistics."""
    t0 = time.monotonic()
    while True:
        try:
            with open(log) as f:
                d = json.load(f)
            if d.get('final'):
                return d
        except (OSError, ValueError):
            pass
        if time.monotonic() - t0 > wait:
            raise SystemExit('no final proxy log at %s' % log)
        time.sleep(0.05)


def base_env():
    env = dict(os.environ, TRS80_MHZ='0', TRS80_DUMB='1', TERM='xterm', TRS80_Z80='')
    for v in ('TRS80_SOUND', 'TRS80_SOUND_WAV', 'TRS80_KMHOLD', 'TRS80_USR'):
        env.pop(v, None)
    return env


def proxied_env(log):
    return dict(base_env(), TRS80_Z80='python3 %s --proxy %s -- python3 %s' % (
        os.path.abspath(__file__), log, os.path.join(ROOT, 'core.py')))


# ---- a pseudo-terminal ---------------------------------------------------------
class Tty:
    def __init__(self, argv, env, cwd):
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            try:
                os.chdir(cwd)
                os.execvpe(argv[0], argv, env)
            finally:
                os._exit(127)
        self.buf = b''

    def until(self, s, timeout):
        """Read until s has appeared; return the time it did."""
        t0 = time.monotonic()
        while s not in self.buf:
            r, _, _ = select.select([self.fd], [], [], 0.05)
            if r:
                try:
                    data = os.read(self.fd, 4096)
                except OSError:
                    data = b''
                if not data:
                    raise SystemExit('the session ended waiting for %r' % s)
                self.buf += data
            if time.monotonic() - t0 > timeout:
                raise SystemExit('timeout waiting for %r' % s)
        return time.monotonic()

    def pump(self, seconds):
        """Drain and discard output for `seconds`, so a drawn screen never blocks."""
        t0 = time.monotonic()
        while time.monotonic() - t0 < seconds:
            r, _, _ = select.select([self.fd], [], [], 0.05)
            if r:
                try:
                    if not os.read(self.fd, 65536):
                        return
                except OSError:
                    return

    def send(self, s, pause=0.05):
        os.write(self.fd, s.encode())
        if pause:
            time.sleep(pause)

    def close(self):
        # Close the terminal (SIGHUP), reap with a bounded poll, and only then
        # signal the session's group -- a blocking waitpid hung once in
        # tick_probe on 2026-09-13.
        try:
            os.close(self.fd)
        except OSError:
            pass
        for sig in (None, signal.SIGTERM, signal.SIGKILL):
            if sig is not None:
                try:
                    os.killpg(self.pid, sig)
                except OSError:
                    try:
                        os.kill(self.pid, sig)
                    except OSError:
                        pass
            for _ in range(20):
                try:
                    if os.waitpid(self.pid, os.WNOHANG)[0] == self.pid:
                        return
                except ChildProcessError:
                    return
                time.sleep(0.1)


def session(basic, env, lines, cwd):
    """trs80basic at its READY prompt with `lines` typed in (plain output)."""
    t = Tty([os.path.join(basic, 'basic')], env, cwd)
    t.until(b'MEMORY SIZE', 15)
    t.send('\r')
    t.until(b'READY', 15)
    for ln in lines:
        t.send(ln + '\r')
    t.buf = b''
    return t


def leave(t, log=None):
    """BYE (Ctrl-U first clears what a held key typed at the prompt); the
    interpreter closes the core's pipe and the proxy writes its statistics."""
    t.send('\x15bye\r')
    try:
        return load(log) if log else None
    finally:
        t.close()


# ---- 0. the pipeline alone ---------------------------------------------------------
PIPE_CHILD = r'''
import os, subprocess, sys, time
os.system("stty raw -echo min 0 time 0 < /dev/tty")
n, cmd = int(sys.argv[1]), sys.argv[2]
ts = []
for _ in range(n):
    t0 = time.perf_counter()
    subprocess.run(["/bin/sh", "-c", cmd], stdout=subprocess.PIPE)
    ts.append(time.perf_counter() - t0)
os.system("stty sane < /dev/tty")
ts.sort()
sys.stdout.write("PIPE %.9f %.9f %.9f END\n" % (ts[len(ts) // 2], ts[min(n - 1, int(n * .99))], ts[-1]))
sys.stdout.flush()
'''


def pipeline_alone(runs):
    t = Tty([sys.executable, '-c', PIPE_CHILD, str(runs), PIPELINE], dict(os.environ), ROOT)
    t.until(b' END', 30 + runs * 0.1)
    fields = t.buf[t.buf.index(b'PIPE '):].split()
    t.close()
    return [float(x) for x in fields[1:4]]


# ---- 1. the core alone -------------------------------------------------------------
def core_alone(n):
    sys.path.insert(0, ROOT)
    from z80.coprocess import Machine
    m = Machine(lambda s: None, lambda: 'K 0', 0.0)
    for i, b in enumerate(routine(n)):
        m.ram[0x7100 + i] = b
    t0 = time.perf_counter()
    m.run(0x7100, 0, 0xFF00)
    return time.perf_counter() - t0, m.cycles


# ---- 2. batch ------------------------------------------------------------------------
def batch_usr(basic, n, work):
    log = os.path.join(work, 'batch.json')
    fresh(log)
    bas = os.path.join(work, 'usr.bas')
    keys = os.path.join(work, 'keys.txt')
    with open(bas, 'w') as f:
        f.write('\n'.join(usr_program(n)) + '\n')
    with open(keys, 'w') as f:
        f.write('a\n' * (n + 16))
    t0 = time.monotonic()
    with open(keys) as kin:
        r = subprocess.run([os.path.join(basic, 'basic'), bas], env=proxied_env(log), stdin=kin,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=work, timeout=900)
    wall = time.monotonic() - t0
    if b'FINISHED' not in r.stdout:
        raise SystemExit('the batch run did not finish:\n' + r.stderr.decode('latin-1')[-2000:])
    return wall, load(log)


# ---- 3 and 4. the terminal, no key and a held key --------------------------------------
def tty_usr(basic, n, work, held):
    log = os.path.join(work, 'tty-%s.json' % ('held' if held else 'idle'))
    fresh(log)
    t = session(basic, proxied_env(log), usr_program(n), work)
    stop = threading.Event()
    t0 = time.monotonic()
    t.send('RUN\r', pause=0)
    if held:
        def repeat():
            while not stop.wait(1 / 30):
                try:
                    os.write(t.fd, b'a')
                except OSError:
                    return
        threading.Thread(target=repeat, daemon=True).start()
    t1 = t.until(b'FINISHED', 120 + n * 0.05)
    stop.set()
    time.sleep(0.1)
    return t1 - t0, leave(t, log)


# ---- 5. BASIC alone at the terminal ------------------------------------------------------
BASIC_PAIRS = [('PEEK(14591)', 'A=PEEK(14591)', 'PEEK(32000)', 'A=PEEK(32000)'),
               ('INKEY$', 'A$=INKEY$', 'A$=""', 'A$=""')]


def tty_basic(basic, stmt, loops, work):
    t = session(basic, base_env(),
                ['10 FOR I=1 TO %d:%s:NEXT:PRINT "FIN";"ISHED"' % (loops, stmt)], work)
    t0 = time.monotonic()
    t.send('RUN\r', pause=0)
    t1 = t.until(b'FINISHED', 60 + loops * 0.05)
    leave(t)
    return (t1 - t0) / loops


def served(n, k, core_per_read):
    """Keyboard reads a second this path serves the routine."""
    return n / (k['sum'] + core_per_read * n)


# ---- 6. a listing whose routine keeps running --------------------------------------------
def snap(log, wait, timeout=60):
    """The proxy's latest counters, once the routine has run a tick."""
    t0 = time.monotonic()
    while True:
        try:
            with open(log) as f:
                d = json.load(f)
            if d['cycles'] > 0:
                return d
        except (OSError, ValueError, KeyError):
            pass
        if time.monotonic() - t0 > timeout:
            raise SystemExit('no routine ran within %d s (%s)' % (timeout, log))
        wait(0.1)


def measure(log, wait, seconds):
    snap(log, wait)
    wait(1.0)                      # past the call's start-up
    a = snap(log, wait)
    wait(seconds)
    b = snap(log, wait)
    dt = b['at'] - a['at']
    return {'speed': (b['cycles'] - a['cycles']) / dt / (MHZ * 1e6),
            'reads': (b['Kn'] - a['Kn']) / dt, 'video': (b['V'] - a['V']) / dt,
            'ends': b['ends'] - a['ends'], 'span': dt, 'ticks': (b['Tn'] - a['Tn']) / dt,
            'kwait': (b['Ksum'] - a['Ksum']) / dt, 'twait': (b['Tsum'] - a['Tsum']) / dt}


def batch_listing(basic, path, seconds, work):
    log = os.path.join(work, 'listing-batch.json')
    fresh(log)
    keys = os.path.join(work, 'nokey.txt')
    with open(keys, 'w') as f:
        f.write(('_' * 4095 + '\n') * 1000)
    with open(keys) as kin:
        p = subprocess.Popen([os.path.join(basic, 'basic'), path], env=proxied_env(log), stdin=kin,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=work,
                             start_new_session=True)
    try:
        return measure(log, time.sleep, seconds)
    finally:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(p.pid, sig)
            except OSError:
                break
            try:
                p.wait(2)
                break
            except subprocess.TimeoutExpired:
                pass


def tty_listing(basic, path, seconds, work, mhz, screen):
    log = os.path.join(work, 'listing-tty-%s-%s.json'
                       % ('paced' if float(mhz) else 'unpaced', 'screen' if screen else 'plain'))
    fresh(log)
    env = dict(proxied_env(log), TRS80_MHZ=mhz, LINES='24', COLUMNS='80')
    if screen:
        env.pop('TRS80_DUMB', None)
    t = Tty([os.path.join(basic, 'basic')], env, work)
    try:
        # timed, not matched: a drawn screen positions every cell, so the
        # prompts never arrive as contiguous text (usr_pty_sweep's approach)
        t.pump(1.2)
        t.send('\r', 0)
        t.pump(0.8)
        t.send('CLOAD "%s"\r' % path, 0)
        t.pump(2.5)
        t.send('RUN\r', 0)
        return measure(log, t.pump, seconds)
    finally:
        t.close()


def poll_listing(rate, path):
    """A never-returning routine reading 3840H `rate` times per emulated
    second: LD A,(3840H) / LD BC,d / DEC BC / LD A,B / OR C / JR NZ,-5 /
    JR -13, which is 30 + 26d T-states a read.  Returns the rate it gets."""
    d = max(1, min(65535, round((MHZ * 1e6 / rate - 30) / 26)))
    code = bytes([0x3A, 0x40, 0x38, 0x01, d & 0xFF, d >> 8,
                  0x0B, 0x78, 0xB1, 0x20, 0xFB, 0x18, 0xF3])
    with open(path, 'w') as f:
        f.write('10 FOR I=0 TO %d:READ B:POKE 28416+I,B:NEXT\n' % (len(code) - 1))
        f.write('20 DATA %s\n' % ','.join(str(b) for b in code))
        f.write('30 DEFUSR=28416:X=USR(0)\n')
    return MHZ * 1e6 / (30 + 26 * d)


def main():
    if len(sys.argv) > 2 and sys.argv[1] == '--proxy':
        proxy(sys.argv[2], sys.argv[sys.argv.index('--') + 1:])
        return 0
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--basic', default=os.path.join(os.path.dirname(ROOT), 'trs80basic'),
                    help='the trs80basic checkout (default: ../trs80basic)')
    ap.add_argument('--reads', type=int, default=20000,
                    help='keyboard reads in the core-alone and batch runs, 1-65535 (default 20000)')
    ap.add_argument('--tty-reads', type=int, default=1000,
                    help='keyboard reads in each terminal run, 1-65535 (default 1000)')
    ap.add_argument('--loops', type=int, default=1000,
                    help='passes of each BASIC loop at the terminal (default 1000)')
    ap.add_argument('--pipe-runs', type=int, default=200,
                    help='runs of the pipeline alone (default 200)')
    ap.add_argument('--listing', metavar='FILE',
                    help='measure this listing instead, its USR routine left running')
    ap.add_argument('--seconds', type=float, default=15.0,
                    help='seconds measured per way with --listing, per rate with --rates (default 15)')
    ap.add_argument('--rates', metavar='R,R...',
                    help='keyboard reads per emulated second to try, paced, at the terminal')
    ap.add_argument('--work', default=os.path.join(ROOT, 'out', 'kbd_probe'),
                    help='directory for the programs and proxy logs (default out/kbd_probe)')
    a = ap.parse_args()
    for name in ('reads', 'tty_reads'):
        if not 1 <= getattr(a, name) <= 65535:
            ap.error('--%s must be 1-65535' % name.replace('_', '-'))
    basic = os.path.abspath(a.basic)
    if not os.path.exists(os.path.join(basic, 'basic')):
        sys.exit('no interpreter at %s (--basic)' % basic)
    work = os.path.abspath(a.work)
    os.makedirs(work, exist_ok=True)
    print('host: %s %s, %s, Python %s' % (platform.system(), platform.release(),
                                         platform.machine(), platform.python_version()))

    if a.rates:
        print('7 a routine reading the keyboard at a set rate, at the terminal, paced at %g MHz, '
              '%g s each after start-up' % (MHZ, a.seconds))
        for rate in [int(r) for r in a.rates.split(',')]:
            path = os.path.join(work, 'poll-%d.bas' % rate)
            want = poll_listing(rate, path)
            r = tty_listing(basic, path, a.seconds, work, str(MHZ), False)
            print('  %5.0f reads per emulated second: speed %.3f, %s reads/s; '
                  'waiting on K %.0f%%, on T %.0f%% of the time'
                  % (want, r['speed'], format(int(r['reads']), ','), r['kwait'] * 100, r['twait'] * 100))
        return 0

    if a.listing:
        path = os.path.abspath(a.listing)
        if not os.path.exists(path):
            sys.exit('no listing at %s' % path)
        print('6 %s, %g s each after start-up; speed is emulated T-states a second '
              'as a share of the %g MHz machine' % (os.path.basename(path), a.seconds, MHZ))
        ways = [('batch, unpaced', lambda: batch_listing(basic, path, a.seconds, work))]
        for mhz, screen in (('0', False), ('0', True), (str(MHZ), True)):
            ways.append(('terminal, %s, %s' % ('paced' if float(mhz) else 'unpaced',
                                               'screen' if screen else 'plain'),
                         lambda mhz=mhz, screen=screen:
                             tty_listing(basic, path, a.seconds, work, mhz, screen)))
        for label, fn in ways:
            r = fn()
            print('  %-26s speed %6.3f  %s keyboard reads/s  %s ticks/s  %s video lines/s;  '
                  'waiting on K %.0f%%, on T %.0f%% of the time%s'
                  % (label, r['speed'], format(int(r['reads']), ','), format(int(r['ticks']), ','),
                     format(int(r['video']), ','), r['kwait'] * 100, r['twait'] * 100,
                     '  (%d call(s) ended in the window)' % r['ends'] if r['ends'] else ''))
        return 0

    p50, p99, mx = pipeline_alone(a.pipe_runs)
    print('0 the pipeline alone         median %s  p99 %s  max %s  (%d runs)'
          % (ms(p50), ms(p99), ms(mx), a.pipe_runs))

    wall, cycles = core_alone(a.reads)
    core_per = wall / a.reads
    tstates = (cycles - 15) / a.reads      # less LD BC, RET, and the last JR NZ falling through
    machine = MHZ * 1e6 / tstates
    print('1 the core alone             %d reads of %.0f T-states: %s a read; '
          'the machine does %s reads/s of this loop'
          % (a.reads, tstates, ms(core_per), format(int(machine), ',')))

    rows = []
    wall, st = batch_usr(basic, a.reads, work)
    rows.append(('2 batch, stdin a file', a.reads, wall, st))
    for held in (False, True):
        wall, st = tty_usr(basic, a.tty_reads, work, held)
        rows.append(('4 terminal, key held' if held else '3 terminal, no key', a.tty_reads, wall, st))
    for label, n, wall, st in rows:
        k = st.get('K')
        if not k or k['n'] != n:
            sys.exit('%s: expected %d K round trips, the proxy logged %s' % (label, n, k and k['n']))
        rate = served(n, k, core_per)
        print('%-29s %d reads: K round trip median %s  p99 %s  max %s; %s reads/s, '
              '%s; RUN to result %.2f s'
              % (label, n, ms(k['p50']), ms(k['p99']), ms(k['max']),
                 format(int(rate), ','), versus(rate, machine), wall))

    for label, stmt, clabel, cstmt in BASIC_PAIRS:
        w = tty_basic(basic, stmt, a.loops, work)
        c = tty_basic(basic, cstmt, a.loops, work)
        print('5 terminal, BASIC %-11s %s a pass; with %s instead %s; the read adds %s'
              % (label, ms(w), clabel, ms(c), ms(w - c)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
