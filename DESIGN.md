# DESIGN — Z80 core for USR calls from BASIC

Agreed with the user 2026-08-07 (conversation in awk_BASIC_interpreter's
session; summarized in ../trs80basic/STATUS.local.md under
"Machine-language call support"), REVISED 2026-08-13 after ML Stage 0
shipped there and the language ruling changed to Python. This
document is the authoritative context for starting the work.

TERMINOLOGY (note added 2026-09-04; the wording it described was
CONVERTED 2026-09-07). This document used to say "the parent" for the
pre-split ../awk_BASIC_interpreter, which then held both the
interpreter and the corpus. Since 2026-08-28 the interpreter is
../trs80basic and awk_BASIC_interpreter is the corpus archive only;
neither is a parent (CLAUDE.md "COMPANION REPOS"). Every occurrence has
now been replaced by the thing it actually named — "the interpreter" /
trs80basic for interpreter-side work, "the archive" / "the corpus
archive" / awk_BASIC_interpreter for corpus-side work. Nothing about
the decisions or the measurements changed; only the names did.
Interpreter-side history cited by hash (c61fdae5, 7e6f0749, 8c38dca6)
is PRE-SPLIT and lives in awk_BASIC_interpreter's git history; the code
those hashes made is in trs80basic today. The interpreter's STATUS is
trs80basic/STATUS.local.md, a gitignored local file; the archive's is
awk_BASIC_interpreter/STATUS.md.

## Goal and non-goals

GOAL: unmodified rescued BASIC listings that load short Z80 routines via
DATA/POKE and call them with USR(n) should run — the routine executes
against the interpreter's memory model and returns to BASIC.

NON-GOALS, standing:
- Standalone machine-language programs (SYSTEM tapes as primary
  program). That is full-emulator territory; trs80gp/sdltrs exist. Our
  niche is "runs your OCR-rescued BASIC listing directly".
  CLARIFIED 2026-08-13 (user): this is a BUILD boundary, not an
  architecture boundary — an assembler and full machine-code execution
  are ANTICIPATED FUTURE CONSUMERS of this core, and the architecture
  keeps those seams open at zero cost (see "Architecture: the reusable
  seams"). Nothing beyond the seams is built until asked.
- Cycle-accurate timing. Sound routines (cycle-counted OUT loops) get
  "returns promptly, silent" semantics — real-TIME pitch requires cycle
  accuracy we will not build. NOTE kept deliberately open (2026-08-13):
  cycle COUNTING is trivial in a table-driven core (a per-opcode cost
  column), so accumulating cycles between port-FFH toggles recovers
  pitch information for possible OFFLINE sound synthesis someday. Do
  not design the counter out; do not build the synth now.
- Interrupts, R-register-based timing, undocumented-opcode exotica in
  v1 (document what real listings demand; measure first).
- SHIPPING ROM BYTES — never. The Level II ROM is copyrighted. All ROM
  services are high-level traps (HLE) reimplemented from documented
  behavior (same legal footing as the interpreter itself and the RND
  LCG research: behavior reimplementation from documentation is fine,
  verbatim code/bytes are not).

## Language and the runtime seam (RULED 2026-08-13)

The core is PYTHON 3, not awk. Ruling: the machine-language portion is
outside the scope of BASIC, so it follows the project's standing split
(interpreter = awk; non-BASIC tooling = Python — the basclean/detok
precedent). Technical case: a Z80 core is ~700 opcodes of table-driven
decode and wall-to-wall bit arithmetic; Python has real integers with
native bit ops where gawk has doubles plus toU/toS juggling; the
single-step JSON test vectors are a json.load() away; and the Phase A
disassembler/classifier shares its decode tables with the core — one
language for the whole ML toolchain. Speed is a non-issue: the target
is ~440K instr/s (real Model I); table-driven CPython does millions.

The cost is the RUNTIME SEAM: USR fires mid-expression against live
interpreter state (mem[] bytes, video SCR, the live keyboard matrix,
HL back to the evaluator). The agreed shape:

- PERSISTENT COPROCESS, not spawn-per-call: gawk's `|&` two-way
  coprocess keeps a warm Python process with line-based messaging —
  sub-millisecond per call, so per-frame USR calls in games stay
  viable. (Python startup is ~30ms; spawn-per-call is disqualified.)
- CALL FRAME OUT, WRITE-SET BACK: awk sends entry address, the HL
  argument, and the sparse mem[] contents (or deltas — dopoke can log);
  Python executes to the terminating RET, returns HL, the memory
  write-set, and a cycle count. awk applies writes through its existing
  device mapping, so video writes render exactly like POKEs.
- DEVICE READS AS PROTOCOL CALLBACKS: reads of 3800H-38FFH (and any
  other live device) round-trip to awk, which answers from the live
  keyboard matrix — this is what makes wait-for-keypress routines work
  instead of spinning on a stale snapshot, and it gives awk a hook to
  honor Ctrl-C (BREAK) during a runaway routine. An instruction budget
  backstops routines that never RET.
- GRACEFUL DEGRADATION: no python3 on the machine -> USR falls back to
  the interpreter's stub (evaluate and return the argument) with a one-time
  notice. trs80basic.awk stays a complete single-file gawk program, the
  Windows zero-install zip stays honest, and the core is an OPTIONAL
  enhancement — the exact pattern the OLLAMA channel established with
  curl.

Consequence for ship location: the old plan (core as src/p95_z80.awk in
trs80basic) is DEAD. The core lives here; trs80basic gains only the
small coprocess plumbing (protocol client + fallback), which is
legitimately awk.

## Architecture: the reusable seams (RULED 2026-08-13)

The user anticipates eventually wanting an ASSEMBLER and the ability to
execute fully assembled machine code. Ruling: accommodate that in the
architecture — but only as far as the accommodation is free, which is
surprisingly far, because the pieces are things this project needs
anyway. Three seams:

1. THE CPU CORE IS A PURE LIBRARY. No I/O, no TRS-80 knowledge, no
   protocol: a state machine parameterized by memory-read/write and
   port-in/out callbacks. The single-step test vectors FORCE this shape
   — they treat a CPU as (registers, memory) -> (registers', memory')
   with no devices at all — so testability and reusability are the same
   requirement. The USR coprocess runner is one consumer; a future
   standalone runner wires the same callbacks to a flat 64K plus
   devices.

2. ONE DECLARATIVE OPCODE TABLE is the single source of truth: per
   entry — mnemonic, operand pattern, encoding, cycle cost, flag
   effects. Three consumers of the SAME table: the Phase A
   disassembler/classifier (encoding -> mnemonic), the core's decoder
   (encoding -> execution), and a future assembler (mnemonic ->
   encoding, the inverse mapping over data that already exists).
   Hardcoding decode logic per-opcode instead would mean re-deriving
   ~700 encodings by hand when the assembler is wanted. Phase A builds
   this table FIRST, so this ruling shapes the very first artifact.

3. CALLER-OWNED RUN LOOP: the library exposes step() (and run-until
   conveniences); the caller loops under its own budget and hooks. The
   USR runner needs this anyway (instruction budget, Ctrl-C/device
   callbacks); it also leaves the between-instructions slot where a
   future machine could check interrupts — without building any
   interrupt machinery now.

NEAR-TERM ASSEMBLER PAYOFF, noted for when it comes up: magazines often
printed the assembly SOURCE beside the BASIC DATA/POKE loader (endgame's
machine-code DATA block was hand-verified against its printed assembly
listing — see FINDING 29 in awk_BASIC_interpreter's notes). With an
assembler sharing
the table: transcribe the printed assembly, assemble it, and diff the
bytes against the DATA block — OCR damage in DATA blocks, nearly
unverifiable today, becomes machine-checkable. A basclean-adjacent
verification tool, and likely the assembler's first real use — well
before any standalone-execution system exists.

Explicitly NOT accommodated (gets no cheaper by anticipating it):
interrupt emulation, a device framework, cassette/disk, ROM-image
loading, timing beyond the cycle counter. Those remain fenced off with
the standalone non-goal.

## The staged plan

STAGE 0 lived in the INTERPRETER repo and SHIPPED 2026-08-13 (fourth corpus
batch): (a) memory-mapped keyboard matrix for PEEK (3800H-38FFH) —
live, pty-verified, corpus-measured; (b) the USR/DEF USR parse-and-stub
(USRn(x) returns its argument; the `DEF USR 0=` space gap of FINDING 8
fixed 2026-08-14). The formerly-pending interpreter items BOTH SHIPPED
2026-08-14: string packing / VARPTR (live write-through descriptor +
bytes) and program-memory mapping (read-only tokenized image at 42E9H,
validated against tok.py, plus MEMORY SIZE enforcement). CAVEAT for
this repo: the interpreter's VARPTR serves the STRING idiom; numeric/array
VARPTR returns per-element 4-byte-single addresses, NOT a contiguous
2-byte-integer image (see the VARPTR paragraph below). See the
"Machine-language call support" entry in trs80basic/STATUS.local.md.

PHASE A (this repo's FIRST artifact, before any core code): a static
Z80 DISASSEMBLER/CLASSIFIER run over the corpus archive's DATA/POKE
loader bytes. For each listing with a loader, decode the poked bytes
and bucket the routine: sound (cycle-timed OUT 255 loops), keyboard
(reads 3800H-38FFH), video (writes 3C00H-3FFFH), pure compute,
ROM-calling (WHICH entry points, exactly). Output = the real gate
number per bucket, the Stage 2 trap priority list, and the
sound-exclusion count, in one measured pass. The decode table it
builds is THE shared declarative opcode table (see "Architecture: the
reusable seams") — the core's decoder and the future assembler are its
other consumers; nothing is thrown away.
ACCEPTANCE ANCHORS (ruled 2026-08-13, wording corrected 2026-08-14,
see CLAUDE.md "ANCHORS BEFORE TRUST"): the table validates against
known-good disassembly first; the classifier must be checked against
Space Chase and endgame SCAN3, and its buckets reconciled with the
evidence, before corpus-wide counts are reported; Phase A ends in a
findings doc + gate count presented to the user — never a rolling start
into Stage 1.
CORRECTION (Z80_FINDINGS FINDING 2): this section previously called
endgame SCAN3 a KEYBOARD scan. It is not. The 214-byte block at B000H
never touches 3800H-38FFH; it walks a caller-supplied table with IX and
finds a minimum via SBC HL,DE — PURE COMPUTE. SCAN3 is the EVENT-CLOCK
scan (awk_BASIC_interpreter's FINDING 29 notes say so, and line 1240
calls it as
`KJ=USR 1(VARPTR(IC(1)))` over the event-clock array `IC()`). Space
Chase's expectation (sound-only) held.

PHASE A INPUT SET (settled 2026-08-13, second session's question):
- Primary sweep: ../awk_BASIC_interpreter/programs/runnable/ (3,280)
  PLUS programs/blocked/ (1,065, all categories) — counts as of
  2026-08-13. The archive re-filed blocked/ on 2026-08-14 (280 moved
  to runnable/, varptr/ retired, blocked/ 1,065 → 779); the sweep re-run
  2026-09-04 reads 4,339 listings with the same 46-file gate
  population, now 17 blocked / 29 runnable (Z80_FINDINGS FINDING 20).
  Both halves matter:
  blocked/ is the gate constituency; runnable/ includes the 148 files
  the USR stub + DEF FN re-selections moved, and classifying THEIR
  routines answers "does the stubbed USR result silently matter"
  statically. These listings are byte-exact detokenized tape images —
  no OCR damage.
- SKIP programs/Model1/ and the zip archive (same content
  re-organized; double-counts), programs/dialect/ (non-Level-II).
  LargeCollection/Detokenized/ is empty.
- The ~10 transcribed fixtures in ../awk_BASIC_interpreter/OCRsamples/
  (LOCAL-ONLY sibling; includes BOTH anchors, spacechase + endgame):
  read IN PLACE by path, NEVER copy into this repo — transcriptions of
  copyrighted magazine listings, same rule as ROM bytes.
- Mechanical: blocked/ files carry a line-0 `0 REM *** BLOCKED: ... ***`
  annotation header — ignore it during extraction.

LOADER EXTRACTION (settled 2026-08-13): TWO MODULES, ONE PIPELINE,
with a defined JSON intermediate {file, idiom, base (int|symbolic),
bytes, provenance, confidence} — itself a durable corpus artifact (a
manifest of every ML payload in the collection).
- EXTRACTOR (BASIC-idiom knowledge). v1 handles the three dominant
  idioms: literal-address FOR/READ/POKE loops, direct POKE sequences,
  and the VARPTR-array idiom — where DATA values land in an INTEGER
  ARRAY, two little-endian bytes per US%(n) element, base symbolic.
  Computed addresses it cannot resolve are FLAGGED, never guessed —
  "N files unextractable" is a reported category, not silence.
  raw-bytes-in-code/ files are a fourth input form (bytes literal in
  the file): bucket as raw, don't force through the loader parser.
  MEASURED (FINDING 6): that category's 135 files are NOT 135 machine-
  language programs — `B1.bas`'s "raw bytes" are the two-byte fragment
  `W\x08`, i.e. damage. A "decodes cleanly and contains a RET" filter
  passes 27.8% of RANDOM byte strings drawn from the same length
  distribution, so raw-byte payloads carry almost no signal and are
  EXCLUDED from the gate population. Only structurally-anchored idioms
  — a declared load address and a declared count the DATA satisfies
  exactly — are counted.
  Ready-made fixture: endgame's DATA block is count- and
  address-locked against its printed assembly (awk_BASIC_interpreter
  FINDING 29).
- CLASSIFIER (Z80 knowledge, consumes the shared opcode table).
  Symbolic base is mostly harmless: classification keys on ABSOLUTE
  operand addresses (OUT (FFH), reads 3800H-38FFH, writes 3C00H-3FFFH,
  CALL 0A7FH/0A9AH), visible regardless of load address; only
  relative-branch resolution needs the base.
- ESCALATION PATH — BUILT 2026-08-14 (`phasea/oracle.py`, FINDINGS
  13-18): for loaders static extraction cannot crack, the COMPANION
  interpreter is the extraction ORACLE — run the listing under the
  shipped USR stub until the first USR call and dump the poked bytes
  from mem[]. Dynamic fallback, static default. It instruments a
  SCRATCH COPY of trs80basic's src/p*.awk (repointed there 2026-09-04;
  env-var-gated, so the build is inert unless asked, and trs80basic is
  never modified), and it
  is validated against the payloads static extraction already resolves
  before its output counts — zero contradictions required (FINDING 13).
  Applied to FINDING 7's 96 unresolvable loaders it recovered 56
  strict-formed payloads and moved the gate number by one.
Rationale (2026-08-13): the old gate proxy (the archive's usr/ blocked
category, 143 files) dissolved when the stub re-scan moved 90 files
and re-filed the rest under deeper blockers; grep can no longer answer
"what would a working Z80 unlock" — only disassembly can.

STAGE 1 (first core milestone): the Z80 core + minimal USR plumbing.
- Core: full documented instruction set (~700 opcodes incl. CB/DD/ED/FD
  prefixes), registers, flags (mind half-carry and DAA — the classic
  correctness traps), 64K address space synced with the interpreter's
  mem[] via the coprocess protocol (default 255 = absent-RAM reads,
  already authentic).
- USR interface: entry address from the USR vector at 408EH/408FH
  (dec 16526/16527, the classic POKE pair) or trs80basic's DEF USR
  stub table (shipped 2026-08-13 — the stub already parses and
  evaluates the address; the coprocess route gives it a consumer).
- Two ROM traps only: 0A7FH and 0A9AH. Named by the USR idiom these
  are "fetch the argument into HL" and "return HL as the result", but
  CORRECTED 2026-09-06 against the reference library — a trap must
  implement the ROM's REAL semantics, not the idiom:
    0A7FH is CINT — convert the value in ACCUM to a signed 16-bit
    integer in HL (ROM Routines Documented p36; Micro-80 Level II ROM
    Reference Manual p17). The USR idiom works only because the
    argument is already sitting in ACCUM at entry. A faithful trap has
    to reproduce CINT's type handling and its overflow behaviour (?FC
    outside -32768..32767), not merely move a number.
    0A9AH is "ACCUM = HL" — LD (4121H),HL, storing HL into ACCUM as an
    integer-typed result (Farvour p117).
  Consequence: the traps are two general ROM services that the USR
  convention happens to compose, so getting them right also gets any
  OTHER caller of CINT right — and getting them wrong is invisible
  until a listing passes an out-of-range or non-integer argument.
- Exit: RET with the entry-call's return address = done.
- This alone runs pure-computation routines (sorts, memory fills),
  fast-video routines (writes to 3C00H-3FFFH land in the interpreter's
  SCR and RENDER — the mapping already exists), AND — new since Stage 0
  shipped — direct keyboard-matrix scan routines, because reads of
  3800H-38FFH callback into the LIVE matrix. SETTLED by Phase A:
  endgame's SCAN3 IS a Stage 1 acceptance case — but for a stronger
  reason than anticipated. Not because the keyboard matrix went live in
  Stage 0, but because the routine never needed the keyboard at all
  (FINDING 2, pure compute). It needs the CPU, the 0A7FH trap, and
  interpreter-side VARPTR.

STAGE 2: the HLE trap table, grown CORPUS-DRIVEN (the basclean
methodology): implement a ROM entry point only when a measured real
listing calls it. MEASURED (Z80_FINDINGS FINDINGS 9 and 18) — the list
is short, and it took the dynamic oracle to find any of it:
  002BH keyboard scan-once      6 callers
  0033H character to display    6 callers
  1BC0H tokenize / COMPRESS a BASIC line    1 caller
  0028H RST 28H, the Disk BASIC DOS vector  3 callers — belongs with
        the CMD blocker, not with HLE
  0049H wait-key, 003BH char-to-printer, 0060H delay:  ZERO callers,
        measured twice. Do not build them on spec.
CORRECTION 2026-09-06 (reference library, three books agreeing): this
list previously read `1BC0H (not a documented Level II entry)`. It IS
documented — "COMPRESS BASIC LINE" (ROM Routines Documented p62),
"TOKENIZE INPUT ROUTINE" (Level II ROMs, Tab Books, p375), and the
tokenization pass in Farvour p11. So the single caller is calling a
real, specified entry point, and "undocumented" was never the reason to
defer it; the corpus-driven rule is (one caller does not yet earn a
trap). Note also that a program calling the line tokenizer is doing
self-modifying BASIC, which is a bigger question than the trap.
Note the history, because it is the methodology working: FINDING 9
measured ALL five named candidates at zero callers over the statically
extractable population and concluded Stage 2 was unjustified. Closing
FINDING 7 with the oracle put callers on two of them. The rule stands —
implement on measured evidence — but "measured" had to include the
dynamically-resolved loaders before it meant anything.

PARALLEL, INTERPRETER-SIDE: VARPTR — SHIPPED 2026-08-14 (7e6f0749,
pre-split), with one consequence for this repo. The archive's varptr/
blocked category is the second-largest (359 files as of 2026-08-13)
and the dominant idiom is DEF USR=VARPTR(US%(0)) — VARPTR used to
LOCATE the poked routine. The shipped VARPTR returns real, consistent
addresses (so those loader lines now RUN), and the STRING-packing
idiom is served faithfully with write-through bytes. BUT the interpreter
strips `%` suffixes and stores all numerics as doubles, so an integer
array does NOT materialize as contiguous 2-bytes-per-element memory:
VARPTR(US%(0)) addresses a 4-byte Microsoft-single of element 0 only.
A future core can never read the VARPTR-array routine image out of
interpreter memory — those files go through the loader EXTRACTOR's
VARPTR-array idiom (above), which decodes the DATA values directly.
The varptr/ pile was NOT auto-unblocked by the ship; it was
RE-CLASSIFIED by the archive's blocked/ re-scan the same evening
(9ee96ca3): 223 files moved to runnable/
on VARPTR alone and the category was retired — which carried four of
the six gate files into runnable/ without making any of them run
(Z80_FINDINGS FINDING 20). Phase A's count already reflects all of
this: the gate 6 need only the core.

## Technical reference (verified in the 2026-08-07 session; CROSS-CHECKED
## 2026-09-06 against the scanned reference library)

CROSS-CHECK RESULT (2026-09-06, against ROM Routines Documented, the
Micro-80 Level II ROM Reference Manual, the Tab Books Level II ROMs and
Farvour — three or four books per address): every address named in this
section and in the Stage 2 caller list above is CORROBORATED — 0A7FH,
0A9AH, 408EH, 40A4H, 42E9H, 37E8H, 002BH, 0033H, 0028H, 0049H, 003BH,
0060H, 01D3H. Two things changed, both recorded where they belong: the
1BC0H "undocumented" claim (Stage 2 list, above) and the CINT semantics
of 0A7FH (Stage 1 traps, above). The books could NOT validate the
opcode table's cycle column — the OCR'd Zilog/Reston/Leventhal
instruction tables yield 0-1 parseable rows each — so T-states stay
"carried but unvalidated" until the core runs the pinned single-step
vectors against them.

- Model I CPU: Z80 @ 1.77 MHz (~440K instr/s effective). The
  interpreter's
  `speed` throttle can slow replay toward authentic feel.
- Memory map (all already meaningful in the interpreter's mem[]):
  3800H-38FFH keyboard matrix (dec 14336-14591; PEEK(14400) = the
  arrow/space row) — LIVE since 2026-08-13 (Stage 0); the core reads it
  through protocol callbacks.
  3C00H-3FFFH video (dec 15360-16383) — mapped to SCR, renders.
  37E8H-37E9H printer status — reads 63 (attached/ready) since Stage 0.
  40A4H program-start pointer, 408EH/408FH USR vector, 42E9H program
  text base (relevant only to the interpreter's program-mapping item).
- Port FFH (the only port real listings meaningfully touch): bits 0-1
  cassette output levels (the sound trick — alternate 1/2 for a square
  wave through an external amp), bit 3 = 32-column video mode (pairs
  with the interpreter's CHR$(23) roadmap item). OUT elsewhere: no-op or
  error, decide from corpus evidence (Phase A).
- USR call convention (Level II): X=USR(n) jumps to the vector address;
  the routine may CALL 0A7FH to get n in HL, computes, optionally loads
  HL and JPs/CALLs 0A9AH to return a value; plain RET returns without
  one. This is the IDIOM; 0A7FH and 0A9AH are the general ROM services
  CINT and "ACCUM = HL" that it composes — see the Stage 1 trap entry
  for the semantics a trap actually has to implement.

## Testing strategy

- The core is exquisitely testable BEFORE any TRS-80 semantics: the
  per-instruction JSON test-vector suites (Tom Harte / jsmoo
  single-step tests) validate each opcode against thousands of
  pre/post-state pairs — in Python these are a json.load() away; the
  classic ZEXDOC/ZEXALL exercisers are the integration-level check
  (need a tiny CP/M-BDOS print trap to run). RULED 2026-08-13: the
  vector suites are third-party data — gitignore them with a fetch
  script, never commit them (the no-third-party-material practice
  inherited from awk_BASIC_interpreter).
- Adopt the companion repos' culture: pin everything in a regression
  suite from day one; the passing suite pins mechanical behavior, not
  "the emulator works" — real-listing acceptance is the bar.
- North-star for the coprocess (Z80_FINDINGS FINDING 19, 2026-09-02):
  "silent Dancing Demon dances". Its 10.9 KB payload lives inside the
  tokenized program image, writes video DURING the USR call, polls the
  keyboard matrix, and calls no ROM — so it needs streamed video
  writes, live key state, and cycle pacing, and NOT ROM emulation.
  Call-and-return USR (memory in, run, memory out) is not enough for
  that class of program; the protocol has to decide this.
- Acceptance corpus: the corpus archive's rescued listings with USR
  routines.
  Space Chase (80 Micro 5/1982) is sound-only USR — runs with sound
  silently swallowed. ENDGAME/BAS (80 Micro 5/1985) is a Stage 1 case:
  SCAN3 is the EVENT-CLOCK scan, pure compute, NOT the keyboard scan
  this document called it before Phase A measured it (FINDING 2). Phase
  A's classification grew this list to 46 statically-extractable
  payloads, and the oracle added 61 more (FINDING 14; 56 when first
  measured, 61 once the interpreter's FINDING 16/17 fixes let more listings
  reach their loader).
- Regression contract with trs80basic: t1-t28 transcripts exit 0 and
  t7's RND line is the only run-to-run variance (t25-t28 arrived with
  the interpreter's 2026-08-14 batch: RND LCG, Model III display modes,
  MERGE/NAME, program-memory mapping); batch mode exit codes
  unchanged; a new t29+ transcript for coprocess USR (with the
  fallback path tested by pointing the interpreter at a missing
  python3).

## The gate (do not start the CORE without it)

Count rescued listings blocked on USR before building Stage 1 — now
operationalized as PHASE A (the disassembler/classifier), which is
in-gate work: it is measurement, not emulator. As of 2026-08-07 the
honest count was ~2 (Space Chase plays stubbed; endgame can't run). As
of 2026-08-13 the interpreter's stub re-scan moved 90 usr/def files (80 ran
clean — some unknown fraction have load-bearing USR results that only
play-testing or Phase A can flag) and re-filed the deep-ML pile:
varptr 359, raw-bytes-in-code 135, inp 54, system 7. The gate question
is now "how many of these does Stage 1 (+VARPTR, interpreter-side — the
VARPTR half shipped 2026-08-14) actually unlock" — Phase A's output IS
the gate decision input. This is the
estimating twin of the corpus project's standing lesson: "measure the
refutation before shipping a plausible heuristic" — here, count the
unlocked programs before building the emulator.

MEASURED AND CLOSED 2026-08-14. Phase A returned **5**; closing
FINDING 7's 96 unresolvable loaders with the dynamic oracle returned
**6**. The measured machine-code population more than doubled (46 →
107 files) and the unlock count moved by one, because what is scarce
in this corpus is not machine code — it is a listing whose ONLY
obstacle is the absent Z80. Full numbers and method in Z80_FINDINGS.md
(FINDINGS 13-18).

NOTE THE GATE NEVER SET A THRESHOLD. It specifies a measurement and a
decision procedure — present to the user, user rules — not a number
that means "build". That was deliberate, and it means no arithmetic
settles the ruling; the judgment is the user's and was never
pre-committed.

WHAT THE CLOSING RUN FOUND THAT THE GATE DOES NOT SCORE: two
INTERPRETER-side defects each worth more listings than the core is —
`USR n(` at the call site (134 listings, FINDING 17) and the
`PEEK(16396)` cassette/disk probe answering 255 instead of 201 (88
listings, FINDING 16). Both were interpreter-owned and both SHIPPED
there the same day (8c38dca6): 53 blocked listings improved, zero
regressions. The ruling on the core was taken knowing the cheapest
listings-per-hour on the table were not in this repo.

RULED 2026-08-14 (user, in the companion session; recorded in
awk_BASIC_interpreter's PROJECT_MAP.md and CLAUDE.md "WHERE THINGS
STAND"): the rescue count does not justify Stage 1 and no longer has
to. The project is re-founded on its own merits — the user wants a
standalone assembler/disassembler in addition to in-BASIC machine-code
handling — with four goals in priority order: run BASIC with embedded
machine code (core + thin optional bridge), run magazine assembly
listings, write new assembly, disassemble. The pure-library core is
split from the coprocess plumbing so that a 2-to-6-listing payoff never
has to justify touching the interpreter's regression bar. The gate is
CLOSED as a decision input; it survives as the measurement record.
The evening's blocked/ re-scan then moved four of the six gate files
to runnable/ (literal reading 2, intent 6, none of them runs — FINDING
20), which changed the bookkeeping and nothing about the ruling.

## Decisions

RULED 2026-08-13:
1. LANGUAGE: Python 3 (see "Language and the runtime seam").
2. SHIP LOCATION: the core lives HERE; trs80basic gains only the awk
   coprocess plumbing + stub fallback. src/p95_z80.awk is dead.
3. NAME: renamed awk_Z80_core -> trs80_z80_core (no remote existed;
   rename was free).
4. TEST VECTORS: fetch-script + gitignore, never committed.
5. REUSABLE SEAMS: core = pure library, one declarative opcode table,
   caller-owned run loop — assembler and standalone execution are
   anticipated consumers, NOT built until asked (see "Architecture:
   the reusable seams").

STILL OPEN (decide when work starts):
1. LICENSE: trs80basic is GPLv3 (c) 2026 David Forbis; mirroring it
   here is the default assumption. No LICENSE file yet — user ruling
   2026-08-14, with Phase A code already present.
2. R register: the interpreter's authentic-RND roadmap item reads R for
   seeding (RANDOM at 01D3H). Emulating R crudely (increment per
   instruction) lets the two items share it. Low stakes.
3. Coprocess protocol details (framing, delta-vs-full memory sync,
   instruction budget size): design with the plumbing, not before.
   ONE CONSTRAINT already known (interpreter-side review, 2026-08-14):
   the call frame must carry the USR SLOT NUMBER, and the interpreter's
   spaced-call
   fix (8c38dca6) currently DISCARDS the slot digit of `USR n(` before
   dispatch — that dispatch point must pass it through when the
   plumbing is built. Recorded in trs80basic/STATUS.local.md's ML
   entry too.
4. INTEGRATION SHAPE — RATIFIED 2026-09-02/04 (user): companion
   engine, NEVER vendored. A p77 protocol shim in trs80basic, the engine
   discovered via `TRS80_Z80`, releases may bundle the engine (the
   Windows-zip/gawk precedent). The first protocol message carries a
   version; a mismatch is a clean error. Protocol design itself is
   DEFERRED to the big-picture talk; no handshake/protocol code before
   it. Nothing of this is built as of 2026-09-04.

## Standing practices inherited from the companion repos

- Measure before shipping; findings documents with numbered findings;
  every increment committed and green on a written regression bar.
- Commit messages via `git commit -F <file>` (not heredocs); absolute
  paths in shell commands.
- No third-party copyrighted material in the repo (awk_BASIC_interpreter
  keeps its scan corpus in a local-only sibling git repo — the same pattern
  applies to ROM-derived material and the downloaded test-vector
  suites here).
