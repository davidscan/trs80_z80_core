"""The corpus USR sweep through a pseudo-terminal (FINDING 25's second
recommendation).  Batch cannot reach a USR call that sits behind an INKEY$
menu -- INKEY$ reads whole lines there and a matrix poll sees nothing -- so
this drives each listing the way a person would: the interpreter's
interactive prompt on a pty, ENTER at MEMORY SIZE?, CLOAD, RUN, then a
keystroke script (digits, ENTER, Y, N, space) for a fixed span, the core's
protocol logged per file.  What it measures is whether the routine was
REACHED and what happened to it; the output is not compared.

    python3 tools/usr_pty_sweep.py                      # the batch sweep's "no USR reached" files
    python3 tools/usr_pty_sweep.py --class all          # every USR-mentioning listing
    python3 tools/usr_pty_sweep.py --files a.bas b.bas  # named listings (corpus-relative)

Reads out/usr_sweep/results.json (tools/usr_sweep.py) for the population
unless --files is given; writes out/usr_pty_sweep/results.json and the
per-file protocol logs under out/usr_pty_sweep/runs/.
"""
import argparse, glob, json, os, pty, re, select, signal, sys, time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEV = os.path.dirname(HERE)
CORPUS = os.path.join(os.environ.get('TRS80_CORPUS') or os.path.join(HERE, 'corpus'), 'programs')
BASIC = os.path.join(DEV, 'trs80basic')
CORELOG = os.path.join(HERE, 'tools', 'corelog.sh')
OUT = os.path.join(HERE, 'out', 'usr_pty_sweep')
RUNS, CWD = OUT + '/runs', OUT + '/cwd'
KEYS = ['1', '\r', 'Y', '\r', ' ', '2', '\r', 'N', '\r', '3', '\r', ' ']
SPAN = 12.0          # seconds of keystrokes after RUN
KEY_EVERY = 0.35


def population(cls, files):
    if files:
        return [os.path.join(CORPUS, f) for f in files]
    if cls == 'all':
        out = []
        for f in sorted(glob.glob(CORPUS + '/runnable/*.bas') + glob.glob(CORPUS + '/blocked/*/*.bas')):
            if re.search(rb'(?i)USR', open(f, 'rb').read()):
                out.append(f)
        return out
    res = json.load(open(os.path.join(HERE, 'out', 'usr_sweep', 'results.json')))
    return [os.path.join(CORPUS, r['file']) for r in res if r['cls'] == cls]


def drive(path):
    rel = os.path.relpath(path, CORPUS)
    tag = rel.replace('/', '__')
    env = dict(os.environ, TRS80_Z80='sh %s %s' % (CORELOG, os.path.join(RUNS, tag)),
               TERM='xterm', LINES='24', COLUMNS='80')
    env.pop('TRS80_DUMB', None)
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(CWD)
        os.execvpe(os.path.join(BASIC, 'basic'), ['basic'], env)
    got = [0]

    def pump(t):
        t0 = time.monotonic()
        while time.monotonic() - t0 < t:
            r, _, _ = select.select([fd], [], [], 0.05)
            if r:
                try:
                    got[0] += len(os.read(fd, 65536))
                except OSError:
                    return False
        return True

    def send(s):
        try:
            os.write(fd, s.encode())
        except OSError:
            pass
    alive = pump(1.2); send('\r'); alive = alive and pump(0.8)
    send('CLOAD "%s"\r' % path); alive = alive and pump(2.5)
    send('RUN\r')
    t0 = time.monotonic(); k = 0
    while alive and time.monotonic() - t0 < SPAN:
        alive = pump(KEY_EVERY); send(KEYS[k % len(KEYS)]); k += 1
    send('\x03\x03\x03'); pump(0.5); send('BYE\r'); pump(1.0)
    try:
        os.close(fd)
    except OSError:
        pass
    for sig in (None, signal.SIGTERM, signal.SIGKILL):
        if sig is not None:
            try:
                os.killpg(pid, sig)
            except OSError:
                try:
                    os.kill(pid, sig)
                except OSError:
                    pass
        for _ in range(20):
            try:
                if os.waitpid(pid, os.WNOHANG)[0] == pid:
                    sig = 'done'; break
            except ChildProcessError:
                sig = 'done'; break
            time.sleep(0.1)
        if sig == 'done':
            break
    log_in = log_out = ''
    try:
        log_in = open(os.path.join(RUNS, tag + '.in'), 'rb').read().decode('latin-1')
        log_out = open(os.path.join(RUNS, tag + '.out'), 'rb').read().decode('latin-1')
    except OSError:
        pass
    calls = sum(1 for l in log_in.splitlines() if l.startswith('CALL '))
    rets = sum(1 for l in log_out.splitlines() if l.startswith('RET '))
    errs = [l for l in log_out.splitlines() if l.startswith('ERR ')]
    ks = sum(1 for l in log_out.splitlines() if l.startswith('K '))
    vs = sum(1 for l in log_out.splitlines() if l.startswith('V '))
    entries = sorted(set(int(dict(kv.split('=', 1) for kv in l.split()[1:] if '=' in kv)['entry'])
                         for l in log_in.splitlines() if l.startswith('CALL ')))
    if errs:
        cls = 'err'
    elif calls == 0:
        cls = 'not-reached'
    elif rets == calls:
        cls = 'reached-clean'
    else:
        cls = 'reached-running'
    return dict(file=rel, cls=cls, calls=calls, rets=rets, errs=errs[:2], K=ks, V=vs,
                entries=['%04XH' % e for e in entries[:4]], keys=k, bytes=got[0])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--class', dest='cls', default='no-usr-reached',
                    help="batch sweep class to take, or 'all' (default: no-usr-reached)")
    ap.add_argument('--files', nargs='*', help='corpus-relative listings instead')
    ap.add_argument('--workers', type=int, default=5)
    a = ap.parse_args()
    if not os.path.isdir(CORPUS):
        sys.exit('no corpus archive at %s: link the listing archive as `corpus` at this '
                 "repo's root, or set TRS80_CORPUS (README, Commands)" % os.path.dirname(CORPUS))
    os.makedirs(RUNS, exist_ok=True); os.makedirs(CWD, exist_ok=True)
    pop = population(a.cls, a.files)
    print('population', len(pop), flush=True)
    res = []
    with ThreadPoolExecutor(a.workers) as ex:
        for i, r in enumerate(ex.map(drive, pop)):
            res.append(r)
            if i % 20 == 0:
                print(i, r['file'], r['cls'], r['calls'], flush=True)
    json.dump(res, open(OUT + '/results.json', 'w'), indent=1)
    print(Counter(r['cls'] for r in res))
    roms = Counter()
    for r in res:
        for e in r['errs'][:1]:
            m = re.search(r'called ([0-9A-F]{4}H)', e)
            roms[(m.group(1) if m else e) + (' (no routine)' if 'never written' in e else '')] += 1
    print('ROM entries reached (first ERR per file):', roms.most_common())
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
