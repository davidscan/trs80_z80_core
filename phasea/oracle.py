"""FINDING 7's dynamic extraction oracle -- the escalation path, built.

96 USR listings have a real machine-language loader whose address or
bounds static extraction cannot resolve: bases computed from INPUT,
bases built from other variables, and one loader assembled inside a
string. DESIGN.md "LOADER EXTRACTION" records the fallback:

    for loaders static extraction cannot crack, the interpreter
    is the extraction ORACLE -- run the listing under the shipped USR
    stub until the first USR call and dump the poked bytes from mem[].
    Dynamic fallback, static default.

This is that. It is MEASUREMENT, not emulator: it runs BASIC under the
companion interpreter (../trs80basic) and reads what the loader deposited. No
Z80 executes anywhere in this module.

HOW THE INTERPRETER IS INSTRUMENTED, AND WHY IT IS NOT MODIFIED. The
interpreter is a PEER (../trs80basic since the 2026-08-28 split; the
corpus is the only thing this module reads from ../awk_BASIC_interpreter),
and its repo is not touched. `build()` copies its `src/p*.awk` into out/, adds
two lines, and concatenates a scratch interpreter exactly the way the
interpreter's own build does (`cat src/p*.awk > trs80basic.awk`). Both added
lines are gated on TRS80_POKELOG being present in the environment, so
with the variable unset the scratch build is behaviorally identical to
the shipped one -- the instrumentation cannot perturb what it measures.
Interpreter-owned code stays interpreter-owned (CLAUDE.md standing
split); this is a harness in THIS repo that happens to drive a peer's code.

    p80_stmt.awk  st_poke   -- log every (address, byte) actually poked,
                               after the interpreter's own normalisation
                               and BEFORE its device dispatch, so we see
                               what the program wrote regardless of where
                               it landed.
    p60_eval.awk  USR stub  -- emit a marker when a USR call is reached.

The log is flushed per line on purpose: a listing that never halts is
killed by the runner's timeout, and an unflushed buffer would take the
loader bytes with it.

WHY THE MARKER RATHER THAN AN EXIT. Stopping the interpreter mid-
expression would mean surgery on its control flow; a marker plus a
timeout gets the same cut point (we read pokes up to the first USR)
with two purely additive lines. Pokes after the marker are ignored.

TRUST DISCIPLINE. CLAUDE.md "ANCHORS BEFORE TRUST" applies to the
oracle exactly as it applied to the opcode table and the classifier:
`python3 -m phasea.oracle --validate` runs it over the files static
extraction ALREADY resolves and checks that it recovers the same bytes
at the same base. An oracle that cannot reproduce known-good
extractions is not evidence about the unresolvable ones. Run that
before believing any number this module produces.

Usage:
    python3 -m phasea.oracle --validate       # against static ground truth
    python3 -m phasea.oracle --run            # over the 96
"""

import argparse
import json
import os
import re

import subprocess
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phasea.extract import extract_file                        # noqa: E402
from phasea.classify import classify                           # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Two neighbours, not one. The interpreter moved to ../trs80basic on
# 2026-08-28; the corpus stayed in ../awk_BASIC_interpreter, which keeps a
# duplicate of src/ that is scheduled for deletion there. Build from the
# live interpreter, read listings from the archive.
INTERP_REPO = '../trs80basic'
CORPUS = '../awk_BASIC_interpreter'
SRC = os.path.join(INTERP_REPO, 'src')
PROGRAMS = os.path.join(CORPUS, 'programs')
OUT = os.path.join(HERE, 'out', 'oracle')
INTERP = os.path.join(OUT, 'trs80basic-oracle.awk')

# Video RAM and the other device windows the interpreter maps. A run landing
# wholly inside video is screen data, not a routine -- FINDING 5's
# discrimination, applied to dynamic output too.
VIDEO = (15360, 16383)
RNDPOKE = (16554, 16556)
PRINTER = (14312, 14313)


# --------------------------------------------------------------------
# the instrumented build
# --------------------------------------------------------------------
# (module, exact text to find, replacement). Exact-match, single
# occurrence, asserted -- if the interpreter's source moves under us the
# build fails loudly rather than silently instrumenting nothing.

PATCHES = [
    ('p80_stmt.awk',
     '    b = bfloor(num(v)) % 256\n'
     '    if (b < 0) b += 256\n',
     '    b = bfloor(num(v)) % 256\n'
     '    if (b < 0) b += 256\n'
     '    if ("TRS80_POKELOG" in ENVIRON) {\n'
     '        print a, b > (ENVIRON["TRS80_POKELOG"])\n'
     '        fflush(ENVIRON["TRS80_POKELOG"])\n'
     '    }\n'),
    # Line trace, gated on TRS80_LINELOG. A listing that never halts is
    # the most interesting outcome the oracle can produce -- IF the loop
    # it is stuck in reads a USR result, a working core would break it.
    # That is a claim about a specific loop, so it has to be measured
    # rather than assumed: liongrp2.bas hangs in `120 X=USR(0):GOTO 110`
    # where line 110 is a REM, and would hang identically with a perfect
    # Z80. Only the trace can tell the two apart.
    ('p70_exec.awk',
     '        SK = CK; SLI = CLI; SCP = CP\n'
     '        execstmt()\n',
     '        if ("TRS80_LINELOG" in ENVIRON && CLN != LASTTRACELN) {\n'
     '            LASTTRACELN = CLN\n'
     '            print CLN > (ENVIRON["TRS80_LINELOG"])\n'
     '        }\n'
     '        SK = CK; SLI = CLI; SCP = CP\n'
     '        execstmt()\n'),
    # Re-anchored 2026-09-10 (usr_resolve made the one-line body a block)
    # and again 2026-09-11 (the p77 shim added a z80_usr() call to it).
    # The body has changed twice in two days, so the anchor is now the
    # block's OPENING LINE only -- unique in p60 (the tokenizer's twin at
    # the top of the file tests `s`, not `name`) -- and the marker goes
    # immediately inside the brace, before numarg, as before. The body
    # can change again without moving this patch point.
    ('p60_eval.awk',
     '    if (name ~ /^USR[0-9]?$/) {\n',
     '    if (name ~ /^USR[0-9]?$/) {\n'
     '        if ("TRS80_POKELOG" in ENVIRON) {\n'
     '            print "USR", name > (ENVIRON["TRS80_POKELOG"])\n'
     '            fflush(ENVIRON["TRS80_POKELOG"])\n'
     '        }\n'),
]


def build(force=False):
    """Concatenate an instrumented interpreter into out/. Returns its path."""
    if os.path.exists(INTERP) and not force:
        return INTERP
    os.makedirs(OUT, exist_ok=True)
    mods = sorted(n for n in os.listdir(SRC) if n.endswith('.awk'))
    if not mods:
        sys.exit('no interpreter sources at %s' % SRC)

    applied = 0
    chunks = []
    for name in mods:
        with open(os.path.join(SRC, name)) as f:
            text = f.read()
        for mod, old, new in PATCHES:
            if mod != name:
                continue
            n = text.count(old)
            if n != 1:
                sys.exit('patch point in %s matched %d times, expected 1 -- '
                         'the interpreter source has moved; re-verify the patch'
                         % (name, n))
            text = text.replace(old, new)
            applied += 1
        chunks.append(text)

    if applied != len(PATCHES):
        sys.exit('applied %d of %d patches' % (applied, len(PATCHES)))

    with open(INTERP, 'w') as f:
        f.write(''.join(chunks))
    subprocess.run(['gawk', '-f', INTERP, '--', '-h'],
                   capture_output=True, check=False)
    return INTERP


# --------------------------------------------------------------------
# running one listing
# --------------------------------------------------------------------

# Neutral answers for listings that INPUT before they POKE. '1' is a
# valid numeric answer and a harmless string. This is a CHOICE and it
# is recorded per-file: a program that branches on its input may take a
# different path under the oracle than under a human.
FEED = ('1\n' * 400).encode()


def run_listing(path, timeout=10.0):
    """Run one listing under the instrumented interpreter.

    Returns dict(rc, pokes, usr_seen, timed_out). `pokes` is the
    ordered (addr, byte) log truncated at the first USR marker.
    """
    log = os.path.join(OUT, 'pokelog.txt')
    if os.path.exists(log):
        os.remove(log)
    env = dict(os.environ, TRS80_POKELOG=log)
    timed_out = False
    try:
        r = subprocess.run(
            ['gawk', '-f', INTERP, '--', '--seed', '1', path],
            input=FEED, capture_output=True, env=env,
            cwd=os.path.dirname(path), timeout=timeout)
        rc, err = r.returncode, r.stderr.decode('latin-1', 'replace')
    except subprocess.TimeoutExpired:
        rc, timed_out, err = 124, True, ''

    # The reason a listing yields nothing is itself the measurement --
    # "?SN before the loader" and "waiting for input" are different
    # facts about whether a core could ever help this file.
    err = '\n'.join(ln for ln in err.splitlines()
                    if not ln.startswith('gawk:'))          # locale warnings
    reason = ''
    for ln in err.splitlines():
        if ln.startswith('?'):
            reason = ln.strip()
            break

    pokes, usr_seen = [], False
    if os.path.exists(log):
        with open(log) as f:
            for line in f:
                parts = line.split()
                if not parts:
                    continue
                if parts[0] == 'USR':
                    usr_seen = True
                    break                    # cut at the first USR call
                try:
                    pokes.append((int(parts[0]), int(parts[1])))
                except (ValueError, IndexError):
                    continue
    return {'rc': rc, 'pokes': pokes, 'usr_seen': usr_seen,
            'timed_out': timed_out, 'reason': reason}


def runs_from_pokes(pokes, min_len=4):
    """Contiguous address runs, last write wins. Returns [(base, bytes)]."""
    if not pokes:
        return []
    final = {}
    for a, b in pokes:
        final[a] = b
    addrs = sorted(final)
    out, start, prev = [], addrs[0], addrs[0]
    for a in addrs[1:]:
        if a == prev + 1:
            prev = a
            continue
        out.append((start, bytes(final[x] for x in range(start, prev + 1))))
        start = prev = a
    out.append((start, bytes(final[x] for x in range(start, prev + 1))))
    return [(b, d) for b, d in out if len(d) >= min_len]


def region_of(base, data):
    """FINDING 5's discrimination applied to a dynamic run."""
    end = base + len(data) - 1
    if base >= VIDEO[0] and end <= VIDEO[1]:
        return 'screen-data'
    if base >= PRINTER[0] and end <= PRINTER[1] + 1:
        return 'device-stream'
    if base >= RNDPOKE[0] and end <= RNDPOKE[1]:
        return 'device-stream'
    return 'candidate-ml'


# --------------------------------------------------------------------
# FINDING 15: is a hanging listing actually waiting on a USR result?
# --------------------------------------------------------------------
# This is the analysis that holds the gate number down, so it lives in
# the module rather than in a scratch script: 13 of the resolved
# listings hang under the stub, and the tempting reading is that a
# working core would release all 13. Measured, it releases one.

def strip_basic_comments(line):
    """Drop ' ... and REM ... tails.

    Not cosmetic. liongrp2.bas's spin cycle is
        110 ' X$=INKEY$:IF X$=""110
        120 X=USR(0): GOTO 110
    Line 110 is a REM, so the loop is unconditional and a perfect Z80
    changes nothing -- but the commented-out text contains both an IF
    and the variable USR was assigned to, so an analysis that reads the
    raw source calls it USR-gated. It is the difference between
    reporting 13 unlocks and reporting 1.
    """
    return re.sub(r'\bREM\b.*$', '', re.sub(r"'.*$", '', line), flags=re.I)


def spin_cycle(trace, max_period=60):
    """Shortest repeating suffix of a line-number trace, else the tail set."""
    tail = trace[-2000:]
    for p in range(1, max_period):
        if len(tail) > 4 * p and all(tail[-i - 1] == tail[-i - 1 - p]
                                     for i in range(3 * p)):
            return tail[-p:], p
    return sorted(set(tail[-30:]), key=lambda x: int(x)), None


def analyse_hang(path, timeout=8.0):
    """Trace one hanging listing and decide whether USR gates its loop."""
    log = os.path.join(OUT, 'linelog.txt')
    if os.path.exists(log):
        os.remove(log)
    env = dict(os.environ, TRS80_LINELOG=log)
    try:
        subprocess.run(['gawk', '-f', INTERP, '--', '--seed', '1', path],
                       input=FEED, capture_output=True, env=env,
                       cwd=os.path.dirname(path), timeout=timeout)
    except subprocess.TimeoutExpired:
        pass
    if not os.path.exists(log):
        return {'file': os.path.basename(path), 'verdict': 'no-trace'}
    with open(log) as f:
        trace = [ln.strip() for ln in f if ln.strip()]
    cycle, period = spin_cycle(trace)

    src = {}
    with open(path, encoding='latin-1') as f:
        for line in f:
            m = re.match(r'\s*(\d+)\s', line)
            if m:
                src.setdefault(m.group(1), strip_basic_comments(line.rstrip()))
    body = ' '.join(src.get(n, '') for n in cycle).upper()
    uvars = set(re.findall(r'([A-Z][A-Z0-9]?)\s*=\s*USR', body))
    gated = [v for v in uvars if re.search(r'\bIF\b[^:]*\b%s\b' % v, body)]
    if 'USR' not in body:
        verdict = 'no-usr-in-cycle'
    elif gated:
        verdict = 'usr-gates-the-loop'
    else:
        verdict = 'unconditional-loop'
    return {'file': os.path.basename(path), 'verdict': verdict,
            'period': period, 'cycle': cycle[:12], 'usr_vars': sorted(uvars)}


# --------------------------------------------------------------------
# validation: the oracle against static ground truth
# --------------------------------------------------------------------

def static_payloads(path):
    """The statically-extracted candidate-ML payloads with a real base.

    Payload.bytes is a list of ints; the oracle's runs are bytes
    objects, so normalise here rather than at every comparison.
    """
    rep = extract_file(path)
    return [(p.base, bytes(p.bytes)) for p in rep.payloads
            if p.kind == 'candidate-ml' and isinstance(p.base, int)
            and p.bytes]


def compare(want_data, got_run, want_base, got_base):
    """Tier one static payload against the oracle's run.

    THE CRITERION IS NOT BYTE EQUALITY, and the first version of this
    function got that wrong. A loader routinely deposits DATA literals
    and then POKEs runtime values into them before calling USR:
    quest_2.bas ships `LD H,00H / LD L,00H / LD C,00H` and pokes pitch
    20 and duration 50 into those operands. Static extraction sees the
    placeholders; the oracle sees the routine as the CPU would.
    Byte-inequality there is the oracle being right, not wrong.

    Returns 'exact' | 'patched' | 'contradiction'.
    """
    off = want_base - got_base
    if off < 0 or off + len(want_data) > len(got_run):
        return 'contradiction'
    seg = got_run[off:off + len(want_data)]
    diffs = sum(1 for a, b in zip(want_data, seg) if a != b)
    if diffs == 0:
        return 'exact'
    # A patch touches operand bytes, not the instruction stream. Allow a
    # small minority; anything more is a different routine, not a patch.
    if diffs <= max(4, len(want_data) // 10):
        return 'patched'
    return 'contradiction'


def validate(files, timeout=10.0, verbose=False):
    """Does the oracle recover what static extraction already knows?

    The property that matters is NOT coverage -- it is that the oracle
    never CONTRADICTS a known-good extraction. A fallback that stays
    silent where it cannot see is safe; one that invents payloads is
    not. Coverage is reported too, because the silent cases turn out to
    carry their own finding.
    """
    tally = Counter()
    details = []
    for path in files:
        want = static_payloads(path)
        if not want:
            continue
        got = run_listing(path, timeout)
        runs = runs_from_pokes(got['pokes'])
        per = []
        for want_base, want_data in want:
            best = 'contradiction'
            for got_base, got_run in runs:
                v = compare(want_data, got_run, want_base, got_base)
                if v == 'exact':
                    best = 'exact'
                    break
                if v == 'patched':
                    best = 'patched'
            per.append(best)

        if not runs:
            status = 'silent'
        elif 'contradiction' in per:
            status = 'contradiction'
        elif 'patched' in per:
            status = 'patched'
        else:
            status = 'exact'
        tally[status] += 1
        details.append({'file': os.path.basename(path), 'status': status,
                        'payloads': per, 'rc': got['rc'],
                        'usr': got['usr_seen'], 'timed_out': got['timed_out']})
        if verbose:
            print('  %-28s %-13s payloads=%s rc=%s%s'
                  % (os.path.basename(path), status, ','.join(per),
                     got['rc'], ' TIMEOUT' if got['timed_out'] else ''))
    return {'tally': dict(tally), 'details': details}


# --------------------------------------------------------------------
# the run over the unresolvable 96
# --------------------------------------------------------------------

def resolve(path, timeout=10.0):
    """Run one unresolvable listing and classify whatever it deposited."""
    got = run_listing(path, timeout)
    out = {'file': os.path.basename(path), 'rc': got['rc'],
           'usr_seen': got['usr_seen'], 'timed_out': got['timed_out'],
           'reason': got['reason'], 'n_pokes': len(got['pokes']),
           'payloads': []}
    for base, data in runs_from_pokes(got['pokes']):
        region = region_of(base, data)
        rec = {'base': base, 'length': len(data), 'region': region}
        if region == 'candidate-ml':
            c = classify(data, base=base)
            q = c.quality
            rec.update({
                'bucket': c.bucket, 'buckets': c.buckets_all,
                'evidence': c.evidence, 'stage1_ok': c.stage1_ok,
                'rom_calls': [a for a, _n in c.rom_calls],
                'stage2_traps': c.stage2_traps,
                'strict_formed': (q['invalid_in_reachable'] == 0
                                  and q['ends_exactly_on_ret']
                                  and q['coverage'] >= 0.9),
                'well_formed': (q['invalid_in_reachable'] == 0
                                and q['has_ret'] and q['coverage'] >= 0.5),
            })
        out['payloads'].append(rec)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--validate', action='store_true')
    ap.add_argument('--run', action='store_true')
    ap.add_argument('--hangs', action='store_true',
                    help='FINDING 15: do the hanging listings wait on USR?')
    ap.add_argument('--files', help='JSON list of corpus-relative keys')
    ap.add_argument('--timeout', type=float, default=10.0)
    ap.add_argument('--limit', type=int)
    ap.add_argument('--json', help='write results here')
    ap.add_argument('--verbose', action='store_true')
    ap.add_argument('--rebuild', action='store_true')
    args = ap.parse_args()

    build(force=args.rebuild)
    print('instrumented interpreter: %s' % os.path.relpath(INTERP, HERE))

    keys = json.load(open(args.files)) if args.files else []
    paths = []
    for k in keys:
        cat, name = k.split('/', 1)
        p = (os.path.join(PROGRAMS, 'runnable', name) if cat == 'runnable'
             else os.path.join(PROGRAMS, 'blocked', cat, name))
        if os.path.exists(p):
            paths.append(p)
    if args.limit:
        paths = paths[:args.limit]

    if args.validate:
        print('validating the oracle against static ground truth '
              '(%d files)' % len(paths))
        res = validate(paths, args.timeout, args.verbose)
        t = res['tally']
        n = sum(t.values())
        print()
        print('  exact          %3d   byte-identical to static extraction'
              % t.get('exact', 0))
        print('  patched        %3d   same routine, runtime-poked operands'
              % t.get('patched', 0))
        print('  silent         %3d   oracle produced nothing' % t.get('silent', 0))
        print('  CONTRADICTION  %3d   must be zero to trust the oracle'
              % t.get('contradiction', 0))
        print('  --- %d files; agreement where it spoke: %d/%d'
              % (n, t.get('exact', 0) + t.get('patched', 0),
                 n - t.get('silent', 0)))
        if args.json:
            json.dump(res, open(args.json, 'w'), indent=1)
        return 0 if not t.get('contradiction') else 1

    if args.hangs:
        print('tracing %d hanging listing(s)' % len(paths))
        res = [analyse_hang(p, args.timeout) for p in paths]
        tally = Counter(r['verdict'] for r in res)
        for r in res:
            print('  %-24s %-20s cycle=%s' % (r['file'], r['verdict'],
                                              ','.join(r.get('cycle') or [])[:28]))
        print()
        for k, v in tally.most_common():
            print('  %-24s %d' % (k, v))
        print('\n  a working core releases %d of %d'
              % (tally.get('usr-gates-the-loop', 0), len(res)))
        if args.json:
            json.dump(res, open(args.json, 'w'), indent=1)
        return 0

    if args.run:
        print('running the oracle over %d listing(s)' % len(paths))
        results = []
        for i, p in enumerate(paths, 1):
            r = resolve(p, args.timeout)
            results.append(r)
            if args.verbose or i % 10 == 0:
                print('  %d/%d %-28s pokes=%d usr=%s payloads=%d'
                      % (i, len(paths), r['file'], r['n_pokes'],
                         r['usr_seen'], len(r['payloads'])))
        summarise(results)
        if args.json:
            json.dump(results, open(args.json, 'w'), indent=1)
        return 0

    ap.print_help()
    return 0


def summarise(results):
    ml = [r for r in results
          if any(p['region'] == 'candidate-ml' for p in r['payloads'])]
    strict = [r for r in results
              if any(p.get('strict_formed') for p in r['payloads'])]
    print()
    print('listings run                 %d' % len(results))
    print('  reached a USR call         %d' % sum(1 for r in results if r['usr_seen']))
    print('  deposited any bytes        %d' % sum(1 for r in results if r['n_pokes']))
    print('  yielded candidate ML       %d' % len(ml))
    print('  yielded STRICT-formed ML   %d' % len(strict))
    print('  timed out                  %d' % sum(1 for r in results if r['timed_out']))
    buckets = Counter()
    for r in strict:
        for p in r['payloads']:
            if p.get('strict_formed'):
                for b in p.get('buckets', []):
                    buckets[b] += 1
    if buckets:
        print('  buckets (strict payloads): %s' % dict(buckets.most_common()))


if __name__ == '__main__':
    sys.exit(main())
