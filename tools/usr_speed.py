#!/usr/bin/env python3
"""usr_speed.py -- what a USR routine costs and saves, measured.

    python3 tools/usr_speed.py [--basic PATH] [--repeats N] [--scale F] [--json FILE]

The numbers behind WRITING_USR.md's "When USR pays". Each case is a
BASIC program run in batch mode by the interpreter with this core
attached, timed at two sizes, n and 2n; the rate comes from the
difference, so start-up (gawk loading the interpreter, the core's
Python) cancels out. Each case runs --repeats times (default 3) and the
median is reported.

  stmt        FOR I=1 TO n: A=A+1: NEXT -- BASIC statements a second,
              counted by the interpreter's --steps-report
  call        FOR I=1 TO n: X=USR(0): NEXT with a routine that is one
              RET, against the same loop with X=0: the cost of a call
  fill_basic  1,024 POKEs filling the screen from a BASIC loop
  fill_usr    the same fill by a 17-byte LDIR routine, one USR call
  spin        one USR call running a counted loop: the core's speed as
              a multiple of the Model I's 1.77408 MHz

Timings depend on the host and its load: measure on a quiet machine
(check `uptime`) and keep the inputs this prints beside the numbers.
--scale multiplies every size (a slow host: 0.5). --json writes the
results and their inputs to FILE, replacing it. Standard library only.
"""
import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CLOCK = 1774080            # the Model I's T-states a second

# Every program reserves F000H-FFFFH (HIMEM EFFFH, then CLEAR) and POKEs
# its routines there; addresses above 32767 are written as negatives, as
# Level II's POKE requires.
HEADER = '10 POKE 16561,255: POKE 16562,239: CLEAR 100\n'
RET = [201]                                            # F000H
FILL = [205, 127, 10, 125, 33, 0, 60, 119, 17, 1, 60,  # F010H: CALL 0A7FH / LD A,L
        1, 255, 3, 237, 176, 201]                      # LD HL,3C00H ... LDIR / RET
# F030H: CALL 0A7FH / loop: LD B,0 / DJNZ $ / DEC HL / LD A,H / OR L / JR NZ,loop / RET
SPIN = [205, 127, 10, 6, 0, 16, 254, 43, 124, 181, 32, 247, 201]
SPIN_CYCLES = 13 * 256 - 5 + 6 + 4 + 4 + 12            # one pass of the loop, JR taken


def loader(base, code, line):
    """BASIC lines POKEing code at base (F000H-FFFFH)."""
    neg = base - 65536
    data = ','.join(str(b) for b in code)
    return ('%d FOR I=0 TO %d: READ B: POKE %d+I,B: NEXT: RESTORE\n'
            '%d DATA %s\n' % (line, len(code) - 1, neg, line + 1, data))


def vector(addr):
    return 'POKE 16526,%d: POKE 16527,%d' % (addr % 256, addr // 256)


def program(case, n):
    p = HEADER
    if case == 'stmt':
        p += '20 FOR I=1 TO %d: A=A+1: NEXT\n' % n
    elif case == 'call_base':
        p += '20 FOR I=1 TO %d: X=0: NEXT\n' % n
    elif case == 'call':
        p += loader(0xF000, RET, 20)
        p += '30 %s\n40 FOR I=1 TO %d: X=USR(0): NEXT\n' % (vector(0xF000), n)
    elif case == 'fill_basic':
        p += '20 FOR R=1 TO %d: FOR I=15360 TO 16383: POKE I,191: NEXT: NEXT\n' % n
    elif case == 'fill_usr':
        p += loader(0xF010, FILL, 20)
        p += '30 %s\n40 FOR R=1 TO %d: X=USR(191): NEXT\n' % (vector(0xF010), n)
    elif case == 'spin':
        p += loader(0xF030, SPIN, 20)
        p += '30 %s\n40 X=USR(%d)\n' % (vector(0xF030), n)
    return p


def run(basic, case, n, tmp):
    path = os.path.join(tmp, '%s.bas' % case)
    with open(path, 'w') as fh:
        fh.write(program(case, n))
    rep = os.path.join(tmp, 'steps.txt')
    env = {k: v for k, v in os.environ.items() if not k.startswith('TRS80_')}
    env.update(TRS80_Z80='python3 ' + os.path.join(ROOT, 'core.py'),
               TRS80_USR='strict', TRS80_DUMB='1')
    t0 = time.perf_counter()
    r = subprocess.run([basic, '--steps-report', rep, path], stdin=subprocess.DEVNULL,
                       capture_output=True, env=env, cwd=tmp, timeout=600)
    dt = time.perf_counter() - t0
    if r.returncode != 0 or r.stderr:
        sys.exit('usr_speed: %s n=%d failed (exit %d): %s'
                 % (case, n, r.returncode, r.stderr.decode(errors='replace').strip()))
    with open(rep) as fh:
        steps = int(fh.read().split()[0])
    return dt, steps


def per_unit(basic, case, n, repeats, tmp):
    """Median seconds per unit of n, and statements per unit, from n and 2n."""
    secs, stmts = [], []
    for _ in range(repeats):
        t1, s1 = run(basic, case, n, tmp)
        t2, s2 = run(basic, case, 2 * n, tmp)
        secs.append((t2 - t1) / n)
        stmts.append((s2 - s1) / n)
    return statistics.median(secs), statistics.median(stmts)


def describe(path):
    try:
        return subprocess.run(['git', '-C', path, 'describe', '--always', '--dirty', '--tags'],
                              capture_output=True, text=True).stdout.strip() or 'unknown'
    except OSError:
        return 'unknown'


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--basic', default=os.path.join(os.path.dirname(ROOT), 'trs80basic'),
                    help='the trs80basic checkout (default: beside this repo)')
    ap.add_argument('--repeats', type=int, default=3)
    ap.add_argument('--scale', type=float, default=1.0)
    ap.add_argument('--json', metavar='FILE')
    a = ap.parse_args(argv)
    basic = os.path.join(a.basic, 'basic')
    if not os.path.isfile(basic):
        sys.exit('usr_speed: no interpreter at %s' % basic)
    # about a second each at n on a 2026 laptop
    size = {'stmt': 40000, 'call_base': 5000, 'call': 5000, 'fill_basic': 40,
            'fill_usr': 400, 'spin': 8000}
    size = {k: max(1, int(v * a.scale)) for k, v in size.items()}
    gawk = subprocess.run(['gawk', '--version'], capture_output=True, text=True).stdout
    inputs = {
        'date': time.strftime('%Y-%m-%d %H:%M'),
        'core': describe(ROOT), 'trs80basic': describe(a.basic),
        'python': platform.python_version(), 'gawk': gawk.split('\n')[0],
        'host': '%s %s, %d cores' % (platform.system(), platform.machine(), os.cpu_count()),
        'load_before': os.getloadavg()[0], 'repeats': a.repeats, 'sizes': size,
    }
    res = {}
    with tempfile.TemporaryDirectory() as tmp:
        sec, st = per_unit(basic, 'stmt', size['stmt'], a.repeats, tmp)
        res['statements_per_s'] = st / sec
        base, _ = per_unit(basic, 'call_base', size['call_base'], a.repeats, tmp)
        call, _ = per_unit(basic, 'call', size['call'], a.repeats, tmp)
        res['usr_call_us'] = (call - base) * 1e6
        res['fill_basic_ms'] = per_unit(basic, 'fill_basic', size['fill_basic'], a.repeats, tmp)[0] * 1e3
        res['fill_usr_ms'] = per_unit(basic, 'fill_usr', size['fill_usr'], a.repeats, tmp)[0] * 1e3
        sec, _ = per_unit(basic, 'spin', size['spin'], a.repeats, tmp)
        res['core_x_model1'] = SPIN_CYCLES / sec / CLOCK
    inputs['load_after'] = os.getloadavg()[0]
    print('inputs:', ', '.join('%s %s' % kv for kv in inputs.items()))
    print('BASIC statements a second          %10.0f' % res['statements_per_s'])
    print('one USR call (a bare RET), us      %10.1f' % res['usr_call_us'])
    print('fill the screen by POKE loop, ms   %10.2f' % res['fill_basic_ms'])
    print('fill the screen by USR (LDIR), ms  %10.2f' % res['fill_usr_ms'])
    print('core speed, x the Model I          %10.2f' % res['core_x_model1'])
    if a.json:
        with open(a.json, 'w') as fh:
            json.dump({'inputs': inputs, 'results': res}, fh, indent=1)
            fh.write('\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
