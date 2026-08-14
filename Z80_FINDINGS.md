# Z80_FINDINGS — Phase A

Numbered findings, basclean-style. Phase A is the static Z80
disassembler/classifier run over the parent corpus's DATA/POKE loader
bytes: measurement, not emulator. It ends here, at a reviewed
checkpoint, with the gate count presented for the user's go/no-go
ruling on Stage 1.

RULING STATUS (2026-08-14): presented, reviewed (independent
assessment reproduced all numbers; FINDING 8 resolved by measurement),
and the user ruled **stop here for now, discuss further**. The user
then agreed the measurement was incomplete while FINDING 7's 96
unresolvable loaders stayed unmeasured, and directed that the gate be
CLOSED — the oracle built and run — before ruling. That work is
FINDINGS 13-18 below, completed 2026-08-14. The gate is now measured
to completion and is back with the user for the ruling. Stage 1 is
still not started; no core code has been written.

Measured 2026-08-13 against `../awk_BASIC_interpreter/programs/`
(runnable 3283 + blocked 1062 = **4345 listings**). Reproduce with
`python3 -m phasea.sweep`; the suite is `python3 -m unittest discover
-s tests` (64 tests). FINDING 8 resolved 2026-08-14 by batch runs
under the parent interpreter; the sweep numbers are unchanged.
PARENT-SIDE UPDATE, later the same day: the FINDING 8 fix SHIPPED in
the parent (c61fdae5) and the parent's VARPTR item shipped too — see
the addendum after the gate table; the gate number is still 5.

---

## THE GATE NUMBER

**5 blocked listings are unlocked by the Z80 core plus the parent's
VARPTR item, and nothing else.** The "up to 2 more" reported on
2026-08-13 was resolved on 2026-08-14: both ?SN errors reproduce, and
their cause is a parent-side `DEF USR 0=` parse gap, not the missing
core (FINDING 8) — the gate number is 5, full stop. A further
**21 already-runnable listings** (23 now that the parent parse gap is
fixed — see the addendum) would stop silently returning a stubbed USR
value and start returning the real one — a correctness gain, not a
runnability gain.

That is the honest answer to "how many rescued listings does Stage 1
(+VARPTR) actually unlock". It is far below what the blocked-category
sizes suggest, and the reasons are FINDINGS 3, 4 and 5.

PARENT-SIDE ADDENDUM (2026-08-14, after the ruling was recorded): the
parent shipped two of the items this measurement leaned on, and the
gate number does not move.
- The `DEF USR 0=` parse fix shipped (parent c61fdae5) and reproduced
  this file's prediction exactly: morsmstr.bas batch exit 0, quest_2.bas
  past its line-36 ?SN to an interactive INPUT — both at stub level,
  joining the sound set. The correctness column is 23 actual, no
  longer conditional.
- The parent's VARPTR item shipped (parent 7e6f0749) — WITH A CAVEAT
  THAT MATTERS HERE: it serves the STRING-packing idiom faithfully
  (live descriptor, write-through bytes), but for numerics and array
  elements it returns the address of a per-element 4-byte
  Microsoft-single materialization. The parent strips `%` suffixes and
  keeps all numerics as doubles, so `VARPTR(US%(0))` now returns a
  real address WITHOUT a contiguous 2-bytes-per-element integer image
  behind it. The VARPTR-array loader idiom therefore still cannot be
  read out of parent memory by a future core — those files route
  through Phase A's extractor/manifest exactly as planned (DESIGN.md
  "LOADER EXTRACTION"). The gate constituency of 5 now needs ONLY the
  core, but nothing about the count changes, and the parent's varptr/
  blocked pile (359) is NOT auto-unblocked — re-classification is a
  future measurement, recorded in the parent STATUS.md.

| | files |
|---|---|
| listings swept | 4345 |
| …using USR | 566 |
| …carrying cleanly extractable machine code (static) | 46 |
| …**plus** recovered by the oracle from the unresolvable 96 (FINDING 14) | **+56** |
| **blocked listings unlocked by core + VARPTR alone** | **6** |
| blocked, ML clean, but *also* blocked by CMD (Disk BASIC) | 14 |
| blocked, ML clean, but needing a Stage 2 ROM trap | 4 (+7, FINDING 18) |
| blocked, ?SN from the parent's `DEF USR 0=` parse gap (FINDING 8; parent fix shipped 2026-08-14, both now run at stub level) | 2 |
| blocked, ?SN unrelated to the loader | 2 |
| runnable listings whose USR result becomes correct | 21 (+2 after the parent fix) |

**THE GATE NUMBER MOVED BY ONE: 5 → 6.** Closing FINDING 7 more than
doubled the measured machine-code population — 46 statically
extractable payloads became 102 — and changed the unlock count by a
single file. That gap is the whole result. The machine code was
always there; what was missing was a listing whose ONLY obstacle is
the absent Z80, and running 96 more loaders produced exactly one more
of those (FINDING 15).

The same run turned up two PARENT-side defects worth more listings
than the core is (FINDINGS 16 and 17), and reversed part of FINDING 9
(FINDING 18).

---

## FINDING 1 — the opcode table validates, and its errors were real

The declarative table (1780 encodings: main/CB/ED/DD/FD/DDCB) was
validated before any classifier output was trusted, per CLAUDE.md
"ANCHORS BEFORE TRUST": 176 hand-authored known-good vectors across all
six pages, total structural coverage, declared-length-equals-consumed
for every entry, and round-trip through the inverse index.

The validation set earned its keep on the first run. **The ED page
never read its operand bytes** — `LD (nn),BC` decoded as 2 bytes
instead of 4. That defect would have desynchronised the linear sweep at
every ED-page absolute load in the corpus, silently, in precisely the
instructions the classifier reads addresses from. A classifier run over
the unvalidated table would have produced numbers, and they would have
been wrong.

One further "failure" was a bad expectation of mine, not a table error:
`FD 25` is `DEC IYH`, an undocumented index-half instruction. Recorded
because the distinction matters — the anchor discipline is only
worth anything if the anchor can also be wrong.

Independent corroboration, beyond the authored set: both anchor
payloads disassemble to a terminating `RET` at *exactly* their last
declared byte. A length error anywhere in those routines would have
landed the terminator somewhere else.

**Cycle costs are carried but UNVALIDATED.** Nothing in the gate
measurement depends on them. They are validated against the
single-step vectors when the core is built.

## FINDING 2 — the endgame anchor is NOT a keyboard scan

DESIGN.md and CLAUDE.md both describe the second ground-truth anchor as
"ENDGAME/BAS SCAN3 (keyboard scan)". **It is not.** The 214-byte block
at `B000H` contains no access to `3800H-38FFH` anywhere. It walks a
caller-supplied table of 16-bit values with IX, finds a minimum via
`SBC HL,DE`, and writes results back through a pointer that USR 0
stashed at `B0D6H`. That is **pure computation**.

The refutation is well-corroborated, not a lone disagreement:

- The parent's own FINDING 29 notes call SCAN3 "the whole **event-clock
  scan**" — not a keyboard scan. The name was mis-glossed.
- Line 1240 invokes it as `KJ=USR 1(VARPTR(IC(1)))`, and `IC()` is the
  event-clock array. The disassembly is exactly a scan of that array.

Four facts FINDING 29 verified *by hand against the printed assembly
listing* all reproduce from the bytes, which makes this an external
check on the opcode table as well:

| FINDING 29, verified against printed Listing 2 | reproduced here |
|---|---|
| DATA exactly fills `POKE -20480..-20267` | 214 bytes at `B000H` |
| `USR1-USR0 = 13 = CALL+6 NOPs+LD+RET` | `CALL`(3)+6×`NOP`+`LD (nn),HL`(3)+`RET`(1) |
| `205,127,10` = CALL 2687 = GETHL | `CALL 0A7FH` |
| a byte impossible as Z80 flags a digit error | implemented as a range lint |

**Consequence for the plan.** DESIGN.md said Phase A would settle
whether endgame is a Stage 1 or Stage 2 acceptance case. It is Stage 1
— and for a stronger reason than anticipated. Not because the keyboard
matrix went live in Stage 0, but because the routine never needed the
keyboard. It needs the CPU, the `0A7FH` trap, and parent-side VARPTR.

Both the measured bucket and the *absence* of keyboard access are
asserted in `tests/test_anchors.py`, so the refuted expectation cannot
creep back in.

## FINDING 3 — most USR listings carry no machine code at all

**288 of the 566 USR-using listings contain no machine language
whatsoever.** They set `DEF USR=&H7800`, `DEF USR 0=(&HBEE6)`, or
`DEF USR 0=AD:CMD"T"` — pointing USR at an address where code is
*expected already to be*, put there by a SYSTEM tape, a disk file, or
TRSDOS. Verified by inspection: zero DATA statements in the sampled
files; their few POKEs are parameter passing (`POKE 30724,T:POKE
30725,S` writes a track and sector before the call).

These are not gate constituency at any stage. They need an external
binary the rescued listing does not contain, which is the standing
standalone/SYSTEM non-goal. **This is the single largest reason the
gate number is small**, and it is invisible to grep — only reading the
loader (or its absence) reveals it.

## FINDING 4 — a clean USR is rarely the *only* thing blocking a listing

Of the 25 blocked-half listings with cleanly extractable machine code,
**14 are also blocked by CMD** (the TRSDOS command escape) and 4 need a
Stage 2 ROM trap. Fixing USR alone leaves all of them blocked.

This is the trap the old proxy fell into. A file sitting in
`blocked/cmd/` with a beautiful 52-byte sound routine is not a listing
"blocked on USR"; it is a Disk BASIC program that also happens to use
USR. Counting the ML payload as gate evidence would have inflated the
number roughly fourfold.

The five that *are* unlocked by core + VARPTR alone:

    raw-bytes-in-code/dmbsfh1.bas     raw-bytes-in-code/xwingcf2.bas
    varptr/MAIL32.bas                 varptr/MAIL48.bas
    varptr/m3t1s2d.bas

Two caveats on the five, recorded 2026-08-14 (assessment review):

- `xwingcf2.bas` has the weakest entry evidence of the five: its USR
  vector poke resolved only the high byte (`hi-only-127`), so
  classification fell back to entry offset 0. The payload is
  strict-formed; the entry-address linkage is not locked.
- "Plus the parent's VARPTR item" is category-level, not
  mechanism-level: **none of the five enters through
  `DEF USR=VARPTR(...)`** — the varptr/ three use literal DEF USR
  addresses and vector pokes, and need parent VARPTR only because
  their listings call VARPTR elsewhere. The entry-idiom VARPTR files
  (the 359-file category's namesake pattern) contributed exactly one
  gate file, `ld8509b.bas` — and it is Stage-2-blocked on `RST 28H`.

## FINDING 5 — not every POKE loop is a machine-code loader

The corpus forced a discrimination the plan did not anticipate.
`POKE 14312,A` in a loop streams bytes to the printer at `37E8H`;
`FOR T=15360 TO 16383` fills video RAM with a screen image;
`READ D,L:POKE P+L,D+128` walks an offset/value graphics table; and a
POKE whose *address* comes out of the READ stream is an address/value
table. None are machine code.

**598 payloads were bucketed away from candidate-ML on these grounds**
(464 damage, 62 screen-data, 55 device-stream, 17 table-data). Had they
been counted as routines, the gate number would have been
unrecognisable. This is the parent's standing lesson — plausible
heuristics die under measurement — arriving on schedule.

## FINDING 6 — raw-byte recovery carries no signal, and it is measurable

`raw-bytes-in-code/` is 135 files, and it is tempting to read that as
135 machine-language programs. It is not. `B1.bas`'s "raw bytes" are
the two-byte fragment `W\x08` — damage, not a routine.

Across the whole sweep, 6808 of 6935 candidate payload records came
from non-printable byte runs, and 159 of them passed a
"decodes without invalid opcodes and contains a RET" filter. That looks
like evidence until it is calibrated:

| filter | false-positive rate on RANDOM bytes |
|---|---|
| loose (no invalid opcodes, has RET, ≥50% coverage) | **27.8%** |
| strict (reaches last byte, stops on RET, ≥90% coverage) | **5.3%** |

Measured over 1500 random byte strings drawn from the same length
distribution as the real runs. The Z80 has very few invalid one-byte
opcodes and `C9` occurs by chance, so the loose filter is nearly
content-free. The 159 hits are consistent with pure chance.

Raw-bytes payloads are therefore **excluded from the gate population**
entirely. Only structurally-anchored idioms — a declared load address
and a declared count the DATA satisfies exactly — are counted. The
sweep recomputes both baselines on every run and carries them in the
report, so no future reader sees a hit rate without its chance rate.

## FINDING 7 — 96 loaders are unresolvable, and are flagged, not guessed

96 USR listings have a real loader whose address or bounds cannot be
resolved statically: `loop-bounds-unresolved` 87, `poke-address-
unresolved` 50, `fixed-address-unresolved` 7 (payload counts; a file
may have several). Causes are computed bases from INPUT, bases built
from other variables, and one loader assembled inside a string
(`"FORX="+S$+"TO"+E$+":READY:POKEX,Y"` — a program writing a program).

These are reported as a category, never guessed at. DESIGN.md's
recorded escalation path applies: the parent interpreter is the
extraction oracle — run the listing under the shipped USR stub to the
first USR call and dump the poked bytes from `mem[]`. **Not built.** If
the gate is ruled met, this is the cheapest way to grow the measured
population, and it would resolve up to 96 more files.

## FINDING 8 — the loader-line ?SN blockers are a parent-side `DEF USR 0=` parse gap (RESOLVED 2026-08-14)

Four `sn-when-run/` listings have clean ML. Their recorded `?SN` lines:

- `morsmstr.bas` line 1 — `FOR I=&HE000 TO&HE033:READ D:POKE I,D:NEXT:DEF USR 0=&HE000`
- `quest_2.bas` line 36 — `ML=&HBFE0:FOR X=&HBFE0 TO&HBFFF:READ N:POKE X,N:NEXT:DEF USR 0=ML`
- `lifesm1.bas` line 60 — `IF ERL=30,1700` (Disk BASIC `IF…,line`; unrelated to ML)
- `sleuth2.bas` line 29 — a PRINT and an assignment; unrelated to ML

For the first two the syntax error is *on the machine-language loader
line*, so as of 2026-08-13 they were plausibly USR-blocked, counted as
0, and reported as "up to +2" pending one batch run each.

**Those runs were made 2026-08-14, and the +2 dissolves.** Both ?SN
errors reproduce under the parent interpreter, exactly on the loader
lines. Minimal repros isolate the cause to one token: `DEF USR 0=`
**with a space before the slot digit** raises `?SN`, while
`DEF USR0=`, `DEFUSR0=`, and `DEF USR=` all parse. The FOR/READ/POKE
and `&H` portions of both lines run clean in isolation. Real Level II
tokenizes past insignificant spaces, so this is a parse gap in the
parent's DEF USR stub — FINDING 12's lexical lesson mirrored: the same
tokenizer that permits `READD` also permits `USR 0`.

Consequence: **neither file is gate constituency.** The blocker was a
one-line fix in the PARENT repo (owed to its queue, per the standing
split — not built here; SHIPPED there 2026-08-14, c61fdae5, verified:
morsmstr exit 0, quest_2 past line 36). Once fixed, both run today under the shipped
stub: both payloads are sound routines (quest_2's 32 bytes disassemble
to a textbook square wave — `OUT (FFH),A` alternating 1 and 0 around
nested `DJNZ` delay loops, `RET` landing on exactly the last byte), so
they join the FINDING 10 sound set and the runnable-half correctness
column (21 → 23), not the unlocked 5. The gate number stays **5**.

## FINDING 9 — the Stage 2 trap priority list is short and mostly not Level II

Corpus-driven, per the basclean methodology — implement a ROM entry
point only when a measured real listing calls it. Across the whole
gate population:

| entry | files | what it is |
|---|---|---|
| `0A7FH` | 27 | USR argument → HL (GETHL) — **already Stage 1** |
| `0028H` | 3 | `RST 28H`, the Disk BASIC DOS vector |
| `01F8H` `0212H` `0235H` `0264H` `0287H` `0296H` `03E3H` | 1 each | all in `varptr/MICROED.bas` |

**The two Stage 1 traps are very nearly the whole requirement.** Not a
single listing in the gate population calls `002BH` (keyboard
scan-once), `0049H` (wait key), `0033H` (char to display), `003BH`
(char to printer) or `0060H` (delay) — the five candidates DESIGN.md
named. Stage 2 as scoped is not justified by this evidence.

`0028H` is a DOS call, which belongs with the CMD blocker, not with
HLE. The `02xx` cluster is one file, and those are not documented
Level II entry points.

## FINDING 10 — what the 46 clean payloads actually are

Buckets by file (a routine may fall in more than one):

| bucket | files | Stage 1 covers |
|---|---|---|
| sound (`OUT (FFH)`) | 25 | 25 |
| video (`3C00H-3FFFH` writes) | 11 | 10 |
| pure compute | 6 | 6 |
| ROM-calling (beyond the two traps) | 4 | 0 |
| keyboard (`3800H-38FFH` reads) | 2 | 2 |
| printer | 2 | 2 |

Sizes: 8 to 193 bytes, median **29**, 2432 bytes in total. These are
short routines. The whole measured corpus of TRS-80 USR machine code is
about 2.4 KB.

**Sound dominates at 25 of 46**, which is the sound-exclusion count
DESIGN.md asked for. Those already "run" today under the stub — silently
and with the wrong return value. Under Stage 1 they run silently and
with the *right* return value. Space Chase is in this set.

**Keyboard is 2 files.** The live keyboard matrix shipped in Stage 0 is
load-bearing for far fewer listings than expected — and, per FINDING 2,
not for endgame.

## FINDING 11 — evidence tiers, and why video needs the weakest one

Classification evidence is tiered and reported separately: **direct**
(an absolute operand — `LD A,(3800H)`, `OUT (FFH),A`), **inferred**
(register-indirect through a propagated constant — `LD DE,3C00H` …
`LD (DE),A`), and **weak** (an immediate that merely falls in a device
range).

The inferred tier is not optional. `varptr/MICROED.bas` writes across
the whole of video RAM via `LD DE,3C00H` and a `SBC HL,DE` loop bounded
at `4000H`; an absolute-operand scan sees none of it. Without constant
propagation the video bucket would be badly undercounted. But it *is* a
propagation heuristic, so it is counted apart from direct evidence
rather than blended into one number.

DESIGN.md's expectation held: symbolic (VARPTR) bases do not block
classification, because the discriminating operands — `OUT (FFH)`,
`3800H`, `3C00H`, `CALL 0A7FH` — are absolute and do not move with the
load address.

## FINDING 12 — two Level II lexical facts cost real bugs

Level II tokenizes keywords, so no space is required before an operand.
`READD` is `READ D`; `DATA205,127` is a DATA statement. A `READ\s+`
regex loses Space Chase's entire loader line, and `DATA\b` refuses
`DATA205,...` because `A` and `2` are both word characters.

Both bugs produced **a plausible-looking zero** — Space Chase extracted
0 bytes, with no error — and both were caught only because an anchor
with a known expected answer was checked before the corpus run. This is
the concrete case for the anchors-before-trust rule.

---

# CLOSING THE GATE — the dynamic oracle (FINDINGS 13-18)

FINDING 7 left 96 USR listings whose loader static extraction could not
resolve, and recorded DESIGN.md's escalation path as "not built". With
the gate ruling deferred on the grounds that a decision taken with 96
files unmeasured is a decision taken on incomplete information, the
oracle was built (`phasea/oracle.py`) and run. It is measurement, not
emulator: no Z80 executes in it.

## FINDING 13 — the oracle never contradicts static extraction

CLAUDE.md "ANCHORS BEFORE TRUST" applied to the oracle itself: before
its output on the unresolvable 96 meant anything, it had to reproduce
the payloads static extraction ALREADY resolves. Over those 45 files:

| | files |
|---|---|
| **exact** — byte-identical to static extraction | 22 |
| **patched** — same routine, runtime-poked operands | 7 |
| **silent** — oracle produced nothing | 16 |
| **CONTRADICTION** | **0** |

Zero contradictions is the property that matters. A fallback that stays
silent where it cannot see is safe; one that invents payloads is not.
Where it spoke, it agreed 29/29.

**The 7 "patched" cases nearly became a false alarm.** The first
validation criterion was byte equality, and it failed 7 files. The
cause was not an oracle defect but a wrong criterion: loaders deposit
DATA literals and then POKE runtime values into them before calling
USR. `quest_2.bas` ships

    LD H,00H / LD L,00H / LD C,00H

and pokes pitch 20 and duration 50 into those operands; `dskindex.bas`
patches five address high-bytes from `A2xx` to `E2xx` (relocation);
`freqanal.bas` writes a single `C9` (RET) over a `3A` at offset 125.
Static extraction sees the placeholders, the oracle sees the routine as
the CPU would. **Byte-inequality there is the oracle being right.** The
criterion now tiers agreement instead of demanding equality, and the
distinction is asserted in `tests/test_oracle.py`.

**The 16 silent cases are a finding, not a gap.** Ten die on a `?SN`
before execution reaches the loader at all, two on `?NF`, one times
out, three run clean down a path that skips the loader. The oracle can
only read what a listing actually deposits, so a listing that cannot
run far enough to load its routine is invisible to it — which is
precisely the population the gate is about.

## FINDING 14 — the oracle resolves most of the 96, and the ML population doubles

Of the 96: 80 deposited bytes, 66 yielded candidate machine code, and
**56 yielded STRICT-formed payloads** (the ≥90%-coverage,
ends-exactly-on-RET filter whose random-data false-positive rate
FINDING 6 measured at 5.3%). 49 of the 56 are covered by Stage 1 alone.

Buckets, by strict payload: sound 40, video 8, ROM-calling 7,
keyboard 1, pure-compute 1. Sound still dominates, exactly as
FINDING 10 found statically.

So the corpus's measured machine-code population goes from 46 files to
102. **This is the finding that most argues the corpus is richer than
the gate number suggests** — and FINDING 15 is why that richness does
not convert.

## FINDING 15 — a hanging listing is not an unlocked listing

13 of the resolved files hang under the stub. The tempting reading is
that a hang means the program is spinning on a USR result the stub gets
wrong, so a working core would release all 13. That reading is a
plausible heuristic, and it dies under measurement like the others.

Each was re-run under a line-number trace, the true spin cycle recovered
by period detection, and the cycle's source read with BASIC comments
stripped:

| | files |
|---|---|
| loop is unconditional — a perfect core changes nothing | 12 |
| **USR result actually gates the loop** | **1** |

The one is `varptr/engindb3.bas`. `liongrp2.bas` is the instructive
near-miss: its cycle is

    110 ' X$=INKEY$:IF X$=""110
    120 X=USR(0): GOTO 110

Line 110 is a REM — the INKEY$ test is commented out — so `120→110→120`
spins forever no matter what USR returns. A first pass that read the
cycle text without stripping comments counted it as USR-gated. Strip
the comment and it is an unconditional loop in a damaged listing.

**Net gate effect of closing FINDING 7: 5 → 6.**

## FINDING 16 — one byte of the memory map is worth more than the core

`IF PEEK(16396)=201` is the classic am-I-under-Disk-BASIC probe: 400CH
holds a RET (201) on a cassette Level II machine. **The parent returns
255** (absent-RAM default), so every listing using the probe takes its
DISK branch — straight into `CMD`, which the parent does not implement
— even though the cassette branch is the one that would run, and is
usually the branch that POKEs the USR vector.

First measured as a counterfactual, by re-running the 96 with the probe
answering 201; **SHIPPED in the parent 2026-08-14 (8c38dca6)**, so the
right-hand column is now simply the truth:

| | before | after (shipped) |
|---|---|---|
| reached a USR call | 25 | **57** |
| deposited any bytes | 80 | 86 |
| yielded strict-formed ML | 56 | 61 |

(57 rather than the 55 the counterfactual predicted: the remaining two
come from FINDING 17's call-site fix, which shipped in the same commit.)

Corpus-wide, **88 listings use the probe** — 66 blocked (29 of them
filed under `cmd/`, 28 under `varptr/`) and 22 runnable. The 29 in
`cmd/` are there *because* the probe sends them down the Disk branch;
they are not Disk BASIC programs, they are cassette programs being told
they are on a disk. This attacks FINDING 4's largest confound directly,
and means **a re-scan of the parent's blocked/ categories is now owed** —
recorded in the parent's STATUS.md, not done here.

The fix was PARENT-OWNED (memory map, CLAUDE.md standing split) and was
made there: `MEM[16396] = 201` seeded at init (p10) rather than
special-cased in `dopeek`, so `POKE 16396` still behaves normally. The
counterfactual patch has been retired from `phasea/oracle.py`; a
cross-repo regression test now asserts the parent still answers 201.

## FINDING 17 — FINDING 8 has a sibling: `USR n(` at the CALL site

FINDING 8 found that `DEF USR 0=` — with a space before the slot digit
— raised `?SN`, and the parent shipped the fix (c61fdae5). That fix
covered the DEFINITION. **The CALL site is still broken.** Minimal
repro against the shipped interpreter:

| source | result |
|---|---|
| `X=USR0(5)` | runs |
| `X=USR(5)` | runs |
| `X=USR 0(5)` | **?SN ERROR** |
| `DEF USR 0=&H7000 : X=USR 0(5)` | **?SN ERROR** (the definition parses, the call does not) |

Level II tokenizes `USR`, so the space is insignificant on real
hardware — FINDING 12's lexical lesson for the third time.
**134 listings corpus-wide use the call form** (118 blocked, 16
runnable).

**SHIPPED in the parent 2026-08-14 (8c38dca6)**, in `e_prim` (p60): a
bare single-digit token after a digitless `USR` spelling is consumed
*if a `(` follows it*, so the correction cannot swallow a digit in any
other construct. Digit-carrying spellings stay strict.

The lesson worth keeping: FINDING 8 and FINDING 17 are the same defect
in the same keyword, and fixing the definition did not fix the call.
**Check both halves of a lexical fix.**

JOINT IMPACT of FINDINGS 16 and 17, measured in the parent old-build vs
new over the 181 blocked listings that use either construct:

| | files |
|---|---|
| now run to completion | 28 |
| past it, stop on a different blocker | 15 |
| past it, reach an interactive INPUT | 4 |
| past it, then hang | 6 |
| **improved** | **53** |
| unchanged | 128 |
| **regressions** | **0** |

Zero regressions was checked explicitly: no listing went from clean to
broken and none gained an error. One case looks like a regression and
is not — `cmd/maestro4.bas` moved from `?SN` at line 150 to `?SN` at
line 10, because line 10 is `... GOSUB 90 ... :CMD"LCDVR"`: it used to
die at 150 *inside that GOSUB*, and now the subroutine returns and it
reaches the CMD its own BLOCKED header already named. BASIC line
numbers are not execution order.

## FINDING 18 — Stage 2 has callers after all

FINDING 9 reported that **not one** listing in the gate population
called `002BH`, `0049H`, `0033H`, `003BH` or `0060H` — DESIGN.md's five
named Stage 2 candidates — and concluded Stage 2 as scoped was not
justified. That conclusion was correct on the population then
measurable, and the oracle changes it:

| entry | files | what it is |
|---|---|---|
| `002BH` | 6 | keyboard scan-once |
| `0033H` | 6 | character to display |
| `1BC0H` | 1 | not a documented Level II entry |

Seven of the 61 strict-formed payloads need a Stage 2 trap; the other
54 are Stage 1 alone. So two of the five named candidates now have
measured callers, and the finding that "Stage 2 as scoped is not
justified" no longer holds in the form FINDING 9 stated it. This is why
findings-correction 2 below is withdrawn rather than applied.

---

## What Phase A built, and what it is worth beyond the gate

- `z80/table.py` — the shared declarative opcode table (DESIGN.md seam
  2), 1780 encodings, with an inverse index. The core's decoder and a
  future assembler are its other consumers; nothing here is throwaway.
- `z80/disasm.py` — a pure consumer of the table.
- `phasea/basic.py`, `phasea/extract.py` — the extractor and its JSON
  intermediate: **a manifest of every ML payload in the collection**,
  regenerable by `python3 -m phasea.sweep`.
- `phasea/classify.py`, `phasea/sweep.py` — the classifier and the
  corpus runner, which refuses to publish counts unless the anchors
  pass.
- 64 tests, including both anchors read in place from the local-only
  sibling and skipped cleanly when it is absent.

Nothing in this repo contains ROM bytes, ROM disassembly, or corpus
material. The sweep output is gitignored.

## Corrections owed to DESIGN.md

1. [APPLIED 2026-08-14] "ENDGAME/BAS SCAN3 (keyboard scan)" →
   **event-clock scan, pure-compute** (FINDING 2). Corrected in
   DESIGN.md "PHASE A ACCEPTANCE ANCHORS" and "Testing strategy", and
   in CLAUDE.md "ANCHORS BEFORE TRUST". The anchor rule as written
   required the classifier to bucket endgame as *keyboard*, which is
   unmeetable because the expectation is false; the rule now states
   the intent — check the anchors before trusting the counts — and
   records that this anchor earned its keep by refuting its own
   premise.
2. [WITHDRAWN 2026-08-14] "Stage 2's named candidates have zero
   measured callers." True of the statically-measurable population,
   false once the oracle closed FINDING 7: `002BH` and `0033H` have
   6 callers each (FINDING 18). DESIGN.md's Stage 2 section is updated
   with the measured list instead.
3. [APPLIED 2026-08-14] `raw-bytes-in-code` (135 files) is not 135 ML
   programs (FINDING 6).
4. [PAID 2026-08-14] Owed to the PARENT repo's queue, not DESIGN.md:
   the DEF USR stub rejected `DEF USR 0=` (space before the slot
   digit) with `?SN` (FINDING 8). The one-line lexical fix shipped in
   the parent (c61fdae5) and unblocked `morsmstr.bas` and
   `quest_2.bas` to stub level, as predicted.

## Owed to the PARENT repo's queue (new, 2026-08-14 — BOTH PAID)

Both found by the oracle, both parent-owned under the standing split,
both built THERE and shipped the same day in parent commit `8c38dca6`.
Together they improved **53 blocked listings** with **zero
regressions** — more than the core itself is measured to unlock, which
is the single most decision-relevant fact in this document.

5. [PAID] `USR n(` at the call site raised `?SN` — FINDING 8's sibling,
   the same one-line lexical shape, **134 listings** (FINDING 17).
   Fixed in `e_prim` (p60).
6. [PAID] `PEEK(16396)` answered 255, not 201 — the cassette/disk
   probe, **88 listings**, and the reason 29 listings sat in
   `blocked/cmd/` that are not Disk BASIC programs at all (FINDING 16).
   Fixed by seeding `MEM[16396]` at init (p10).

Parent regression bar held for both: t1-t28 exit 0, every transcript
byte-identical to the pre-change build except t7 (documented RND
variance, confirmed to vary on the unchanged build too) and t23, which
grew coverage of the spaced call form and the probe on purpose.

## Now owed BACK to the parent (not done)

7. A re-scan of `blocked/`. FINDING 16 means some files are mis-filed:
   several `blocked/cmd/` listings were never Disk BASIC programs, they
   were cassette programs being told they were on a disk. Until that
   re-scan runs, the blocked-category sizes overstate the CMD blocker
   and understate everything behind it — including, possibly, the gate
   population itself.
