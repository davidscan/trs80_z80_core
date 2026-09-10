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

**SUPERSEDED IN PART BY FINDING 24 (2026-09-09).** Every number above
reproduces exactly and is kept as measured. Two claims do not: "no ROM
calls at all" is wrong (`CALL 01C9H`, CLS, x4), and "patches 4018H" is a
one-line summary of a self-relocating dispatcher that walks the BASIC
line-record chain — the structure that decides what the core and the
interpreter must provide. FINDING 24 carries the deltas; work items are
in `DANCING_DEMON.md`.

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

---

## FINDING 22 — "protected" and "absent" RAM are the same thing to the interpreter, and goal (1) is what makes that bite (2026-09-07)

Raised by a user question about whether MEMORY SIZE still shields space for
machine code. Read-only investigation of trs80basic's `src/p75_mem.awk` and
`src/p80_stmt.awk`; **nothing was edited there** (CLAUDE.md standing rule).

**STATUS 2026-09-08 — FIXED BY trs80basic, AND THIS FINDING HAD ONLY HALF OF
IT.** They shipped the RAMTOP/HIMEM split exactly as specified below: `RAMTOP`
(65535) now drives the absent-RAM tests, `HIMEM` stays the MEMORY SIZE? answer
driving `PEEK(16561/2)` and `sp_materialize`'s descent. Verified from this side
— the repro that returned 255 now returns 123, `t1`-`t31` exit 0, and
`trs80basic.awk` still equals `cat src/*.awk`.

**THE HALF THIS FINDING MISSED, found by them while chasing it: `POKE
16561/16562` was silently dropped too.** 40B1H was readable but not writable —
`dopeek` routed those addresses to `pm_sysptr`, so a listing that reserved its
own space PROGRAMMATICALLY, without the user touching the boot prompt, got no
reservation. That is the commoner form and it needs no user cooperation: **91
corpus listings POKE 16561/16562** over runnable+blocked, against the 36
candidates measured below for the prompt-driven form. `pm_sethimem()` now moves
the live fence.

THE 91 IS THEIRS AND IT CORRECTS A COUNT OF MINE. This side first measured 88
and challenged their 91; the challenge was wrong. 88 is the **decimal-only**
count (`POKE 1656[12]`), and three further listings — `blocked/cmd/diskdir.bas`,
`runnable/fulscnts.bas`, `runnable/scrgenmf.bas` — spell it in **hex**
(`POKE&H40B1`), which a decimal pattern cannot see. 88 + 3 = 91, verified here.
`fulscnts.bas` also uses a low-byte-only form (`POKE&H40B1,20`, reserving 235
bytes off the top), a fourth spelling. **LESSON, and it generalises past this
count: match loader idioms on the RESOLVED ADDRESS, not on the text.**
`phasea/basic.py` already does — it carries a `&H` literal rule and an
expression evaluator — so no published extractor number is affected; the error
was in an ad-hoc grep, which is the second time in this exchange that ad-hoc
greps were the weak link (see the `LC_ALL=C` trap in FINDING 23's status).

It also produced a CONFIRMED rescue rather than a candidate count.
`runnable/wordsmth.bas` probes for RAM by writing and reading back, then lowers
HIMEM and installs a lowercase driver in the region it reserved. Verbatim A/B,
`MEMORY SIZE? 48887`, run here against a reverted scratch build:

    BEFORE:  nOT RECOMMENDED FOR USE WITH A 16K MACHINE
    AFTER:   lOWERCASE IS LOADED.  pLEASE TYPE RUN AGAIN.

A 48K machine was being told it was 16K because the user reserved memory.
(Their handoff quoted the AFTER line as "48K CONFIRMED - INSTALLING", which
appears nowhere in the corpus — corrected in `handoff/to-trs80basic.md`. The
finding was right; only the quote was reconstructed.)

NOTE the "what it needs" section below is now HISTORY, not a request — it is
what they built. One residual, recorded and NOT requested: `POKE 16561/16562`
without a following `CLEAR` leaves `SPK` cells above the new fence, so a POKE
into the freshly reserved region routes to string write-through instead of
`MEM[]` and is lost on the next reallocation. Defensible as hardware parity; it
matters only because a byte in the protected region that is not in `MEM[]` is a
byte the core will not execute.

### What is already right, and it is more than expected

The VARPTR string space mirrors the real machine's layout exactly.
`sp_materialize()` sets `SSP = HIMEM` on first use and allocates DOWNWARD
(`base = SSP - need + 1`), with a floor of 17131 (42EBH, just above the 42E9H
program text) and `?OM` if it would reach the program. So string space descends
from the MEMORY SIZE ceiling toward the program text, exactly as Level II did.

**Consequence: answering MEMORY SIZE with a lower number really does move packed
strings down and free the region above.** The shield works for string packing
today, for the same structural reason it worked in 1979. And the top-of-memory
pointer is served live — `PEEK(16561/16562)` returns `HIMEM` lo/hi (40B1H/40B2H,
corroborated in ROM Routines Documented, the Micro-80 ROM Reference Manual and
Farvour) — so a listing that COMPUTES its load address from the ceiling gets a
correct answer. The default is `HIMEM = 65535`, i.e. the machine presents itself
as a fully expanded 48K Model I, which is the right default.

### The defect

Both PEEK and POKE treat everything above `HIMEM` as ABSENT RAM:

    st_peek:  if (a > HIMEM) return 255      # absent RAM above MEMORY SIZE
    st_poke:  else if (a > HIMEM) { }        # absent RAM: discarded

On real hardware the MEMORY SIZE? answer does not make memory absent. It makes
it **protected** — present, readable, writable RAM that BASIC will not allocate
into. That is the entire point of the prompt, and it is where machine code goes.
The two concepts have been collapsed into one, keyed on `HIMEM`.

So the single most classic machine-code-in-BASIC idiom is half-implemented:

    MEMORY SIZE? 32000                     <- string space correctly moves down
    FOR I=32001 TO 32100: READ B: POKE I,B: NEXT   <- bytes DISCARDED
    DEF USR0=32001 : X=USR0(0)             <- would execute nothing

The shielding half works; the reserved region is not writable.

### Why it has been harmless until now, and why it stops being

The default `HIMEM` is 65535 and pressing ENTER at the prompt keeps it there, so
nothing sits above the ceiling unless a program or user actually sets a lower
one — and until there is a core, no bytes poked above it would ever have been
EXECUTED, so discarding them cost nothing observable. Treating high addresses as
absent is even authentic for a genuinely smaller machine: on a 16K Model I,
addresses above 7FFFH really are absent, and 255-on-read is correct.

Goal (1) is what activates it. The moment a core executes what was poked, the
distinction between "BASIC must not use this" and "this is not there" becomes
load-bearing.

### What it needs (REPORTED, not built — this is interpreter-owned)

Two quantities where there is currently one:

- **RAMTOP** — the machine's physical RAM top (FFFFH for 48K, BFFF for 32K,
  7FFF for 16K). Above it: absent. 255 on read, discard on write. Authentic.
- **HIMEM** — the MEMORY SIZE? answer, at or below RAMTOP. Between HIMEM and
  RAMTOP: **protected RAM.** Present, readable, writable, simply never allocated
  by BASIC's string space. This is the region machine code lives in.

`PEEK(16561/16562)` keeps reporting HIMEM, which is already correct. The string
allocator keeps descending from HIMEM, which is already correct. Only the two
absent-RAM tests change, and they become tests against RAMTOP.

This also gives the machine-size question a home: a core that presents itself as
48K should say so in one place, and RAMTOP is that place.

### Addendum: the string-space allocator does not reclaim (same reading)

`sp_materialize()` is a BUMP allocator. `SSP` only ever descends; `sp_free()`
deletes a variable's mapping cells (`SPK`/`SPT`/`SPV`) but does not raise `SSP`,
and `sp_reset()` restores it to `HIMEM` wholesale on CLEAR/RUN/NEW. So a program
that re-VARPTRs in a loop — legitimate, since the documented behaviour is that a
re-VARPTR after the value changed allocates a fresh region — marches `SSP` down
toward the 42EBH floor and eventually raises `?OM`, with most of the space it
passed over dead but unreclaimable.

Harmless for the corpus idiom (pack once, call many times) and NOT a bug in what
was built: the shipped behaviour is documented and matches the real machine's
lack of string reclamation without an explicit collection. Recorded because it
becomes a scaling limit exactly where goal (1) leans hardest — a long-running
program that repeatedly re-packs a routine. On real hardware this is what
`FRE("")` triggering garbage collection was for. Interpreter-owned; reported.

### Note for the protocol, when it comes

The coprocess memory image must carry the protected region. If the call frame
ships "the sparse mem[]" and mem[] never received the discarded POKEs, the core
executes an empty region and returns silently — which is the FINDING 16/17
failure shape again: a wrong answer with no error. Whatever the protocol does
about absent versus protected has to be decided once, on this distinction.

---

## FINDING 23 — the program image shadows POKEd machine code, and an unbounded program shadows the whole address space (measured 2026-09-07)

Asked by the user: does an 800K BASIC program break string packing or embedded
machine code if the loader sits three-quarters of the way through the listing?
Measured against trs80basic in batch mode; **nothing was edited there**.

**STATUS 2026-09-08 — REPORTED, MEASURED BY THE INTERPRETER SIDE, DEFERRED BY
AGREEMENT.** trs80basic ran the shadow dynamically over all 4,339 corpus files
(instrumenting the one branch, validated against this finding's own repro) and
recorded **zero shadow events**; 385 loader listings, 224 of which executed at
least one POKE, 28,483 addresses written. Their coverage caveat is honest —
batch stdin means many listings stop at their first `INPUT`, so the zero is a
lower bound, not a proof. That CONFIRMS this finding's own corrected estimate of
"approximately zero" (see the CORRECTION below) and refutes the withdrawn 123.
The writable program-image mapping stays unbuilt, and this side agreed: the
Dancing Demon payload is READ out of the image, not self-modifying, so goal (1)
does not need it — with the caveat that FINDING 19's linear sweep is a signal,
not a control-flow proof, so that "no" is revisable once the core can run it.
**The `PEEK(16634)` sub-bug below was FIXED the same day** (`pm_sysptr` now
masks the high byte): the 1200-line program answers 125 where it answered 381,
verified here. Full exchange in `handoff/to-trs80basic.md`.

**BOUND CORRECTION 2026-09-08 (this finding was right when written and is now
stale).** The `min(PMEND, HIMEM)` bounds below described the code as it stood on
2026-09-07, where `st_peek`'s `a > HIMEM` absent-RAM test fired before the
program-image branch. trs80basic shipped the FINDING 22 fix on 2026-09-08, and
that test is now `a > RAMTOP`. **So HIMEM no longer bounds the shadow at all:**
lowering it with `MEMORY SIZE?` or `POKE 16561/16562` does not shrink the
shadowed range, which is now simply `[17129, PMEND)` capped at RAMTOP. The
thresholds quoted further down (~14.8 KB for a routine at 32000, ~47 KB to
shadow everything) are unaffected — they never depended on HIMEM. The full
post-fix resolution order, which the core must reproduce byte-for-byte, is set
out in `handoff/to-trs80basic.md` §2 of the 2026-09-08 reply; note in particular
that `a in SPK` outranks the program image, which is what makes string packing
immune, and that unwritten memory reads **255**, not 0.

### Position in the listing is irrelevant. Total program SIZE is the variable.

`pm_build()` serialises the whole program from 42E9H (17129) upward and sets
`PMEND = 17129 + crunched size + 2`. `st_peek()` then resolves any address in
`[17129, min(PMEND, HIMEM)]` from the program image `PMEM[]`, while `st_poke()`
writes to `MEM[]`. The two never meet — documented in p75's header as "POKEs
into the region land in MEM and are never read back", with the writable mapping
deliberately unbuilt. **So a POKE below PMEND is written and then invisible.**

Confirmed by probing at line 1 versus line 9000 of the same 300-line program:
identical results. Only the total changes anything.

### Measured

Probe: `POKE addr,v` then `PEEK(addr)`, with REM padding to set the size.
The padding byte is `X` = 88, so **88 means "read the program image instead"**.

| program | PMEND | PEEK 20000 | PEEK 60000 | PEEK 65000 | VARPTR A$ |
|---|---|---|---|---|---|
| probe only | 17346 | 222 ✓ | 200 ✓ | 111 ✓ | 65533 |
| 300 lines (~20 KB) | 37446 | **88** | 200 ✓ | 111 ✓ | 65533 |
| 13000 lines (~850 KB) | 887944 | **88** | **88** | **88** | 65533 |

So the answer to the 800K case is unambiguous: **every** POKE in the 16-bit
space is shadowed. A DATA/POKE loader anywhere would deposit nothing a PEEK —
or a core reading through the same path — can see.

### The rule, and the two thresholds worth knowing

The program image shadows `[42E9H, min(PMEND-1, HIMEM)]`. Therefore a loader
targeting address T is shadowed once the crunched program exceeds `T - 17129`
bytes: **~14.8 KB for a routine at 32000, ~42.8 KB for one at 60000.** Once the
program passes **48,404 bytes (~47 KB)** PMEND clears 65535 and the entire
usable address space is shadowed. Note how ordinary the first threshold is —
this is not an exotic-program problem.

### STRING PACKING IS UNAFFECTED — at any program size

`VARPTR(A$)` returned 65533 in every run above. `st_peek()` tests `a in SPK`
BEFORE the program-image branch, so projected string bytes always win, and
`sp_materialize()` descends from `HIMEM` with no reference to the program at
all. String packing therefore keeps working in an 800K program exactly as in a
20-line one. **Of the two idioms the user asked about, one is immune and the
other fails silently.**

The corollary is a layering accident rather than a plan: the string floor is a
hardcoded 17131, not `PMEND`, so for a large program string space and program
image OVERLAP, with strings shadowing the image. On real hardware they cannot
overlap — string space is bounded below by the end of the program.

### A plain bug found alongside: PEEK(16634) can return a non-byte

40F9H/40FAH (16633/16634) serve "start of variables" as `PMEND % 256` and
`int(PMEND / 256)`, uncapped. Measured `PEEK(16634)` = **381** for a 1200-line
program and **3468** for the 13000-line one. A PEEK must return 0-255. This is
wrong independently of the core, and independently of any of the above.

### Assessment

The shadowing mechanism is documented and was a reasonable simplification while
nothing executed the bytes: with no core, a POKE-loader that deposits nothing is
a program that already did nothing. Goal (1) is what converts it into the
FINDING 16/17 failure shape — a wrong answer, no error, exit 0. What is NOT
covered by the existing rationale is the SCOPE: a reader of "POKEs into the
region" would take "the region" to mean where the program sits, which on real
hardware is bounded by 48K. An unbounded program makes the region everything.

Interpreter-owned; reported, not built. It bears directly on the DESIGN.md
address-space invariant: the 16-bit window is only faithful while what is
projected into it stays inside it, and the program image is the projection that
does not currently respect its own window.

Also relevant to FINDING 22's severity: batch mode always runs with
`HIMEM = 65535` (measured in all runs), so the protected-versus-absent discard
there is reachable only through the interactive MEMORY SIZE? prompt. FINDING 23
needs no prompt and no unusual program.

## FINDING 24 — the north star re-measured: Dancing Demon is a self-relocating dispatcher, it DOES call the ROM, and it needs a stack (2026-09-09)

Asked for a readiness assessment of this repo against a "Dancing Demon
(no sound)" run. FINDING 19 was re-derived from its own prose rather
than trusted, because **no committed code implements its extraction
recipe** — that is the first finding here and the reason the rest were
available to be found.

### What reproduced exactly

Re-implementing FINDING 19's recipe (walk the line records, concatenate
the bodies of lines 2..258 including each terminating `00`, base mapped
from 42E9H) reproduces every number it reported:

| FINDING 19 | re-measured 2026-09-09 |
|---|---|
| 106 fake BASIC lines, 2..258 | 106 (line numbers 2..207) |
| 10,931 bytes | 10,931 |
| loads at 42F6H | 42F6H |
| 8,068 insns, 0 undecodable | 8,068, 0 undecodable, 0 truncated, 0 undoc |
| 34 video immediates in 3C00-3FFFH | 34 |
| keyboard matrix once, `LD HL,38FFH` | 1 |
| sound exactly twice, 43FC/4401H | 2 |
| patches 4018H, reads (40A4H) | both present |

The load address is self-confirming: the BASIC driver computes
`N = PEEK(16549)*256 + PEEK(16548) + 13` and POKEs it to 16526/16527,
and 42E9H + 13 = 42F6H. `z80/disasm.py` held again over 8,068
instructions as its second outside consumer.

### 1. THE PAYLOAD IS A DISPATCHER, NOT A ROUTINE — the load-bearing structure FINDING 19 did not record

The entry routine, disassembled:

    42F6  211840    LD HL,4018H
    42F9  36C3      LD (HL),C3H        ; write a JP opcode into system RAM
    42FB  2AA440    LD HL,(40A4H)      ; start of BASIC program text
    42FE  3E19      LD A,19H           ; wanted line number, low byte = 25
    4300  E5        PUSH HL
    4301  DDE1      POP IX
    4303  DDBE02    CP (IX+02H)        ; compare against this record's lineno
    4306  2806      JR Z,430EH
    4308  5E        LD E,(HL)          ; else follow the next-line pointer
    4309  23        INC HL
    430A  56        LD D,(HL)
    430B  EB        EX DE,HL
    430C  18F2      JR 4300H
    430E  23 23 23 23                  ; skip next-ptr + lineno
    4312  221940    LD (4019H),HL      ; complete the JP at 4018H
    4315  212840    LD HL,4028H        ; and a second trampoline at 4028H
    ...
    431F  CD1840    CALL 4018H

So the payload **walks the BASIC line-record chain at run time, matching
on line number, and patches a JP trampoline in system RAM**. The 106
fake lines are 106 dispatchable entry points addressed by line number:
the line-record chain IS the routine's symbol table. Reached call
counts: `CALL 4018H` x243, `CALL 4028H` x23 (linear sweep: 422 and 25).

Three consequences for the core, none of them optional:

- the tokenized program image must be mapped at 42E9H **with correct
  next-line links**. DESIGN.md notes the `% 65536` wrap in `pm_build`
  as a caveat about walking the chain; for this program the chain is
  the dispatch mechanism, so a wrong link is a jump into garbage with
  no error — the FINDING 16/17 failure shape again.
- **4000-41FF must be writable AND executable** core RAM. This is
  self-modifying code, but its target is the communication region, not
  the program image.
- 40A4H/40A5H must read 42E9H, on both the BASIC side (`PEEK(16548/9)`)
  and the core side (`LD HL,(40A4H)`).

### 2. CORRECTION to FINDING 19 — "no ROM calls at all" is wrong

`CALL 01C9H` appears **4 times** (2 of them reached from the entry
points), each in clean code immediately following a NUL-terminated
message, all four in the identical idiom:

    2E 00 | CD C9 01 | 3E 03 | 08 | 3E xx | CD 18 40

Four independent books in the reference library agree on what 01C9H is:
"Performs the CLS function" (Level II ROM Reference Manual), "CLS: Clear
CRT video display & home cursor" (Level II ROMs, Tab), "A CALL 1C9H will
clear the screen. (CLS)" (Assembly Language Made Simple), plus
Encyclopedia Vol 08. It is a **documented** entry point, so it is
HLE-trappable under the never-commit-ROM rule, and reimplementing CLS is
trivial. But the count is one, not zero, and **01C9H is not on Stage 2's
trap list** (DESIGN.md: 002BH, 0033H, 1BC0H, 0028H) because the sweep
population excludes `LargeCollection/` — see item 6.

FINDING 19's linear-sweep caveat is what saved it from being worse: it
said "the proof is running it", and it was right to.

### 3. A Z80 STACK INSIDE THE 64K IS REQUIRED, AND UNDESIGNED

Reached code: **CALL x268, RET x51, PUSH x14, POP x14, EXX x20,
`EX AF,AF'` x138.** `PUSH HL / POP IX` sits in the verified entry
routine above, so this is not a mis-decode artifact.

DESIGN.md states twice that BASIC's stack is "an awk structure, not
addresses" and lives outside the 64K ("The address space", and the
inversion argument). That is right for BASIC and insufficient for the
core: a Z80 executing 268 calls needs a real stack at a real 16-bit
address. Nothing in DESIGN.md records where SP is initialised, who owns
it across the USR boundary, or where the USR return address is pushed.
Recorded as a gap, not resolved here.

### 4. THE WRITABLE PROGRAM IMAGE IS NOT NEEDED — now measured, not reasoned

`handoff/to-trs80basic.md` answered trs80basic's question ("do we need
the writable program image?") with "No. Not now, and not for Dancing
Demon", by reading FINDING 19. That answer is **correct, and now has a
measurement behind it.** Every real absolute write in reached code goes
to 4019H, 401BH, 4020H, 4023H, 4029H, 402BH or 4100H — all system RAM.
The four absolute writes that land inside the image (4C2DH, 7320H,
7420H, 7720H) are ASCII text mis-decoded as `LD (nn),A`; their operand
bytes are spaces and lowercase letters.

Honest limit: 172 HL-indirect and 14 stack writes cannot be resolved
statically, so this is strong evidence, not proof. The proof is still
running it.

### 5. ONE PAYLOAD, FIFTEEN FILES

All 15 tokenized Dancing Demon images in the archive — 1979 Radio Shack,
1979 80-NW, 1986 Powersoft, and the `demon.dsk`/`demon.snd`/`dancedem`
copies — carry a **10,931-byte payload at 42F6H with 106 fake lines and
an identical device profile** (34 video / 1 keyboard / 2 OUT / 4 CALL
01C9H / 422 CALL 4018H). Eight are byte-identical; the other seven differ
in data bytes only. Only the BASIC driver varies (179-193 line records).

So "does it run Dancing Demon" is **one** acceptance target, and the
choice of variant is a matter of which driver is convenient.

### 6. SILENCING IS CLEAN, AND THE DELAY LOOPS ARE THE TEMPO

The sound routine in full:

    43F7  210102    LD HL,0201H
    43FA  0EFF      LD C,FFH
    43FC  ED61      OUT (C),H
    43FE  42        LD B,D
    43FF  10FE      DJNZ 43FFH
    4401  ED69      OUT (C),L
    4403  42        LD B,D
    4404  10FE      DJNZ 4404H
    4406  1D        DEC E
    4407  20F3      JR NZ,43FCH

Port FFH is not sound-only: **bit 3 selects 32-character video mode**
(confirmed in the library — "BIT 3 Select video 32 character mode if
set"). The values written here are H=02H and L=01H, so bit 3 is clear in
both and suppressing the two `OUT`s has **no display side effect**. The
surrounding `DJNZ` loops must still EXECUTE — they are the delay that
sets the tempo, and skipping them would silence the demon and make it
dance too fast.

### 7. SCOPE AND SPEED

| measure | value |
|---|---|
| reachability from the 106 entries + 42F6H | 8,916 / 10,931 bytes (81.6%), 7,018 insns |
| distinct encodings executed | **169** — ~16% of the table's 1,033 documented |
| distinct mnemonics | **23** |
| pages needed | main 161, ED 4, DD/FD 4 — **no CB page** |
| NOT observed | DAA, block ops (LDIR/CPIR), interrupts (DI/EI/IM), undocumented opcodes |
| reached-code mean, table base cycle column | **5.67 T-states/insn** |
| real-time bar at 1,774,080 T-states/s | **313,030 insn/s** |
| pre-decoded closure dispatch, full flag computation (CPython 3.11) | 5,470,126 insn/s — **~17x headroom** |
| `z80/disasm.py` decode path | 724,554 insn/s — **2.3x** the bar |

Timing is comfortable, with one architectural constraint: **do not reuse
the disassembler's decode path as the execution decoder.** 2.3x leaves
no margin for memory callbacks, video streaming and coprocess I/O; a
pre-decoded dispatch has 17x and does. 169 is a lower bound — dynamic
dispatch through 4018H is unresolved and 18.4% of the payload is
unreached.

Correction to README while here: it puts the real Model I at
"~440K instr/s". The table's own cycle column says ~164K insn/s on a
general mix and 313K on this payload's mix. The direction of README's
claim (Python is faster) survives; the figure does not.

### 8. THE INSTRUMENT GAP — why none of this was measured before

- `LargeCollection/` is **outside the sweep population** (`phasea/sweep.py`
  reads `runnable/` + `blocked/` only, by the settled Phase A input set).
  No committed instrument has ever measured this program.
- The corpus file is a **tokenized** image (FF-prefixed, `8D` GOTO token).
  `phasea/basic.py:read_source` is byte-safe latin-1 but assumes
  DETOKENIZED text, and there is no detokenizer in this repo.
- FINDING 19's extraction recipe exists **only as prose**. It had to be
  reimplemented to run this audit.

Reproduce the extraction (the recipe FINDING 19 described in words):

    def records(b, base=0x42E9):
        i = 1 if b[:1] == b'\xff' else 0      # leading FF marker
        s, out = i, []
        while i + 4 <= len(b):
            nxt = b[i] | (b[i+1] << 8)
            if nxt == 0: break
            ln = b[i+2] | (b[i+3] << 8)
            j = i + 4
            while j < len(b) and b[j] != 0: j += 1
            out.append((base + (i - s), ln, b[i+4:j]))
            if j >= len(b): break
            i = j + 1
        return out
    fake = [r for r in records(open(PATH,'rb').read()) if 2 <= r[1] <= 258]
    payload = b''.join(body + b'\x00' for _, _, body in fake)   # 10,931 bytes
    base    = fake[0][0] + 4                                    # 42F6H

Committing this as a real extractor idiom is DD-1 in `DANCING_DEMON.md`.

### 9. THE PAYLOAD IS POSITION-INDEPENDENT — correcting DESIGN.md's relocation worked example (measured 2026-09-09)

DESIGN.md ("The address space", CAN A TRANSLATION TABLE REACH PAST 64K)
uses this program as its worked example for why relocation needs a fixed
load address:

> Dancing Demon is 10,931 bytes loading at 42F6H. `JR` and `DJNZ` reach
> +/-127 bytes, so a routine that size CANNOT be internally connected by
> relative jumps alone; it necessarily contains absolute JP/CALL into its
> own body, and therefore must load where it was assembled to load.

The premise is true. **The inference is false, and measurably so.**
Measured by LINEAR SWEEP over the whole 10,931 bytes — not just the
81.6% reached, so data bytes are included and can only inflate these
counts:

| | |
|---|---|
| distinct CALL targets in the entire payload | **3** — 01C9H, 4018H, 4028H |
| absolute CALL into its own body | **0** |
| internal JP | **0** (one JP in the sweep, not internal) |
| internal control flow, reached code | `JR` x365, `DJNZ` x22 — relative only |

So the routine is not connected by relative jumps ALONE — it is
connected by relative jumps PLUS A DISPATCHER. Everything beyond +/-127
bytes goes through the 4018H trampoline, whose target is computed at run
time by walking the BASIC line-record chain (section 1). That chain is a
**run-time relocation table**, and it is exactly why the payload can sit
inside the program image wherever BASIC puts it and still find its own
routines: it never names an address inside itself.

**The conclusion inverts.** Far from proving that a routine this size
must load where it was assembled, Dancing Demon is a demonstration of the
opposite — a 10.9 KB fully position-independent payload, using the
interpreter's own program structure as its symbol table. The period
technique it demonstrates is not "load at a fixed address"; it is "locate
yourself from (40A4H) and dispatch by line number".

What survives of the DESIGN.md passage: relocation is only safe for
position-independent code, and real routines mostly are not. That general
claim stands — this program is the exception that shows what it costs to
be the exception, not the rule's illustration. The section's actual
subject (a 16-bit operand field cannot name address 617,129) is untouched.

### Assessment

The terrain is friendlier than expected and the obstacles moved. The CPU
is cheap: 169 encodings, 23 mnemonics, no CB page, no DAA, no
interrupts, 17x timing headroom, one trivial documented ROM trap, two
instructions to silence with no side effect. What is expensive is
everything around it — the image projection with correct links, a
writable and executable communication region, a stack policy that does
not exist on paper, and the streaming protocol DESIGN.md already
identified as the real question.

Neither DESIGN.md open question blocks this program: the image spans
42E9H-7DE5H (15,100 bytes, 33,307 clear of FFFFH) so the window-overflow
policy does not bind, and the stub-loudness question is orthogonal.

THREE DOCUMENTS ARE CORRECTED HERE: FINDING 19 (the ROM call count and
the dispatcher structure), README (the Model I instruction rate), and
DESIGN.md (the north-star bullet's "calls no ROM", the self-modifying-code
paragraph's "sits on the north-star path", and the relocation worked
example, section 9 — all three applied 2026-09-09). Every correction was
produced by resolving addresses through the disassembler rather than by
matching text — the discipline CLAUDE.md's "corpus counting traps" rule
demands, applied to a program the corpus tooling cannot currently read.
