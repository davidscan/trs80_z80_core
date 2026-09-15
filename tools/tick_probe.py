#!/usr/bin/env python3
"""tick_probe.py -- the 2026-09-13 speed and tick round-trip measurements behind machine-code sound.

    python3 tools/tick_probe.py [--basic PATH] [--passes N]

Runs a demon-shaped sound loop (OUT (C),H / LD B,D / DJNZ / OUT (C),L /
LD B,D / DJNZ / DEC E / JR NZ, D = 100, so 2,638 T-states a cycle) for
N passes of 256 cycles (12 passes: 4.57 s of emulated time) and reports:

  1. the core alone (Machine.run with a stub transport), unpaced and
     paced at 1.77408 MHz;
  2. the same routine POKEd by a BASIC program and called through the
     interpreter in batch mode, paced, with a logging proxy between the
     two that times every T -> OK round trip;
  3. the same through a pseudo-terminal, so the interpreter is
     interactive and polls the real keyboard on every tick.

--basic is the trs80basic checkout (default: ../trs80basic beside this
repo). Standard library only. Timings vary by host; the shape does not.

Internal: `--proxy LOG -- CMD...` is the logging proxy the interpreter is
pointed at for measurements 2 and 3.
"""
import argparse
import json
import os
import pty
import select
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MHZ = '1.77408'


def routine(passes):
    """LD D,100 / LD C,FFH / LD HL,0201H / LD A,passes / LD E,0 /
    loop: OUT (C),H / LD B,D / DJNZ $ / OUT (C),L / LD B,D / DJNZ $ /
    DEC E / JR NZ,loop / DEC A / JR NZ,loop / RET   (28 bytes)"""
    return bytes([0x16, 100, 0x0E, 0xFF, 0x21, 0x01, 0x02, 0x3E, passes, 0x1E, 0x00,
                  0xED, 0x61, 0x42, 0x10, 0xFE, 0xED, 0x69, 0x42, 0x10, 0xFE, 0x1D, 0x20, 0xF3,
                  0x3D, 0x20, 0xF0, 0xC9])


# ---- 1. the core alone -------------------------------------------------------
def core_alone(passes):
    sys.path.insert(0, ROOT)
    from z80.coprocess import Machine
    out = []
    for mhz in (0.0, float(MHZ)):
        m = Machine(lambda s: None, lambda: 'OK', mhz)
        for i, b in enumerate(routine(passes)):
            m.ram[0x7100 + i] = b
        t0 = time.perf_counter()
        m.run(0x7100, 0, 0xFF00)
        wall = time.perf_counter() - t0
        emu = m.cycles / (float(MHZ) * 1e6)
        out.append((mhz, emu, wall))
    return out


# ---- the proxy: times T -> OK between the interpreter and the core -----------
def proxy(log, cmd):
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    sent = [None]
    rtts = []

    def core_to_interp():
        for line in iter(p.stdout.readline, b''):
            if line.startswith(b'T '):
                sent[0] = time.monotonic()
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()

    def interp_to_core():
        for line in iter(sys.stdin.buffer.readline, b''):
            if sent[0] is not None and line.strip() in (b'OK', b'BREAK'):
                rtts.append(time.monotonic() - sent[0])
                sent[0] = None
            p.stdin.write(line)
            p.stdin.flush()
        try:
            p.stdin.close()
        except OSError:
            pass

    t = threading.Thread(target=core_to_interp, daemon=True)
    t.start()
    interp_to_core()
    p.wait()
    t.join(1)
    r = sorted(rtts)
    if r:
        n = len(r)
        json.dump({'ticks': n, 'p50': r[n // 2], 'p99': r[int(n * .99)], 'max': r[-1]},
                  open(log, 'w'))


def stats(log):
    try:
        d = json.load(open(log))
    except (OSError, ValueError):
        return 'no tick log'
    return 'tick round-trip median %.2f ms, p99 %.2f, max %.2f (%d ticks)' % (
        d['p50'] * 1e3, d['p99'] * 1e3, d['max'] * 1e3, d['ticks'])


def program(passes):
    data = ','.join(str(b) for b in routine(passes))
    return ['10 FOR I=0 TO 27:READ B:POKE 32000+I,B:NEXT',
            '20 DATA ' + data,
            '30 DEFUSR=32000:X=USR(0)',
            '40 PRINT "FIN";"ISHED"']


def env_for(basic, log, mhz):
    core = 'python3 %s --proxy %s -- python3 %s' % (
        os.path.abspath(__file__), log, os.path.join(ROOT, 'core.py'))
    return dict(os.environ, TRS80_Z80=core, TRS80_MHZ=mhz, TRS80_DUMB='1', TERM='xterm')


# ---- 2. batch --------------------------------------------------------------------
def batch(basic, passes, log, mhz):
    bas = log + '.bas'
    open(bas, 'w').write('\n'.join(program(passes)) + '\n')
    t0 = time.monotonic()
    subprocess.run([os.path.join(basic, 'basic'), bas], env=env_for(basic, log, mhz),
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   cwd=basic, check=False)
    return time.monotonic() - t0


# ---- 3. interactive, through a pseudo-terminal -----------------------------------
def interactive(basic, passes, log, mhz):
    env = env_for(basic, log, mhz)
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(basic)
        os.execvpe('./basic', ['./basic'], env)
    buf = [b'']

    def until(s, timeout):
        t0 = time.monotonic()
        while s not in buf[0]:
            r, _, _ = select.select([fd], [], [], 0.05)
            if r:
                try:
                    buf[0] += os.read(fd, 4096)
                except OSError:
                    break
            if time.monotonic() - t0 > timeout:
                raise SystemExit('timeout waiting for %r' % s)

    def send(s):
        os.write(fd, s.encode())
        time.sleep(0.05)

    until(b'MEMORY SIZE', 15)
    send('\r')
    until(b'READY', 15)
    for ln in program(passes):
        send(ln + '\r')
    buf[0] = b''
    t0 = time.monotonic()
    send('RUN\r')
    until(b'FINISHED', 60)
    wall = time.monotonic() - t0
    # Let the interpreter leave on its own first: BYE reaches the proxy as
    # EOF and the proxy writes its log; a torn-down session loses it.
    send('bye\r')
    for _ in range(30):
        if os.path.exists(log):
            break
        time.sleep(0.1)
    # Teardown: close the terminal (the session gets SIGHUP), reap with a
    # bounded poll, and only then kill hard -- a blocking waitpid here
    # hung once on 2026-09-13.
    os.close(fd)
    for sig in (None, 15, 9):
        if sig is not None:
            try:
                os.kill(pid, sig)
            except OSError:
                pass
        for _ in range(20):
            try:
                if os.waitpid(pid, os.WNOHANG)[0] == pid:
                    return wall
            except ChildProcessError:
                return wall
            time.sleep(0.1)
    return wall


def main():
    if len(sys.argv) > 2 and sys.argv[1] == '--proxy':
        proxy(sys.argv[2], sys.argv[sys.argv.index('--') + 1:])
        return 0
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--basic', default=os.path.join(os.path.dirname(ROOT), 'trs80basic'))
    ap.add_argument('--passes', type=int, default=12)
    a = ap.parse_args()
    basic = os.path.abspath(a.basic)
    if not os.path.exists(os.path.join(basic, 'basic')):
        sys.exit('no interpreter at %s (--basic)' % basic)
    for mhz, emu, wall in core_alone(a.passes):
        print('core alone   %-8s %.3f s emulated in %.2f s wall%s'
              % ('paced' if mhz else 'unpaced', emu, wall,
                 '' if mhz else ' (%.1fx real time)' % (emu / wall)))
    os.makedirs(os.path.join(ROOT, 'out'), exist_ok=True)
    log = os.path.join(ROOT, 'out', 'tick_probe.json')
    for name, fn in (('batch', batch), ('interactive', interactive)):
        for mhz in (MHZ, '0'):
            if os.path.exists(log):
                os.remove(log)
            wall = fn(basic, a.passes, log, mhz)
            print('%-12s %-8s RUN to result %.2f s; %s'
                  % (name, 'paced' if mhz != '0' else 'unpaced', wall, stats(log)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
