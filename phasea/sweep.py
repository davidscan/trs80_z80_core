"""Phase A corpus sweep -- produces the gate numbers.

Input set:
    programs/runnable/   +   programs/blocked/   (all categories)
  skipped: Model1/ and the zip archive (same content re-organised --
  double-counts), dialect/ (non-Level-II), the large collection's
  Detokenized/ (empty). The anchors in OCRsamples/ are read IN PLACE, never copied.

THE SWEEP REFUSES TO PUBLISH COUNTS UNLESS BOTH ANCHOR SUITES PASS.
The counting rule: "A count produced without both checks passing is not a
measurement." That is enforced here rather than left to discipline.

Usage:
    python3 -m phasea.sweep [--json out/manifest.json]
"""

import argparse
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phasea.extract import extract_file                        # noqa: E402
from phasea.classify import classify, ROM_NAMES                # noqa: E402

# The corpus archive. The interpreter is NOT here any more (it moved to
# ../trs80basic 2026-08-28); the sweep reads listings only.
# The corpus archive is a local-only sibling repository of period listings,
# never published.  It is reached through a `corpus` link at this repo's root
# (gitignored: `ln -s /path/to/the/archive corpus`), or TRS80_CORPUS names it.
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.environ.get('TRS80_CORPUS') or os.path.join(HERE, 'corpus')
PROGRAMS = os.path.join(CORPUS, 'programs')


ANCHOR_SUITES = ('tests.test_table', 'tests.test_anchors', 'tests.test_extract')


def gate_check(suites=ANCHOR_SUITES, cwd=HERE):
    """Run the anchor suites. Returns (ok, summary).

    A SKIPPED test is not a passed one. The anchor tests skip when the
    corpus sibling is absent, and unittest still exits 0 with
    `OK (skipped=14)`: the gate would say PASS with neither anchor read.
    So the gate wants exit 0, at least one test run, and no skip.
    """
    r = subprocess.run([sys.executable, '-m', 'unittest'] + list(suites),
                       cwd=cwd, capture_output=True, text=True)
    lines = (r.stderr or '').strip().splitlines()
    summary = lines[-1] if lines else ''
    ran = [ln for ln in lines if ln.startswith('Ran ')]
    ok = (r.returncode == 0 and 'skipped' not in summary
          and bool(ran) and not ran[-1].startswith('Ran 0 '))
    return ok, summary


def input_files():
    """(path, half, category) for every listing in the input set."""
    out = []
    rp = os.path.join(PROGRAMS, 'runnable')
    if os.path.isdir(rp):
        for n in sorted(os.listdir(rp)):
            if n.lower().endswith('.bas'):
                out.append((os.path.join(rp, n), 'runnable', 'runnable'))
    bp = os.path.join(PROGRAMS, 'blocked')
    if os.path.isdir(bp):
        for cat in sorted(os.listdir(bp)):
            cd = os.path.join(bp, cat)
            if not os.path.isdir(cd):
                continue
            for n in sorted(os.listdir(cd)):
                if n.lower().endswith('.bas'):
                    out.append((os.path.join(cd, n), 'blocked', cat))
    return out


def entry_offsets(rep, payload):
    """Where inside this payload might execution start?"""
    offs = []
    for e in rep.usr_entries:
        if e.addr is not None and payload.base is not None:
            if payload.base <= e.addr < payload.base + payload.length:
                offs.append(e.addr - payload.base)
        elif e.kind == 'varptr' and payload.idiom == 'varptr-array':
            offs.append(0)          # DEF USR=VARPTR(A(0)) -> array start
    return offs or [0]


def analyse(path):
    rep = extract_file(path)
    results = []
    for p in rep.payloads:
        if p.kind != 'candidate-ml' or not p.bytes:
            results.append((p, None))
            continue
        c = classify(bytes(p.bytes), p.base, entry_offsets(rep, p))
        results.append((p, c))
    return rep, results


# Idioms with a STRUCTURAL anchor -- a declared load address, a declared
# count that the DATA satisfies exactly, and (usually) a USR entry that
# lands inside the block. Only these enter the gate population.
# `raw-bytes` has none of that and is reported separately: see
# random_baseline() for why it carries no signal.
STRUCTURAL_IDIOMS = {'for-read-poke', 'varptr-array', 'poke-seq', 'string-packed'}


def well_formed(c):
    """Loose filter: decodes without invalid opcodes and contains a RET.

    Kept only for comparison. Its random-data false-positive rate is
    ~28%, so on its own it means almost nothing.
    """
    q = c.quality
    return (q['invalid_in_reachable'] == 0 and q['has_ret']
            and q['coverage'] >= 0.5)


def strict_formed(c):
    """Strict filter: the sweep reaches the LAST byte and stops on RET.

    A length error anywhere would desynchronise the sweep and land the
    terminator elsewhere, so this is a real check on both the payload
    and the opcode table. Random-data false-positive rate ~4%.
    Both anchors pass it.
    """
    q = c.quality
    return (q['invalid_in_reachable'] == 0 and q['ends_exactly_on_ret']
            and q['coverage'] >= 0.9)


def random_baseline(lengths, n=1500, seed=20260813):
    """Measure both filters against random bytes of the same lengths.

    Publishing a hit-rate without its chance rate would be a plausible
    heuristic wearing a measurement's clothes.
    """
    import random
    if not lengths:
        return {}
    rng = random.Random(seed)
    loose = strict = 0
    for _ in range(n):
        ln = rng.choice(lengths)
        data = bytes(rng.randrange(256) for _ in range(ln))
        c = classify(data, None, [0])
        if well_formed(c):
            loose += 1
        if strict_formed(c):
            strict += 1
    return {'samples': n,
            'loose_filter_false_positive_rate': round(loose / n, 3),
            'strict_filter_false_positive_rate': round(strict / n, 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default='out/manifest.json')
    ap.add_argument('--skip-gate', action='store_true',
                    help=argparse.SUPPRESS)
    args = ap.parse_args()
    if not os.path.isdir(PROGRAMS):
        sys.exit('no corpus archive at %s: link the listing archive as `corpus` at this '
                 "repo's root, or set TRS80_CORPUS (README, Commands)" % os.path.dirname(PROGRAMS))

    if not args.skip_gate:
        ok, summary = gate_check()
        print('anchor gate: %s  (%s)' % ('PASS' if ok else 'FAIL', summary))
        if not ok:
            print('\nREFUSING TO PUBLISH COUNTS: a count produced '
                  'without both anchor checks passing is not a measurement '
                  '(a skipped anchor test has not passed).')
            return 2

    files = input_files()
    print('input set: %d listings' % len(files))

    manifest = []
    stats = Counter()
    bucket_files = defaultdict(set)
    rom_files = defaultdict(set)
    unextractable = Counter()
    notml = Counter()
    stage1_files = set()
    stage2_files = set()
    varptr_needed = set()
    ml_files = set()
    per_half = defaultdict(Counter)
    cat_ml = defaultdict(set)
    raw_lengths = []
    half_ml = defaultdict(set)
    bucket_stage1 = defaultdict(set)
    usr_files = set()
    disposition = defaultdict(set)
    disposition_all = defaultdict(set)

    for path, half, cat in files:
        name = os.path.basename(path)
        key = '%s/%s' % (cat, name)
        rep, results = analyse(path)
        stats['files'] += 1

        has_usr = rep.usr_calls > 0 or bool(rep.usr_entries)
        if has_usr:
            stats['files_with_usr'] += 1
            per_half[half]['files_with_usr'] += 1
            usr_files.add(key)

        # ---- per-file disposition: what stands between this listing
        # and a running USR call? This is the gate's real denominator.
        idioms = set(p.idiom for p in rep.payloads
                     if p.kind == 'candidate-ml')
        kinds = set(p.kind for p in rep.payloads)
        strict_here = any(c is not None and p.idiom in STRUCTURAL_IDIOMS
                          and strict_formed(c) for p, c in results)
        # An `unextractable` payload also carries idiom 'for-read-poke',
        # so this must key on KIND -- otherwise a file whose only loader
        # is unresolvable is miscounted as having extracted machine code.
        struct_here = bool(idioms & STRUCTURAL_IDIOMS)
        if strict_here:
            disp = 'ml-extracted'
        elif struct_here:
            disp = 'ml-extracted-but-not-clean'
        elif 'unextractable' in kinds:
            disp = 'loader-unresolvable'
        elif 'raw-bytes' in idioms:
            disp = 'raw-bytes-only'
        elif kinds & {'device-stream', 'screen-data', 'table-data'}:
            disp = 'non-ml-poke-loops-only'
        else:
            disp = 'no-ml-in-listing'
        if has_usr:
            disposition[disp].add(key)
        disposition_all[disp].add(key)

        for p, c in results:
            rec = {'file': key, 'half': half, 'category': cat,
                   'idiom': p.idiom, 'kind': p.kind,
                   'base': p.base, 'base_symbol': p.base_symbol,
                   'length': p.length, 'confidence': p.confidence,
                   'flags': p.flags, 'provenance': p.provenance,
                   'usr_calls': rep.usr_calls,
                   'usr_entries': [(e.kind, e.slot, e.addr, e.symbol)
                                   for e in rep.usr_entries]}
            if p.kind == 'unextractable':
                for f in p.flags:
                    unextractable[f] += 1
                stats['payloads_unextractable'] += 1
            elif p.kind in ('device-stream', 'screen-data', 'table-data',
                            'damage'):
                notml[p.kind] += 1
                stats['payloads_not_ml'] += 1
            if c is None:
                manifest.append(rec)
                continue

            stats['payloads_ml'] += 1
            wf = well_formed(c)
            sf = strict_formed(c)
            structural = p.idiom in STRUCTURAL_IDIOMS
            rec.update({'bucket': c.bucket, 'buckets': c.buckets_all,
                        'evidence': c.evidence, 'stage1_ok': c.stage1_ok,
                        'rom_calls': [a for a, _n in c.rom_calls],
                        'stage2_traps': c.stage2_traps,
                        'quality': c.quality, 'well_formed': wf,
                        'strict_formed': sf, 'structural': structural,
                        'ports_out': c.ports_out, 'ports_in': c.ports_in})
            manifest.append(rec)

            if not structural:
                stats['payloads_rawbytes'] += 1
                if wf:
                    stats['payloads_rawbytes_loose_pass'] += 1
                if sf:
                    stats['payloads_rawbytes_strict_pass'] += 1
                raw_lengths.append(p.length)
                continue

            stats['payloads_structural'] += 1
            if not sf:
                stats['payloads_structural_illformed'] += 1
                if wf:
                    stats['payloads_structural_loose_only'] += 1
                continue
            stats['payloads_structural_strict'] += 1
            ml_files.add(key)
            cat_ml[cat].add(key)
            half_ml[half].add(key)
            for b in c.buckets_all:
                bucket_files[b].add(key)
                if c.stage1_ok:
                    bucket_stage1[b].add(key)
            for a, _n in c.rom_calls:
                rom_files[a].add(key)
            if c.stage1_ok:
                stage1_files.add(key)
            else:
                stage2_files.add(key)
            if any(e.kind == 'varptr' for e in rep.usr_entries) or \
                    p.idiom == 'varptr-array':
                varptr_needed.add(key)

    print('measuring random-data baseline for the quality filters...')
    baseline = random_baseline(raw_lengths)

    report = {
        'input_files': len(files),
        'stats': dict(stats),
        'quality_filter_baseline': baseline,
        'gate_population_files': len(ml_files),
        'gate_population_by_half': {k: len(v) for k, v in
                                    sorted(half_ml.items())},
        'buckets_by_file': {k: len(v) for k, v in
                            sorted(bucket_files.items())},
        'buckets_stage1_ok': {k: len(v) for k, v in
                              sorted(bucket_stage1.items())},
        'stage1_unlocks': len(stage1_files),
        'stage2_needed': len(stage2_files),
        'varptr_also_needed': len(varptr_needed & ml_files),
        'rom_entry_points': sorted(
            ((('%04XH' % a), ROM_NAMES.get(a), len(v))
             for a, v in rom_files.items()),
            key=lambda t: -t[2]),
        'files_with_usr': len(usr_files),
        'usr_file_disposition': {k: len(v) for k, v in
                                 sorted(disposition.items(),
                                        key=lambda t: -len(t[1]))},
        'all_file_disposition': {k: len(v) for k, v in
                                 sorted(disposition_all.items(),
                                        key=lambda t: -len(t[1]))},
        'unextractable_reasons': dict(unextractable.most_common()),
        'not_machine_code': dict(notml.most_common()),
        'ml_by_category': {k: len(v) for k, v in sorted(cat_ml.items())},
    }

    os.makedirs(os.path.dirname(args.json) or '.', exist_ok=True)
    with open(args.json, 'w') as fh:
        json.dump({'report': report, 'payloads': manifest}, fh, indent=1)

    print(json.dumps(report, indent=1))
    print('\nmanifest -> %s (%d payload records)'
          % (args.json, len(manifest)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
