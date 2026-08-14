# Z80_FINDINGS — Phase A

Numbered findings, basclean-style. Phase A is the static Z80
disassembler/classifier run over the parent corpus's DATA/POKE loader
bytes: measurement, not emulator. It ends here, at a reviewed
checkpoint, with the gate count presented for the user's go/no-go
ruling on Stage 1.

Measured 2026-08-13 against `../awk_BASIC_interpreter/programs/`
(runnable 3283 + blocked 1062 = **4345 listings**). Reproduce with
`python3 -m phasea.sweep`; the suite is `python3 -m unittest discover
-s tests` (64 tests).

---

## THE GATE NUMBER

**5 blocked listings are unlocked by the Z80 core plus the parent's
VARPTR item, and nothing else.** Up to **2 more** are plausible but
unconfirmed (FINDING 8). A further **21 already-runnable listings**
would stop silently returning a stubbed USR value and start returning
the real one — a correctness gain, not a runnability gain.

That is the honest answer to "how many rescued listings does Stage 1
(+VARPTR) actually unlock". It is far below what the blocked-category
sizes suggest, and the reasons are FINDINGS 3, 4 and 5.

| | files |
|---|---|
| listings swept | 4345 |
| …using USR | 566 |
| …carrying cleanly extractable machine code | 46 |
| **blocked listings unlocked by core + VARPTR alone** | **5** |
| blocked, ML clean, but *also* blocked by CMD (Disk BASIC) | 14 |
| blocked, ML clean, but needing a Stage 2 ROM trap | 4 |
| blocked, ?SN on or near the loader line (unconfirmed) | 4 |
| runnable listings whose USR result becomes correct | 21 |

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

## FINDING 8 — three ?SN blockers sit on the loader line itself

Four `sn-when-run/` listings have clean ML. Their recorded `?SN` lines:

- `morsmstr.bas` line 1 — `FOR I=&HE000 TO&HE033:READ D:POKE I,D:NEXT:DEF USR 0=&HE000`
- `quest_2.bas` line 36 — `ML=&HBFE0:FOR X=&HBFE0 TO&HBFFF:READ N:POKE X,N:NEXT:DEF USR 0=ML`
- `lifesm1.bas` line 60 — `IF ERL=30,1700` (Disk BASIC `IF…,line`; unrelated to ML)
- `sleuth2.bas` line 29 — a PRINT and an assignment; unrelated to ML

For the first two the syntax error is *on the machine-language loader
line*. They are plausibly USR-blocked and would join the gate
population, but the ?SN has not been reproduced under the interpreter,
so they are **counted as 0 and reported as "up to +2"**. Confirming
them costs one batch run each.

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

## Corrections owed to DESIGN.md, if the ruling proceeds

1. "ENDGAME/BAS SCAN3 (keyboard scan)" → **event-clock scan,
   pure-compute** (FINDING 2). Appears in DESIGN.md "PHASE A ACCEPTANCE
   ANCHORS", "Testing strategy", and CLAUDE.md "ANCHORS BEFORE TRUST".
2. Stage 2's named candidates (`002BH`, `0049H`, `0033H`, `003BH`,
   `0060H`) have **zero** measured callers (FINDING 9).
3. `raw-bytes-in-code` (135 files) is not 135 ML programs (FINDING 6).
