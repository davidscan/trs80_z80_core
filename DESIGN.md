# DESIGN — Z80 core for USR calls from BASIC

Agreed with the user 2026-08-07 (conversation in the parent repo's
session; summarized in ../awk_BASIC_interpreter/STATUS.md under
"Machine-language call support"), REVISED 2026-08-13 after ML Stage 0
shipped in the parent and the language ruling changed to Python. This
document is the authoritative context for starting the work.

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
  the parent's stub (evaluate and return the argument) with a one-time
  notice. trs80basic.awk stays a complete single-file gawk program, the
  Windows zero-install zip stays honest, and the core is an OPTIONAL
  enhancement — the exact pattern the OLLAMA channel established with
  curl.

Consequence for ship location: the old plan (core as src/p95_z80.awk in
the parent) is DEAD. The core lives here; the parent gains only the
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
listing — see the parent's FINDING 29 work). With an assembler sharing
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

STAGE 0 lived in the PARENT repo and SHIPPED 2026-08-13 (fourth corpus
batch): (a) memory-mapped keyboard matrix for PEEK (3800H-38FFH) —
live, pty-verified, corpus-measured; (b) the USR/DEF USR parse-and-stub
(USRn(x) returns its argument; the `DEF USR 0=` space gap of FINDING 8
fixed 2026-08-14). The formerly-pending parent items BOTH SHIPPED
2026-08-14: string packing / VARPTR (live write-through descriptor +
bytes) and program-memory mapping (read-only tokenized image at 42E9H,
validated against tok.py, plus MEMORY SIZE enforcement). CAVEAT for
this repo: parent VARPTR serves the STRING idiom; numeric/array
VARPTR returns per-element 4-byte-single addresses, NOT a contiguous
2-byte-integer image (see the VARPTR paragraph below). See the parent
STATUS.md roadmap.

PHASE A (this repo's FIRST artifact, before any core code): a static
Z80 DISASSEMBLER/CLASSIFIER run over the parent corpus's DATA/POKE
loader bytes. For each listing with a loader, decode the poked bytes
and bucket the routine: sound (cycle-timed OUT 255 loops), keyboard
(reads 3800H-38FFH), video (writes 3C00H-3FFFH), pure compute,
ROM-calling (WHICH entry points, exactly). Output = the real gate
number per bucket, the Stage 2 trap priority list, and the
sound-exclusion count, in one measured pass. The decode table it
builds is THE shared declarative opcode table (see "Architecture: the
reusable seams") — the core's decoder and the future assembler are its
other consumers; nothing is thrown away.
ACCEPTANCE ANCHORS (ruled 2026-08-13, see CLAUDE.md "ANCHORS BEFORE
TRUST"): the table validates against known-good disassembly first; the
classifier must bucket Space Chase (sound) and endgame SCAN3 (keyboard)
correctly before corpus-wide counts are reported; Phase A ends in a
findings doc + gate count presented to the user — never a rolling start
into Stage 1.

PHASE A INPUT SET (settled 2026-08-13, second session's question):
- Primary sweep: ../awk_BASIC_interpreter/programs/runnable/ (3,280)
  PLUS programs/blocked/ (1,065, all categories). Both halves matter:
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
  Ready-made fixture: endgame's DATA block is count- and
  address-locked against its printed assembly (parent FINDING 29).
- CLASSIFIER (Z80 knowledge, consumes the shared opcode table).
  Symbolic base is mostly harmless: classification keys on ABSOLUTE
  operand addresses (OUT (FFH), reads 3800H-38FFH, writes 3C00H-3FFFH,
  CALL 0A7FH/0A9AH), visible regardless of load address; only
  relative-branch resolution needs the base.
- ESCALATION PATH, recorded not built: for loaders static extraction
  cannot crack, the parent interpreter is the extraction ORACLE — run
  the listing under the shipped USR stub until the first USR call and
  dump the poked bytes from mem[]. Dynamic fallback, static default.
Rationale (2026-08-13): the old gate proxy (the parent's usr/ blocked
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
  (dec 16526/16527, the classic POKE pair) or the parent's DEF USR
  stub table (shipped 2026-08-13 — the stub already parses and
  evaluates the address; the coprocess route gives it a consumer).
- Two ROM traps only: 0A7FH (fetch the USR integer argument into HL)
  and 0A9AH (return HL to BASIC as the function result).
- Exit: RET with the entry-call's return address = done.
- This alone runs pure-computation routines (sorts, memory fills),
  fast-video routines (writes to 3C00H-3FFFH land in the interpreter's
  SCR and RENDER — the mapping already exists), AND — new since Stage 0
  shipped — direct keyboard-matrix scan routines, because reads of
  3800H-38FFH callback into the LIVE matrix. Endgame's SCAN3 may
  therefore be a STAGE 1 acceptance case, not Stage 2 as originally
  assumed; Phase A's disassembly of it settles which.

STAGE 2: the HLE trap table, grown CORPUS-DRIVEN (the basclean
methodology): implement a ROM entry point only when Phase A shows a
measured real listing calls it. Known candidates (from Microsoft BASIC
Decoded and the Paay ROM reference): 002BH keyboard scan-once, 0049H
wait-key, 0033H character-to-display, 003BH character-to-printer
(likely route to the parent's LPRINT stream or refuse), 0060H delay.
Start Z80_FINDINGS.md on the first real listing, findings-numbered like
basclean's.

PARALLEL, PARENT-SIDE: VARPTR — SHIPPED in the parent 2026-08-14
(7e6f0749), with one consequence for this repo. The parent's varptr/
blocked category is the second-largest (359 files as of 2026-08-13)
and the dominant idiom is DEF USR=VARPTR(US%(0)) — VARPTR used to
LOCATE the poked routine. The shipped VARPTR returns real, consistent
addresses (so those loader lines now RUN), and the STRING-packing
idiom is served faithfully with write-through bytes. BUT the parent
strips `%` suffixes and stores all numerics as doubles, so an integer
array does NOT materialize as contiguous 2-bytes-per-element memory:
VARPTR(US%(0)) addresses a 4-byte Microsoft-single of element 0 only.
A future core can never read the VARPTR-array routine image out of
parent memory — those files go through the loader EXTRACTOR's
VARPTR-array idiom (above), which decodes the DATA values directly.
The varptr/ pile is NOT auto-unblocked by the ship; re-classification
is a future measurement (recorded in the parent STATUS.md). Phase A's
count already reflects all of this: the gate 5 now need only the core.

## Technical reference (verified in the 2026-08-07 session)

- Model I CPU: Z80 @ 1.77 MHz (~440K instr/s effective). The parent's
  `speed` throttle can slow replay toward authentic feel.
- Memory map (all already meaningful in the interpreter's mem[]):
  3800H-38FFH keyboard matrix (dec 14336-14591; PEEK(14400) = the
  arrow/space row) — LIVE since 2026-08-13 (Stage 0); the core reads it
  through protocol callbacks.
  3C00H-3FFFH video (dec 15360-16383) — mapped to SCR, renders.
  37E8H-37E9H printer status — reads 63 (attached/ready) since Stage 0.
  40A4H program-start pointer, 408EH/408FH USR vector, 42E9H program
  text base (relevant only to the parent's program-mapping item).
- Port FFH (the only port real listings meaningfully touch): bits 0-1
  cassette output levels (the sound trick — alternate 1/2 for a square
  wave through an external amp), bit 3 = 32-column video mode (pairs
  with the parent's CHR$(23) roadmap item). OUT elsewhere: no-op or
  error, decide from corpus evidence (Phase A).
- USR call convention (Level II): X=USR(n) jumps to the vector address;
  the routine may CALL 0A7FH to get n in HL, computes, optionally loads
  HL and JPs/CALLs 0A9AH to return a value; plain RET returns without
  one.

## Testing strategy

- The core is exquisitely testable BEFORE any TRS-80 semantics: the
  per-instruction JSON test-vector suites (Tom Harte / jsmoo
  single-step tests) validate each opcode against thousands of
  pre/post-state pairs — in Python these are a json.load() away; the
  classic ZEXDOC/ZEXALL exercisers are the integration-level check
  (need a tiny CP/M-BDOS print trap to run). RULED 2026-08-13: the
  vector suites are third-party data — gitignore them with a fetch
  script, never commit them (the parent's no-third-party-material
  practice).
- Adopt the parent repo's culture: pin everything in a regression
  suite from day one; the passing suite pins mechanical behavior, not
  "the emulator works" — real-listing acceptance is the bar.
- Acceptance corpus: the parent's rescued listings with USR routines.
  Known today: Space Chase (80 Micro 5/1982; sound-only USR — should
  run with sound silently swallowed) and ENDGAME/BAS (80 Micro 5/1985;
  SCAN3 keyboard routine is load-bearing — possibly Stage 1 now that
  the matrix is live; Phase A settles it). Phase A's classification
  grows this list from the corpus.
- Regression contract with the parent: t1-t24 transcripts exit 0 and
  t7's RND line is the only run-to-run variance; batch mode exit codes
  unchanged; a new t25+ transcript for coprocess USR (with the
  fallback path tested by pointing the interpreter at a missing
  python3).

## The gate (do not start the CORE without it)

Count rescued listings blocked on USR before building Stage 1 — now
operationalized as PHASE A (the disassembler/classifier), which is
in-gate work: it is measurement, not emulator. As of 2026-08-07 the
honest count was ~2 (Space Chase plays stubbed; endgame can't run). As
of 2026-08-13 the parent's stub re-scan moved 90 usr/def files (80 ran
clean — some unknown fraction have load-bearing USR results that only
play-testing or Phase A can flag) and re-filed the deep-ML pile:
varptr 359, raw-bytes-in-code 135, inp 54, system 7. The gate question
is now "how many of these does Stage 1 (+VARPTR, parent-side — the
VARPTR half shipped 2026-08-14) actually unlock" — Phase A's output IS
the gate decision input. This is the
estimating twin of the parent's standing lesson: "measure the
refutation before shipping a plausible heuristic" — here, count the
unlocked programs before building the emulator.

## Decisions

RULED 2026-08-13:
1. LANGUAGE: Python 3 (see "Language and the runtime seam").
2. SHIP LOCATION: the core lives HERE; the parent gains only the awk
   coprocess plumbing + stub fallback. src/p95_z80.awk is dead.
3. NAME: renamed awk_Z80_core -> trs80_z80_core (no remote existed;
   rename was free).
4. TEST VECTORS: fetch-script + gitignore, never committed.
5. REUSABLE SEAMS: core = pure library, one declarative opcode table,
   caller-owned run loop — assembler and standalone execution are
   anticipated consumers, NOT built until asked (see "Architecture:
   the reusable seams").

STILL OPEN (decide when work starts):
1. LICENSE: parent is GPLv3 (c) 2026 David Forbis; mirroring it here is
   the default assumption. No LICENSE file until code exists.
2. R register: the parent's authentic-RND roadmap item reads R for
   seeding (RANDOM at 01D3H). Emulating R crudely (increment per
   instruction) lets the two items share it. Low stakes.
3. Coprocess protocol details (framing, delta-vs-full memory sync,
   instruction budget size): design with the plumbing, not before.

## Standing practices inherited from the parent repo

- Measure before shipping; findings documents with numbered findings;
  every increment committed and green on a written regression bar.
- Commit messages via `git commit -F <file>` (not heredocs); absolute
  paths in shell commands.
- No third-party copyrighted material in the repo (the parent keeps its
  scan corpus in a local-only sibling git repo — the same pattern
  applies to ROM-derived material and the downloaded test-vector
  suites here).
