"""The corpus USR sweep (Z80_FINDINGS FINDING 25): every listing that
mentions USR, run three ways in batch -- no core, the real core, and the
real core again as the same-build control -- and classified by what the
core changed.  Measurement, not emulator: the corpus is read in place
(the archive's programs/, runnable/ and blocked/*, through the `corpus`
link at this repo's root or TRS80_CORPUS), the
interpreter is the peer checkout (../trs80basic), and the protocol of
every core run is logged per file so the ROM entry a routine reached, the
frame it was given and the calls it made can be read afterwards.

    python3 tools/usr_sweep.py            # ~10 minutes; writes out/usr_sweep/

Controls (the corpus measurement traps): --seed 1, the oracle's stdin feed
of 400 "1" lines, a same-build control run, gawk diagnostics and the two
USR notices dropped before comparing, cwd outside both repos.  Batch has
no keyboard: a routine that polls the matrix sees 0 and, at the end of
stdin, BREAK; a program's INKEY$ menu gets "1".
"""
import glob, json, os, re, signal, subprocess, sys, time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEV = os.path.dirname(HERE)
CORPUS = os.path.join(os.environ.get('TRS80_CORPUS') or os.path.join(HERE, 'corpus'), 'programs')
BASIC = os.path.join(DEV, 'trs80basic', 'basic')
CORELOG = os.path.join(HERE, 'tools', 'corelog.sh')
CORE = 'python3 ' + os.path.join(HERE, 'core.py')
OUT = os.path.join(HERE, 'out', 'usr_sweep')
RUNS, CWD = OUT + '/runs', OUT + '/cwd'
FEED = ('1\n' * 400).encode()
TIMEOUT = 10.0

def population():
    files = sorted(glob.glob(CORPUS + '/runnable/*.bas') + glob.glob(CORPUS + '/blocked/*/*.bas'))
    keep = []
    for f in files:
        if re.search(rb'(?i)USR', open(f, 'rb').read()):
            keep.append(f)
    return keep

def run(path, z80):
    env = dict(os.environ, TRS80_Z80=z80, TRS80_DUMB='1')
    env.pop('TRS80_MHZ', None)
    t0 = time.monotonic()
    p = subprocess.Popen([BASIC, '--seed', '1', path], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, env=env, cwd=CWD, start_new_session=True)
    try:
        out, err = p.communicate(FEED, timeout=TIMEOUT); rc = p.returncode; to = False
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL); out, err = p.communicate(); rc, to = 124, True
    return dict(rc=rc, timeout=to, out=out.decode('latin-1'), err=err.decode('latin-1'), secs=round(time.monotonic() - t0, 2))

def norm(r):
    lines = (r['out'] + '\n--stderr--\n' + r['err']).splitlines()
    return '\n'.join(l for l in lines if not l.startswith(('gawk:', 'USR STUB:', 'USR CORE:')))

def one(path):
    rel = os.path.relpath(path, CORPUS)
    tag = rel.replace('/', '__')
    stub = run(path, '')
    core = run(path, 'sh %s %s' % (CORELOG, RUNS + '/' + tag))
    ctrl = run(path, CORE)
    log = ''
    try: log = open(RUNS + '/' + tag + '.out', 'rb').read().decode('latin-1')
    except OSError: pass
    calls = 0
    try: calls = sum(1 for l in open(RUNS + '/' + tag + '.in', 'rb').read().decode('latin-1').splitlines() if l.startswith('CALL '))
    except OSError: pass
    rets = sum(1 for l in log.splitlines() if l.startswith('RET '))
    errs = [l for l in log.splitlines() if l.startswith('ERR ')]
    ks = sum(1 for l in log.splitlines() if l.startswith('K '))
    vs = sum(1 for l in log.splitlines() if l.startswith('V '))
    modes = sum(1 for l in log.splitlines() if l.startswith('MODE '))
    m = re.search(r'USR STUB: (\d+) CALL', stub['err'])
    tally = int(m.group(1)) if m else 0
    notices = [l for l in core['err'].splitlines() if l.startswith('USR CORE:')]
    equal = norm(stub) == norm(core); stable = norm(core) == norm(ctrl)
    if errs: cls = 'err'
    elif core['timeout'] and not stub['timeout']: cls = 'timeout-core-only'
    elif core['timeout']: cls = 'timeout-both'
    elif calls == 0 and tally == 0: cls = 'no-usr-reached'
    elif calls == 0 and tally > 0: cls = 'stub-only-reached'
    elif equal: cls = 'identical'
    elif stable: cls = 'differs-stable'
    else: cls = 'differs-noise'
    return dict(file=rel, cls=cls, tally=tally, calls=calls, rets=rets, errs=errs, notices=notices, K=ks, V=vs, MODE=modes,
                rc=[stub['rc'], core['rc'], ctrl['rc']], timeout=[stub['timeout'], core['timeout'], ctrl['timeout']],
                secs=[stub['secs'], core['secs'], ctrl['secs']], equal=equal, stable=stable)

if __name__ == '__main__':
    os.makedirs(RUNS, exist_ok=True); os.makedirs(CWD, exist_ok=True)
    pop = population()
    print('population', len(pop), flush=True)
    res = []
    with ThreadPoolExecutor(6) as ex:
        for i, r in enumerate(ex.map(one, pop)):
            res.append(r)
            if i % 25 == 0: print(i, r['file'], r['cls'], flush=True)
    json.dump(res, open(OUT + '/results.json', 'w'), indent=1)
    print(Counter(r['cls'] for r in res))
    roms = Counter()
    for r in res:
        for e in r['errs'][:1]:
            m = re.search(r'called ([0-9A-F]{4}H)', e)
            roms[m.group(1) if m else e] += 1
    print('ROM entries reached (first ERR per file):', roms.most_common())
    print('DONE', flush=True)
