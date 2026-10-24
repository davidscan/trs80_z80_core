"""The corpus USR sweep: every listing with USR evidence
(a call, a DEF USR or a vector POKE: phasea.extract.has_usr), run three ways in batch -- no core, the real core, and the
real core again as the same-build control -- and classified by what the
core changed.  Measurement, not emulator: the corpus is read in place
(the archive's programs/, runnable/ and blocked/*, through the `corpus`
link at this repo's root or TRS80_CORPUS), the
interpreter is the peer checkout (../trs80basic), and the protocol of
every core run is logged per file so the ROM entry a routine reached, the
frame it was given and the calls it made can be read afterwards.

    python3 tools/usr_sweep.py            # ~10 minutes; writes out/usr_sweep/

It refuses (exit 2, results.json untouched) on an empty population or an
input set that is not phasea/sweep.py's pinned one (--accept-input-set),
and publishes nothing (exit 1) when the core never started in a run:
such a listing is `core-failed`, not a class of the measurement.

results.json is {"inputs": ..., "results": [...]}: the inputs are the
core's and the interpreter's commits (+dirty), the interpreter's
--version, the corpus commit, the input-set fingerprint, the controls,
the worker count and the host load at start and end; each result names
its class and how each of the three runs stopped (`stop`).  A run that
reached no USR is `error-before-usr` when the stub run stopped on an
interpreter error, `no-usr-reached` otherwise (INPUT ran dry, a CMD, a
menu, a quiet end).

Controls (the corpus measurement traps): --seed 1, the oracle's stdin feed
of 400 "1" lines, a same-build control run, gawk diagnostics and the two
USR notices dropped before comparing, a fresh cwd per run (under the
gitignored out/usr_sweep/cwd, never a repo's own tree).  Batch has
no keyboard: a routine that polls the matrix sees 0 and, at the end of
stdin, BREAK; a program's INKEY$ menu gets "1".
"""
import glob, json, os, re, shutil, signal, subprocess, sys, time
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
WORKERS = 6

def listings():
    return sorted(glob.glob(CORPUS + '/runnable/*.bas') + glob.glob(CORPUS + '/blocked/*/*.bas'))


def population(files=None):
    # the extractor's USR evidence, the gate's own definition (ZM-9: a
    # substring search put 20 non-callers into the published 606, and
    # 28 more, USR in DATA tables and damaged bytes, into the 586 after it)
    sys.path.insert(0, HERE)
    from phasea.extract import has_usr
    return [f for f in (listings() if files is None else files) if has_usr(f)]


def refusal(files, pop, accept=False):
    """Why this run must not publish, or None.  A tree with no listings
    gave population 0, "DONE", exit 0 and overwrote results.json with []
    (ZM-11); the listings are phasea/sweep.py's pinned input set."""
    sys.path.insert(0, HERE)
    from phasea.sweep import input_set_problem
    why = input_set_problem(files, CORPUS)
    if not files or not pop:
        return why or 'no listing in the input set calls USR'
    return None if accept else why


def publish(res, path):
    """Write results.json whole or not at all: usr_pty_sweep reads it as
    its population, and out/ is not versioned."""
    tmp = path + '.tmp'
    with open(tmp, 'w') as fh:
        json.dump(res, fh, indent=1)
    os.replace(tmp, path)

# A sweep is a MEASUREMENT, so the environment it runs listings in cannot
# be whoever's shell started it.  Both sweeps inherited it whole, so a
# TRS80_USR=strict left over from a debugging session turned every
# un-executed USR into ?FC, TRS80_SOUND started a player per listing, and
# TRS80_PRINTER collected every LPRINT in the corpus into one file (the
# 2026-09-19 audit, L-65).  tools/kbd_probe.py has stripped them from the
# start; phasea/oracle.py does since L-64.
def sweep_env(**over):
    # A denylist rots as the interpreter grows knobs (ZL-8: TRS80_MEMORY,
    # the memory-host switch, was not on it), so every TRS80_* is dropped
    # and the measurement sets the ones it means.
    env = dict(os.environ, LC_ALL='C')
    for v in [k for k in env if k.startswith('TRS80_')]:
        env.pop(v, None)
    env.update(over)
    return env


def run(path, z80, cwd):
    # each run gets a FRESH cwd: a high-score or data file a listing wrote
    # reached the next run under the shared one, so the stub/core/control
    # comparison measured leftovers, not the build (ZL-9)
    shutil.rmtree(cwd, ignore_errors=True)
    os.makedirs(cwd)
    env = sweep_env(TRS80_Z80=z80, TRS80_DUMB='1')
    t0 = time.monotonic()
    p = subprocess.Popen([BASIC, '--seed', '1', path], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, env=env, cwd=cwd, start_new_session=True)
    try:
        out, err = p.communicate(FEED, timeout=TIMEOUT); rc = p.returncode; to = False
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL); out, err = p.communicate(); rc, to = 124, True
    return dict(rc=rc, timeout=to, out=out.decode('latin-1'), err=err.decode('latin-1'), secs=round(time.monotonic() - t0, 2))

def stop(r):
    """How the run ended, as the interpreter said it on stderr: its first
    line that is not a gawk diagnostic or a USR notice ('?OV ERROR IN 12'),
    or '' for a quiet end."""
    for l in r['err'].splitlines():
        if l.strip() and not l.startswith(('gawk:', 'USR STUB:', 'USR CORE:')):
            return l.strip()
    return ''


BASIC_ERROR_RE = re.compile(r'^\?[A-Z/0-9]{2} ERROR')

# the interpreter's notices for a core that never ran: it could not be
# started, or it answered the handshake with another protocol (p77)
NEVER_STARTED_RE = re.compile(r"^USR CORE: (cannot start '|'.*' speaks protocol )")


def never_started(r):
    """True when the run's core never ran and USR fell back to the stub:
    then the run measured the stub twice, and a listing whose stub run
    counted calls was published as 'stub-only-reached' (ZL-7)."""
    return any(NEVER_STARTED_RE.match(l) for l in r['err'].splitlines())


def git_state(repo):
    """'<commit>' or '<commit>+dirty' for the repo at `repo`; '?' if none."""
    try:
        head = subprocess.run(['git', '-C', repo, 'rev-parse', '--short', 'HEAD'],
                              capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(['git', '-C', repo, 'status', '--porcelain', '--untracked-files=no'],
                               capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return '?'
    return head + ('+dirty' if dirty else '')


def inputs(files, pop):
    """What this measurement ran on, recorded beside its numbers (ZM-8:
    the class table could not be reproduced, and nothing said which
    interpreter, core, corpus or host load had produced it)."""
    sys.path.insert(0, HERE)
    from phasea.sweep import fingerprint
    try:
        version = subprocess.run([BASIC, '--version'], capture_output=True, text=True,
                                 env=sweep_env(), timeout=30).stdout.strip().splitlines()[0]
    except (OSError, IndexError, subprocess.TimeoutExpired):
        version = '?'
    return dict(core=git_state(HERE), interpreter=git_state(os.path.dirname(BASIC)),
                interpreter_version=version, corpus=git_state(os.path.dirname(CORPUS)),
                listings=len(files), input_set=fingerprint(files, CORPUS), population=len(pop),
                seed=1, feed='400 lines of "1"', timeout_s=TIMEOUT, workers=WORKERS,
                python=sys.version.split()[0], started=time.strftime('%Y-%m-%dT%H:%M:%S'),
                load_start=[round(x, 2) for x in os.getloadavg()])


def norm(r):
    lines = (r['out'] + '\n--stderr--\n' + r['err']).splitlines()
    return '\n'.join(l for l in lines if not l.startswith(('gawk:', 'USR STUB:', 'USR CORE:')))

def clear_logs(base):
    """Remove base.in and base.out before a logged run.  The interpreter
    starts the core at the first USR call, so a listing that never reaches
    one writes no log -- and the log a previous sweep left under the same
    name would be counted as this run's calls, RETs and ERRs: exactly the
    listing a re-sweep exists to catch (the 2026-09-19 audit, H-22)."""
    for ext in ('.in', '.out'):
        try:
            os.remove(base + ext)
        except FileNotFoundError:
            pass

def one(path):
    rel = os.path.relpath(path, CORPUS)
    tag = rel.replace('/', '__')
    clear_logs(RUNS + '/' + tag)
    stub = run(path, '', CWD + '/' + tag)
    core = run(path, 'sh %s %s' % (CORELOG, RUNS + '/' + tag), CWD + '/' + tag)
    ctrl = run(path, CORE, CWD + '/' + tag)
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
    if never_started(core) or never_started(ctrl): cls = 'core-failed'   # not a measurement
    elif errs: cls = 'err'
    elif core['timeout'] and not stub['timeout']: cls = 'timeout-core-only'
    elif core['timeout']: cls = 'timeout-both'
    elif calls == 0 and tally == 0 and BASIC_ERROR_RE.match(stop(stub)):
        cls = 'error-before-usr'      # the run stopped on an interpreter error (ZM-8)
    elif calls == 0 and tally == 0: cls = 'no-usr-reached'
    elif calls == 0 and tally > 0: cls = 'stub-only-reached'
    elif equal: cls = 'identical'
    elif stable: cls = 'differs-stable'
    else: cls = 'differs-noise'
    return dict(file=rel, cls=cls, tally=tally, calls=calls, rets=rets, errs=errs, notices=notices, K=ks, V=vs, MODE=modes,
                rc=[stub['rc'], core['rc'], ctrl['rc']], timeout=[stub['timeout'], core['timeout'], ctrl['timeout']],
                secs=[stub['secs'], core['secs'], ctrl['secs']], equal=equal, stable=stable,
                stop=[stop(stub), stop(core), stop(ctrl)])

def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not os.path.isdir(CORPUS):
        sys.exit('no corpus archive at %s: link the listing archive as `corpus` at this '
                 "repo's root, or set TRS80_CORPUS (README, Commands)" % os.path.dirname(CORPUS))
    files = listings()
    pop = population(files)
    print('population', len(pop), 'of', len(files), 'listings', flush=True)
    why = refusal(files, pop, '--accept-input-set' in argv)
    if why:
        print('REFUSING TO MEASURE: %s.  --accept-input-set runs a changed (non-empty) set; '
              'results.json is left as it was.' % why, flush=True)
        return 2
    os.makedirs(RUNS, exist_ok=True); os.makedirs(CWD, exist_ok=True)
    meta = inputs(files, pop)
    print('inputs', json.dumps(meta), flush=True)
    res = []
    with ThreadPoolExecutor(WORKERS) as ex:
        for i, r in enumerate(ex.map(one, pop)):
            res.append(r)
            if i % 25 == 0: print(i, r['file'], r['cls'], flush=True)
    failed = sum(1 for r in res if r['cls'] == 'core-failed')
    if failed:
        print('REFUSING TO PUBLISH: the core never started in %d of %d listings (%s); '
              'results.json is left as it was.' % (failed, len(res), CORE), flush=True)
        return 1
    meta.update(finished=time.strftime('%Y-%m-%dT%H:%M:%S'),
                load_end=[round(x, 2) for x in os.getloadavg()])
    publish(dict(inputs=meta, results=res), OUT + '/results.json')
    print(Counter(r['cls'] for r in res))
    roms = Counter()
    for r in res:
        for e in r['errs'][:1]:
            m = re.search(r'called ([0-9A-F]{4}H)', e)
            roms[m.group(1) if m else e] += 1
    print('ROM entries reached (first ERR per file):', roms.most_common())
    print('DONE', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
