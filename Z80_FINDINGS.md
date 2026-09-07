# Z80_FINDINGS — Phase A

Numbered findings, basclean-style. Phase A is the static Z80
disassembler/classifier run over the corpus archive's DATA/POKE loader
bytes: measurement, not emulator. It ends here, at a reviewed
checkpoint, with the gate count presented for the user's go/no-go
ruling on Stage 1.

TERMINOLOGY (converted 2026-09-07): this document used to say "the
parent" for the pre-split ../awk_BASIC_interpreter, which then held
both the interpreter and the corpus. Since 2026-08-28 the interpreter
is ../trs80basic and awk_BASIC_interpreter is the corpus archive only —
this project is a peer of both, a child of neither (CLAUDE.md
"COMPANION REPOS"). Every occurrence now names what it meant: "the
interpreter" / trs80basic for interpreter-side work, "the archive" /
"the corpus archive" for corpus-side work. Commit hashes cited for
interpreter-side ships (c61fdae5, 7e6f0749, 8c38dca6) are PRE-SPLIT and
resolve in awk_BASIC_interpreter's history; that code lives in
trs80basic now. No measurement, number or ruling changed — only names.

RULING STATUS (2026-08-14): presented, reviewed (independent
assessment reproduced all numbers; FINDING 8 resolved by measurement),
and the user ruled **stop here for now, discuss further**. The user
then agreed the measurement was incomplete while FINDING 7's 96
unresolvable loaders stayed unmeasured, and directed that the gate be
CLOSED — the oracle built and run — before ruling. That work is
FINDINGS 13-18 below, completed 2026-08-14. The gate was measured to
completion and presented, and the user RULED the same evening (in the
companion session; recorded in awk_BASIC_interpreter's PROJECT_MAP.md):
the rescue count does not justify the core and no longer has to — the
project is wanted for its own sake, four goals in priority order
(CLAUDE.md "WHERE THINGS STAND"). The gate is closed as a decision
input and survives here as the measurement record. The same evening's
blocked/ re-scan changed the bookkeeping of the six gate files without
unlocking any (FINDING 20, recorded 2026-09-04). Stage 1 is still not
started; no core code has been written.

Measured 2026-08-13 against `../awk_BASIC_interpreter/programs/`
(runnable 3283 + blocked 1062 = **4345 listings**). Reproduce with
`python3 -m phasea.sweep`; the suite is `python3 -m unittest discover
-s tests` (104 tests). The archive re-filed blocked/ on 2026-08-14, so a
re-run today reads 4339 listings with the same 46-file gate population
split differently between the halves — the deltas are tabulated in
FINDING 20; the numbers below are left as measured. FINDING 8 resolved 2026-08-14 by batch runs
under the companion interpreter; the sweep numbers are unchanged.
INTERPRETER-SIDE UPDATE, later the same day: the FINDING 8 fix SHIPPED
(c61fdae5) and the VARPTR item shipped too — see
the addendum after the gate table; neither moved the number. The
FINDING 16/17 fixes shipped that evening (8c38dca6) and did not
move it either — they change how many listings RUN, not how many are
blocked on the core alone. Post-fix figures are re-measured throughout
FINDINGS 14-18.

---

## THE GATE NUMBER

### Current answer: **6**

**6 blocked listings are unlocked by the Z80 core and nothing else** —
the measurement is complete as of 2026-08-14, with FINDING 7's 96
unresolvable loaders closed by the oracle. A further **23
already-runnable listings** would stop silently returning a stubbed USR
value and start returning the real one — a correctness gain, not a
runnability gain.

That is the honest answer to "how many rescued listings does Stage 1
actually unlock". It is far below what the blocked-category sizes
suggest, and the reasons are FINDINGS 3, 4, 5 and 15.

**The gate never set a numeric threshold** — it specifies a measurement
and a decision procedure (present to the user, user rules), not a
number that means "build". No arithmetic settles the ruling.

### How it got here (history, kept deliberately)

Phase A returned **5**, on the statically extractable population only.
The "up to 2 more" reported on 2026-08-13 was resolved on 2026-08-14:
both ?SN errors reproduce, and their cause is an interpreter-side
`DEF USR 0=` parse gap, not the missing core (FINDING 8). Closing
FINDING 7 with the dynamic oracle then moved 5 → 6 (FINDINGS 13-15).

INTERPRETER-SIDE ADDENDUM (2026-08-14, after the ruling was recorded):
the interpreter shipped two of the items this measurement leaned on,
and the
gate number does not move.
- The `DEF USR 0=` parse fix shipped (c61fdae5) and reproduced
  this file's prediction exactly: morsmstr.bas batch exit 0, quest_2.bas
  past its line-36 ?SN to an interactive INPUT — both at stub level,
  joining the sound set. The correctness column is 23 actual, no
  longer conditional.
- The interpreter's VARPTR item shipped (7e6f0749) — WITH A CAVEAT
  THAT MATTERS HERE: it serves the STRING-packing idiom faithfully
  (live descriptor, write-through bytes), but for numerics and array
  elements it returns the address of a per-element 4-byte
  Microsoft-single materialization. The interpreter strips `%` suffixes and
  keeps all numerics as doubles, so `VARPTR(US%(0))` now returns a
  real address WITHOUT a contiguous 2-bytes-per-element integer image
  behind it. The VARPTR-array loader idiom therefore still cannot be
  read out of interpreter memory by a future core — those files route
  through Phase A's extractor/manifest exactly as planned (DESIGN.md
  "LOADER EXTRACTION"). The gate constituency of 5 now needs ONLY the
  core, but nothing about the count changes, and the archive's varptr/
  blocked pile (359) is NOT auto-unblocked — re-classification is a
  future measurement, recorded in the archive's STATUS.md. (Done that
  evening: varptr/ retired, four gate files re-filed — FINDING 20.)

| | files |
|---|---|
| listings swept | 4345 |
| …using USR | 566 |
| …carrying cleanly extractable machine code (static) | 46 |
| …**plus** recovered by the oracle from the unresolvable 96 (FINDING 14) | **+61** |
| **blocked listings unlocked by core + VARPTR alone** | **6** (2 by the literal wording after the 2026-08-14 re-scan moved four of them to runnable/; none of the six runs — FINDING 20) |
| blocked, ML clean, but *also* blocked by CMD (Disk BASIC) | 14 |
| blocked, ML clean, but needing a Stage 2 ROM trap | 4 (+7, FINDING 18) |
| blocked, ?SN from the interpreter's `DEF USR 0=` parse gap (FINDING 8; fix shipped 2026-08-14, both now run at stub level) | 2 |
| blocked, ?SN unrelated to the loader | 2 |
| runnable listings whose USR result becomes correct | 21 (+2 after the interpreter fix) |

**THE GATE NUMBER MOVED BY ONE: 5 → 6.** Closing FINDING 7 more than
doubled the measured machine-code population — 46 statically
extractable payloads became 107 — and changed the unlock count by a
single file. That gap is the whole result. The machine code was
always there; what was missing was a listing whose ONLY obstacle is
the absent Z80, and running 96 more loaders produced exactly one more
of those (FINDING 15).

The same run turned up two INTERPRETER-side defects worth more listings
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

- awk_BASIC_interpreter's own FINDING 29 notes call SCAN3 "the whole
  **event-clock
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
keyboard. It needs the CPU, the `0A7FH` trap, and interpreter-side
VARPTR.

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

The five that *are* unlocked by core + VARPTR alone (statically
measured; the sixth arrived later from the oracle):

    raw-bytes-in-code/dmbsfh1.bas     raw-bytes-in-code/xwingcf2.bas
    varptr/MAIL32.bas                 varptr/MAIL48.bas
    varptr/m3t1s2d.bas

    varptr/engindb3.bas   <- the 6th, added by FINDING 15: the only one
                             of 14 hanging listings whose loop is
                             actually gated on the USR result

(Paths as of 2026-08-13. The archive's re-scan that evening retired
varptr/ and moved MAIL32, MAIL48, m3t1s2d and engindb3 to runnable/;
the two raw-bytes-in-code files stay blocked. FINDING 20.)

Two caveats on the first five, recorded 2026-08-14 (assessment review):

- `xwingcf2.bas` has the weakest entry evidence of the five: its USR
  vector poke resolved only the high byte (`hi-only-127`), so
  classification fell back to entry offset 0. The payload is
  strict-formed; the entry-address linkage is not locked.
- "Plus the interpreter's VARPTR item" is category-level, not
  mechanism-level: **none of the five enters through
  `DEF USR=VARPTR(...)`** — the varptr/ three use literal DEF USR
  addresses and vector pokes, and need the interpreter's VARPTR only
  because
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
unrecognisable. This is the corpus project's standing lesson — plausible
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
recorded escalation path applies: the companion interpreter is the
extraction oracle — run the listing under the shipped USR stub to the
first USR call and dump the poked bytes from `mem[]`. **Not built** as
of 2026-08-13 — BUILT 2026-08-14, FINDINGS 13-18. It was the cheapest
way to grow the measured population, and it resolved 61 of the 96.

## FINDING 8 — the loader-line ?SN blockers are an interpreter-side `DEF USR 0=` parse gap (RESOLVED 2026-08-14)

Four `sn-when-run/` listings have clean ML. Their recorded `?SN` lines:

- `morsmstr.bas` line 1 — `FOR I=&HE000 TO&HE033:READ D:POKE I,D:NEXT:DEF USR 0=&HE000`
- `quest_2.bas` line 36 — `ML=&HBFE0:FOR X=&HBFE0 TO&HBFFF:READ N:POKE X,N:NEXT:DEF USR 0=ML`
- `lifesm1.bas` line 60 — `IF ERL=30,1700` (Disk BASIC `IF…,line`; unrelated to ML)
- `sleuth2.bas` line 29 — a PRINT and an assignment; unrelated to ML

For the first two the syntax error is *on the machine-language loader
line*, so as of 2026-08-13 they were plausibly USR-blocked, counted as
0, and reported as "up to +2" pending one batch run each.

**Those runs were made 2026-08-14, and the +2 dissolves.** Both ?SN
errors reproduce under the companion interpreter, exactly on the loader
lines. Minimal repros isolate the cause to one token: `DEF USR 0=`
**with a space before the slot digit** raises `?SN`, while
`DEF USR0=`, `DEFUSR0=`, and `DEF USR=` all parse. The FOR/READ/POKE
and `&H` portions of both lines run clean in isolation. Real Level II
tokenizes past insignificant spaces, so this is a parse gap in the
interpreter's DEF USR stub — FINDING 12's lexical lesson mirrored: the same
tokenizer that permits `READD` also permits `USR 0`.

Consequence: **neither file is gate constituency.** The blocker was a
one-line fix in the INTERPRETER repo (owed to its queue, per the standing
split — not built here; SHIPPED there 2026-08-14, c61fdae5, verified:
morsmstr exit 0, quest_2 past line 36). Once fixed, both run today under the shipped
stub: both payloads are sound routines (quest_2's 32 bytes disassemble
to a textbook square wave — `OUT (FFH),A` alternating 1 and 0 around
nested `DJNZ` delay loops, `RET` landing on exactly the last byte), so
they join the FINDING 10 sound set and the runnable-half correctness
column (21 → 23), not the unlocked set. The gate number stayed **5** at
this point; FINDING 15 later moved it to 6.

## FINDING 9 — the Stage 2 trap priority list is short and mostly not Level II

Corpus-driven, per the basclean methodology — implement a ROM entry
point only when a measured real listing calls it. Across the whole
gate population:

| entry | files | what it is |
|---|---|---|
| `0A7FH` | 27 | CINT: ACCUM → HL, i.e. the USR argument fetch — **already Stage 1** |
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

Of the 96, measured against the interpreter as it then stood: 80 deposited
bytes, 66 yielded candidate machine code, and **56 yielded
STRICT-formed payloads** (the ≥90%-coverage, ends-exactly-on-RET filter
whose random-data false-positive rate FINDING 6 measured at 5.3%).

RE-MEASURED against the interpreter after FINDINGS 16 and 17 shipped there,
which is the number to quote now: 86 deposited, 73 candidate, **61
strict-formed**, 57 reached a USR call (from 25). 54 of the 61 are
covered by Stage 1 alone; the other 7 need a Stage 2 trap (FINDING 18).

Buckets, by strict payload: sound 44, video 8, ROM-calling 7,
pure-compute 3, keyboard 1. Sound still dominates, exactly as
FINDING 10 found statically.

So the corpus's measured machine-code population goes from 46 files to
107. **This is the finding that most argues the corpus is richer than
the gate number suggests** — and FINDING 15 is why that richness does
not convert.

## FINDING 15 — a hanging listing is not an unlocked listing

14 of the resolved files hang under the stub. The tempting reading is
that a hang means the program is spinning on a USR result the stub gets
wrong, so a working core would release all 14. That reading is a
plausible heuristic, and it dies under measurement like the others.

Each was re-run under a line-number trace, the true spin cycle recovered
by period detection, and the cycle's source read with BASIC comments
stripped. Reproduce with `python3 -m phasea.oracle --hangs --files
<list>`; the analysis lives in the module (`analyse_hang`) rather than
in a scratch script precisely because it is the number holding the gate
down:

| | files |
|---|---|
| loop is unconditional — a perfect core changes nothing | 13 |
| **USR result actually gates the loop** | **1** |

(13 hangs when first measured, 14 after the interpreter's FINDING 16/17
fixes let more listings reach their loader. The USR-gated count stayed
at exactly one through both runs.)

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
holds a RET (201) on a cassette Level II machine. **The interpreter returns
255** (absent-RAM default), so every listing using the probe takes its
DISK branch — straight into `CMD`, which the interpreter does not implement
— even though the cassette branch is the one that would run, and is
usually the branch that POKEs the USR vector.

First measured as a counterfactual, by re-running the 96 with the probe
answering 201; **SHIPPED interpreter-side 2026-08-14 (8c38dca6)**, so the
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
and means **a re-scan of the archive's blocked/ categories is now owed** —
recorded in the archive's STATUS.md, not done here. (PAID the same
evening; the cmd/ half was measured by reachability rather than
re-filed, and contributed zero to the gate — FINDING 20.)

The fix was INTERPRETER-OWNED (memory map, CLAUDE.md standing split) and was
made there: `MEM[16396] = 201` seeded at init (p10) rather than
special-cased in `dopeek`, so `POKE 16396` still behaves normally. The
counterfactual patch has been retired from `phasea/oracle.py`; a
cross-repo regression test now asserts the interpreter still answers 201.

## FINDING 17 — FINDING 8 has a sibling: `USR n(` at the CALL site

FINDING 8 found that `DEF USR 0=` — with a space before the slot digit
— raised `?SN`, and the interpreter shipped the fix (c61fdae5). That fix
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

**SHIPPED interpreter-side 2026-08-14 (8c38dca6)**, in `e_prim` (p60): a
bare single-digit token after a digitless `USR` spelling is consumed
*if a `(` follows it*, so the correction cannot swallow a digit in any
other construct. Digit-carrying spellings stay strict.

The lesson worth keeping: FINDING 8 and FINDING 17 are the same defect
in the same keyword, and fixing the definition did not fix the call.
**Check both halves of a lexical fix.**

JOINT IMPACT of FINDINGS 16 and 17, measured in the interpreter old-build vs
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
| `1BC0H` | 1 | tokenize / COMPRESS a BASIC line |

CORRECTION 2026-09-06: this table read "not a documented Level II
entry" for `1BC0H`. That was an artefact of the classifier's ROM_NAMES
table, which simply did not carry the address — not of the ROM. The
scanned reference library names it in three independent books:
"COMPRESS BASIC LINE" (ROM Routines Documented p62), "TOKENIZE INPUT
ROUTINE" (Level II ROMs, Tab Books, p375), and Farvour p11 on the
tokenization pass. `phasea/classify.py` now carries the name, and the
Stage 2 entry in DESIGN.md is corrected. The caller count is unchanged
at 1, so nothing about the Stage 2 priority moves; what moves is the
reason — one caller, not an unknowable entry point.

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
- 104 tests, including both anchors read in place from the local-only
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
4. [PAID 2026-08-14] Owed to the INTERPRETER repo's queue, not DESIGN.md:
   the DEF USR stub rejected `DEF USR 0=` (space before the slot
   digit) with `?SN` (FINDING 8). The one-line lexical fix shipped in
   the interpreter (c61fdae5) and unblocked `morsmstr.bas` and
   `quest_2.bas` to stub level, as predicted.

## Owed to the INTERPRETER repo's queue (new, 2026-08-14 — BOTH PAID)

Both found by the oracle, both interpreter-owned under the standing
split, both built THERE and shipped the same day in commit `8c38dca6`.
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

The interpreter's regression bar held for both: t1-t28 exit 0, every transcript
byte-identical to the pre-change build except t7 (documented RND
variance, confirmed to vary on the unchanged build too) and t23, which
grew coverage of the spaced call form and the probe on purpose.

## Now owed BACK to the archive — PAID 2026-08-14 (recorded 2026-09-04)

7. [PAID] A re-scan of `blocked/`. FINDING 16 means some files are
   mis-filed: several `blocked/cmd/` listings were never Disk BASIC
   programs, they were cassette programs being told they were on a
   disk. Done the same evening (awk_BASIC_interpreter 9ee96ca3 +
   89d9269b) and verified from this side; the cmd/ half was measured
   rather than re-filed, and the gate population did not grow.
   FINDING 20.

## FINDING 19 — Dancing Demon profiled: the coprocess needs a screen, a keyboard, and a clock, but not a ROM (2026-09-02)

The famous acceptance question ("does it run Dancing Demon?") now has
numbers behind it. The 1986 Powersoft image in the corpus archive
(`programs/LargeCollection/Dancing Demon (1986)(...)[BAS]/dncdm86a.bas`)
is `1 GOTO 259` plus **10,931 bytes of Z80 stored as 106 fake BASIC
lines** (line numbers 2..258), loading at **42F6H** — the payload sits
inside the tokenized program image itself, not in a DATA/POKE loader,
so Phase A's extractor idioms never see it. Extraction recipe: walk the
image's line records (2-byte next-ptr, 2-byte lineno, body to the 00
terminator), concatenate the bodies of lines 2..258 *including* each
00, base = record offset mapped from 42E9H.

A linear sweep with `z80/disasm.py` (8,068 insns, 0 undecodable —
first outside consumer of the module, and it held) says the payload
touches:

- **video RAM, heavily**: 34 immediates in 3C00-3FFFH (`LD DE,3C01H`,
  `3F80H`, `3C40H`...) — the animation writes the screen *during* the
  USR call, not before RET;
- **the keyboard matrix, once**: `LD HL,38FFH` — the all-rows poll;
- **sound, exactly twice**: `OUT (C),H` / `OUT (C),L` at 43FC/4401H —
  one compact cassette-latch routine, trivially no-op'd;
- **system RAM**: patches 4018H, reads (40A4H) — expects the 4000H
  communication region to look sane (the interpreter already seeds part of
  it, FINDING 16's MEM[16396]);
- **no ROM calls at all** under the sweep — self-contained.

Linear-sweep caveat applies: LD 2,602 / ADD 1,978 mnemonic counts smell
of interleaved data decoding as code, so these are signals, not a
control-flow proof. The proof is running it.

**What this buys the Stage-1 discussion:** "silent Dancing Demon
dances" is a near-ideal north-star acceptance test for the coprocess.
It needs exactly the three capabilities the protocol has to decide on
anyway — (a) sustained execution with video writes streamed or synced
to the interpreter's live display buffer, not just memory-at-RET; (b) key
state fed into coprocess reads of 3800-38FFH (the interpreter's
keyboard
layer already holds it); (c) cycle-paced execution so the demon dances
at 1.77 MHz tempo — and it needs nothing we dread (no ROM emulation,
sound isolable to two instructions). It is visually self-verifying and
famous enough to be worth the trouble. Call-and-return USR (memory in,
run, memory out) is demonstrably NOT enough for this class of program.

## FINDING 20 — the blocked/ re-scan moved four gate files without unlocking any (measured 2026-08-14, recorded 2026-09-04)

The re-scan owed to the corpus archive after FINDINGS 16/17 was PAID
the same evening (awk_BASIC_interpreter `9ee96ca3` and `89d9269b`) and
verified from this side at once. The verification was offered as a
finding and never written down, so the gate numbers above were being
quoted as if the re-scan had not happened. Recorded now; the run under
the current interpreter was repeated 2026-09-04.

**What the re-scan did.** All 1,065 blocked listings re-scanned; 280
moved to `runnable/` (223 on VARPTR alone, 24 NAME+VARPTR, 9 NAME, 22
on the `DEF USR` spacing fix alone, 2 splice); `varptr/`, `name/` and
`merge/` retired; `blocked/` 1,065 → 779; `cmd/` 386 → 500 and
`raw-bytes-in-code/` 135 → 139 as the deeper blockers surfaced.

**The FINDING 16 half was measured, not re-filed — correctly.** `blocked/`
is a static classifier and those `cmd/` listings still contain `CMD`,
so they cannot be promoted. Instead a reachability scan gave the 779 a
second verdict: BLOCKED 541, BLOCKED-RUNS-ANYWAY 238. Crossed against
FINDING 4's 14 CMD-blocked ML-clean listings, exactly one
(`cmd/newmap.bas`) reaches END without its CMD — and only on empty
stdin: its line 160 GOSUB is an `INKEY$` poll, EOF returns an empty
key, `ASC(E$)` falls out of range and it takes the END branch at its
first prompt. Fed a drive number it goes straight to line 200's
`CMD"ROUTE,PR,DO"` and dies `?SN`. **The CMD confound contributes zero
to the gate.** (That EOF-key-poll degenerate exit was a third
BLOCKED-RUNS-ANYWAY cause the archive had not named; it was reported
and the archive measured it in `655ea0b1`: of the 238, only 7 reach
their own END and 231 halt at a key poll.)

**Effect on the six gate files.** `MAIL32`, `MAIL48`, `m3t1s2d` and
`engindb3` left `blocked/varptr/` for `runnable/` under the VARPTR-alone
attribution; only `raw-bytes-in-code/dmbsfh1.bas` and `xwingcf2.bas`
stay blocked. By the gate's literal wording — "blocked listings unlocked
by the core and nothing else" — the number is now **2**, and one of the
two is `xwingcf2`, the weak-entry-evidence file of FINDING 4. By the
gate's intent it is still **6**: none of the six runs to completion.
Re-run 2026-09-04 under trs80basic, `--seed 1`, empty stdin, 6 s:

| file | outcome |
|---|---|
| `runnable/MAIL32.bas`, `MAIL48.bas` | exit 1, `?BATCH: END OF INPUT AT LINE 160` — interactive, untested by an empty-stdin gate |
| `runnable/m3t1s2d.bas` | exit 1, `?OD ERROR IN 191` |
| `runnable/engindb3.bas` | exit 1, `?BATCH: END OF INPUT AT LINE 50`; fed ENTERs on 2026-08-14 it timed out spinning on the USR-gated loop FINDING 15 found |
| `blocked/raw-bytes-in-code/dmbsfh1.bas`, `xwingcf2.bas` | exit 1, `?BATCH: END OF INPUT` |

So the core-dependency claim survives and only the bookkeeping changed:
the archive's headline stats count those four as rescued, and the
core's measured contribution has collapsed almost entirely into the
correctness column. This was the last unmeasured input to the ruling,
and it moved the number down or sideways depending on which reading is
held — the ruling (RULING STATUS above) was taken with it in hand.

**Sweep re-run 2026-09-04** against the re-filed corpus, so the numbers
above can be reconciled with a run today:

| | 2026-08-14 | 2026-09-04 |
|---|---|---|
| listings swept | 4345 | 4339 |
| using USR | 566 | 560 |
| gate population (structural, strict) | 46 | 46 |
| …blocked / runnable | 25 / 21 | 17 / 29 |
| unresolvable loaders (FINDING 7) | 96 | 91 |
| strict-filter random baseline | 5.3% | 3.7% |

The population is the same 46 files; only their halves moved. The
random baseline drifts because it is drawn with a fixed seed from the
length distribution of the raw-byte runs, and that distribution
changed with the six files that left the input set — a reminder that
it is a calibration, not a constant.

The oracle was also re-validated the same day after being repointed at
trs80basic's `src/` (the interpreter's post-split home): 22 exact, 7
patched, 16 silent, 0 contradictions — identical to FINDING 13.

---

## FINDING 21 — the undocumented half of the table checked against an outside source, and SLL was misflagged (2026-09-07)

The opcode table's 1780 entries had never been checked against anything
outside this repo except the 176 hand-authored vectors in
`tests/test_table.py` — vectors this project wrote, over the documented
set only. "ANCHORS BEFORE TRUST" applies to the table itself, so the
reference library was searched for an independent tabulation of the
UNDOCUMENTED set. Exactly one book has one: the Nano Systems **Z80
Microprocessor Reference Card** (1981), pages 7-8.

**The queued grep found nothing, for a notation reason.** The plan was
to grep the card for `IXH`/`IXL`/`IYH`/`IYL`. Zero hits — the card
names the index halves `HX`, `LX`, `HY`, `LY` and says so explicitly in
its prose ("HX is the H of IX"). A negative grep is not a negative
result until the target's own notation has been checked; this one
would have been read as "the card has nothing" and closed the item.

**What the card could actually validate.** Its opcode tables are dense
two-page grids and OCR badly — perhaps a dozen rows survive legibly out
of a few hundred. So a wholesale diff was never available. Three things
were:

| what the card states | result |
|---|---|
| IX/IY each expose two addressable 8-bit registers, so every H/L-operand instruction has a DD and an FD twin | table has **92** such entries, 46 per prefix: 52 LD + 4 each of INC/DEC/ADD/ADC/SUB/SBC/AND/XOR/OR/CP — the shape the card describes |
| timing is the corresponding H/L instruction **plus 4 T-states** | **92 of 92 conform**, zero deviations |
| the legible rows (`LD LX,A` = 221,111; `LD B,HX` = 221,068; `DEC HY` = 253,037; `INC LY` = 253,044; and four more) | all **8 match** the table's mnemonic and encoding |
| the unassigned ED page behaves as a NOP | table names them `DB` (right for a disassembler) but already carries NOP length and timing — corroborated |

**The timing rule is the first external check the cycle column has
ever had.** The column has been "carried but unvalidated" since Phase A
(`z80/table.py` docstring), and the earlier read of this library
concluded the books could not validate it, because the Zilog, Reston
and Leventhal instruction tables OCR to 0-1 parseable rows each. That
conclusion was right about TABLES and wrong about the column: the Nano
card states a RULE instead of tabulating, and a rule survives OCR. It
constrains 92 entries exactly. The other 1688 remain unchecked, and the
pinned single-step vectors are still what settles them.

**THE DEFECT: SLL was flagged as documented.** `SLL` is not in Zilog's
published set at all — the mnemonic itself comes from this card ("we
have given them the mnemonic SLL because it seems most appropriate"),
which lists it among the undocumented instructions. The table set
`undoc` for the CB page from one condition only, "is this a DDCB/FDCB
variant that also copies the result into `R[z]`", so all 24 SLL entries
came out `undoc=False`. Two independent reasons to flag it were being
treated as one. Fixed: the flag is now the OR of them.

This is not cosmetic. The `undoc` flag drives the INVERSE index — the
seam-3 assembler's mnemonic → encoding direction — where a documented
encoding must win over an undocumented one with the same signature. A
misflagged instruction is a wrong answer waiting for the assembler to
be built, which is goal (3).

**Corrected split: 1780 = 1033 documented + 747 undocumented** (was
recorded as 1043 + 737). No decode, no disassembly and no classifier
output changes — the flag is metadata, and the previously-reported
counts were the only casualty.

All four checks are now pinned in
`tests/test_table.py::TestUndocumentedAgainstTheReferenceCard`,
including the split itself, so it cannot drift silently. 104 tests.

**The lesson, and it is the standing one:** the table's own test suite
could not have found this, because the suite was authored from the same
understanding that built the table. It took a source from outside the
project. The card is a two-page scan whose tables are mostly
unreadable, and it still paid for itself twice — one defect and one
column that was believed unvalidatable.
