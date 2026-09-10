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

ORIGINAL GOAL (2026-08-07), and still goal (1) of four: unmodified
rescued BASIC listings that load short Z80 routines via DATA/POKE and
call them with USR(n) should run — the routine executes against the
interpreter's memory model and returns to BASIC.

RE-FOUNDED 2026-08-14. The gate measured the rescue payoff at 6
listings and the user ruled that the count does not justify the core
and no longer has to: the project is wanted for its own sake. Read the
rest of this document with FOUR goals in the user's priority order, not
one — the sections below were largely written when only the first
existed, so where they say "the goal" they mean goal (1):
  (1) run BASIC programs containing embedded machine code — string
      packing, DATA/POKE loaders, USR. The core plus a thin bridge.
      ACTIVE WORK as of 2026-09-07; the user calls it the highest
      bang-for-the-buck piece.
  (2) extract assembly listings from magazines and run them (likely an
      OCR revisit).
  (3) write new assembly, "for the joy of it" — needs the assembler.
  (4) disassemble, e.g. machine code embedded in BASIC — mostly built.
Goals (2)-(4) do not route through BASIC at all, which is why the core
is a pure library with the coprocess plumbing kept separate (see
"Architecture: the reusable seams").

NON-GOALS, standing:
- Standalone machine-language programs (SYSTEM tapes as primary
  program). That is full-emulator territory; trs80gp/sdltrs exist. Our
  niche is "runs your OCR-rescued BASIC listing directly".
  CLARIFIED 2026-08-13 (user): this is a BUILD boundary, not an
  architecture boundary — an assembler and full machine-code execution
  are ANTICIPATED FUTURE CONSUMERS of this core, and the architecture
  keeps those seams open at zero cost (see "Architecture: the reusable
  seams"). Nothing beyond the seams is built until asked.
  UPDATED 2026-08-14 by the re-founding, one day later: goals (2) and
  (3) ARE the asking. Standalone execution is no longer hypothetical —
  it is stated, unscheduled work, so read this bullet as build ORDER
  ("not yet"), never as a prohibition.
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
language for the whole ML toolchain. Speed is a non-issue: table-driven
CPython does millions of instructions per second against a real-Model-I
target in the low hundreds of thousands.
FIGURE CORRECTED 2026-09-09 (FINDING 24 section 7): this sentence used
to put the real Model I at "~440K instr/s", which implies ~4 T-states an
instruction — true only for the simplest register ops. The table's own
cycle column gives a mean of 10.8 T-states over the documented set, so
**~164K instr/s** on a general mix, and 5.67 T-states / **313K instr/s**
on the north-star payload's actual mix. The claim's direction survives
and its margin widens, but one caveat is now measured rather than
assumed: a PRE-DECODED dispatch reaches ~5.5M insn/s with full flag
computation (~17x the bar), while re-decoding per instruction through
`z80/disasm.py` reaches only 724K insn/s (2.3x) — so the execution
decoder must not be the disassembler's decode path.

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
- Core: full documented instruction set (the "~700 opcodes" of the
  2026-08-07 estimate; the built table expands to 1780 encodings —
  1033 documented, 747 undocumented — incl. CB/DD/ED/FD prefixes),
  registers, flags (mind half-carry and DAA — the classic
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

## Technical reference — verified 2026-08-07, cross-checked 2026-09-06 against the scanned reference library

CROSS-CHECK RESULT (2026-09-06, against ROM Routines Documented, the
Micro-80 Level II ROM Reference Manual, the Tab Books Level II ROMs and
Farvour — three or four books per address): every address named in this
section and in the Stage 2 caller list above is CORROBORATED — 0A7FH,
0A9AH, 408EH, 40A4H, 42E9H, 37E8H, 002BH, 0033H, 0028H, 0049H, 003BH,
0060H, 01D3H. Two things changed, both recorded where they belong: the
1BC0H "undocumented" claim (Stage 2 list, above) and the CINT semantics
of 0A7FH (Stage 1 traps, above).

The books could not validate the opcode table's cycle column
WHOLESALE — the OCR'd Zilog/Reston/Leventhal instruction tables yield
0-1 parseable rows each — but one book states a RULE that does the job
for part of it. The Nano Systems reference card (1981) gives the
index-half instructions as "the corresponding H or L instruction plus 4
T-states", and all 92 of ours satisfy it exactly (Z80_FINDINGS FINDING
21, pinned in tests/test_table.py). So 92 entries now have an external
check and the other 1688 do not; the column stays "carried but largely
unvalidated" until the core runs the pinned single-step vectors.

- Model I CPU: Z80 @ **1,774,080 T-states/s**. Effective instruction
  rate depends entirely on the mix: ~164K instr/s at the table's
  documented-set mean of 10.8 T-states, ~313K instr/s on the north-star
  payload's measured mean of 5.67 (FINDING 24 section 7). The "~440K
  instr/s effective" this line used to carry was corrected 2026-09-09;
  quote T-states and the mix, never a single instruction rate. The
  interpreter's `speed` throttle can slow replay toward authentic feel.
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

## The address space — how much room assembly actually gets (2026-09-07)

Asked in the goal-(1) discussion: the interpreter is not bound by real
hardware and has effectively unlimited room for BASIC programs, so how
does assembly benefit, and what is the largest space we can address?

**64 KB, hard, and no interpreter generosity changes it.** The Z80
address bus is 16 bits. A core that addresses more than 65,536 bytes is
not a Z80, and goals (2) and (4) — run magazine assembly listings,
disassemble real embedded code — depend on it being one. This is an
architectural fact being adopted as an invariant, not a budget.

WHAT THE 64K HOLDS on a Model I Level II, and therefore here:

| range | size | what it is |
|---|---|---|
| 0000-2FFF | 12K | Level II ROM — NOT present here (see below) |
| 3000-37FF | 2K | mostly unused; 37E8-37E9 printer status |
| 3800-38FF | 256B | keyboard matrix — LIVE, callback per read |
| 3900-3BFF | 768B | keyboard mirrors |
| 3C00-3FFF | 1K | video RAM — LIVE, writes render |
| 4000-41FF | 512B | RAM communication region / system variables |
| 4200-FFFF | ~47K | RAM: BASIC program, variables, strings, stack, ML |

A fully expanded 48K Model I has RAM from 4000H to FFFFH: **49,152
bytes**. That is the ceiling, we can offer all of it, and offering all
of it costs nothing — so the answer to "the largest addressable space"
is 64K total, 48K of it usable RAM.

**THE ASYMMETRY THE QUESTION SENSED IS REAL, AND IT FAVOURS ASSEMBLY —
just not by enlarging the address space.** BASIC program text,
variables and strings live in the interpreter's own awk data
structures, not inside a simulated 64K. So they do not COMPETE for
address space. On a real 48K machine a large BASIC program left only
scraps for machine code, and MEMORY SIZE existed to fight over the
boundary; here the address space is very nearly all available to
machine code and its data, whatever the size of the BASIC program
driving it. Assembly gets more usable room than the real machine ever
offered, without the address space growing by one byte.

WHAT IS PROJECTED INTO THE 64K (everything else is the core's own RAM):
keyboard 3800-38FF and video 3C00-3FFF as live device callbacks;
37E8-37E9 printer status; the READ-ONLY tokenized program image at
42E9H; string bytes reachable through VARPTR, write-through. Numeric
and array VARPTR do NOT materialise as contiguous memory (see the
VARPTR paragraph above) — that is a known hole, not a plan.

TWO CONSEQUENCES WORTH STATING PLAINLY, BOTH ALREADY IMPLIED BY
STANDING RULES:

1. **ROM is not there.** We never commit ROM bytes, so 0000-2FFF holds
   no data. Documented entry points are HLE traps, which serves code
   that CALLS the ROM. It does not serve code that READS the ROM — the
   character generator, the trig and constant tables, anything that
   PEEKs below 3000H for its contents. That bounds what "runs a
   magazine listing" can mean, and the bound is a licensing choice we
   have already made deliberately.
2. **A BASIC program can outgrow the window that shows it.** Program
   text is unbounded interpreter-side but the image mapped at 42E9H is
   inside a 16-bit space. What happens to a program too large to map —
   truncate the window and say so, refuse and report, or map a
   sliding window — is UNDECIDED. It is a live question for goal (1)
   because FINDING 19's Dancing Demon payload lives inside the program
   image itself, at 42F6H.

THE INVARIANT, stated so downstream questions settle themselves
(user's framing, 2026-09-07): **the 16-bit space is a faithful Model I,
and none of the interpreter's generosity leaks into it.** The 64K is a
WINDOW the interpreter projects, not the place BASIC's data lives.
BASIC's storage is unbounded and sits outside; the interpreter
materialises into the window only what Z80 code must be able to see,
and it owns that projection policy entirely.

The user proposed inverting the machine-accurate layout — start BASIC's
mapping at 64K and leave everything below it TRS-80-accurate. That IS
the architecture, arrived at independently, and it is already what
happens: variables and the stack are awk structures, not addresses.
ONE BOUNDARY THE INVERSION CANNOT CROSS, and it is the Z80's, not
ours: anything BASIC must HAND to machine code needs a 16-bit address.
VARPTR cannot return 65536; the USR vector at 408EH/408FH is two bytes.
So the windows — VARPTR'd strings and numerics, the program image at
42E9H, video, keyboard — stay inside the space by necessity. Everything
else is free to live outside it, and does.

Consequences that follow from the invariant without further argument:
report a definite machine size (48K, RAMTOP FFFFH) and never "unlimited",
because listings compute load addresses from PEEK(16561/16562); do not
widen the address bus; do not let the size of a BASIC program change
what Z80 code sees; and when something cannot fit the window, FAIL
LOUDLY rather than silently show the wrong bytes — a sliding program-
image window is the tempting answer and the dangerous one, because Z80
code walking the image with HL would read wrong bytes with no error.

WHERE MACHINE CODE AND BASIC MEET, AND WHY THEY DO NOT COLLIDE
(verified 2026-09-07 by reading trs80basic; FINDING 22). The
separation is NOT bank switching and does not need it. BASIC's
variables and stack are outside the 64K, so they cannot grow into
machine code — that is free. STRING PACKING IS THE DELIBERATE
EXCEPTION: the idiom puts the routine inside a BASIC string, so those
bytes must be projected into the address space for VARPTR to locate
and the core to execute. The interpreter already does this the way the
real machine did — string space descends from the MEMORY SIZE ceiling
(HIMEM) toward the 42E9H program text, `?OM` on collision — so
answering MEMORY SIZE lower really does free the region above, and
`PEEK(16561/16562)` reports the ceiling so listings can compute a load
address from it. MEMORY SIZE is therefore NOT vestigial here: it is
the live mechanism that keeps packed strings clear of poked code.
A DEFECT SITS IN THE OTHER HALF (FINDING 22): the interpreter treats
everything above HIMEM as ABSENT rather than PROTECTED, so POKEs into
the reserved region are discarded. Harmless until a core executes
them. Interpreter-owned, reported not built.

THE "EVERYTHING EARLY" PATTERN — the model that does work, and the
period convention behind it (user recollection, MEASURED 2026-09-07).

The user recalled that period programs did all their string packing at
the very start, and proposed generalising it: assign packed strings
early where they are addressable, and place embedded code early in the
program, jumping around it. That is right, it is what the north-star
program does, and it survives an 800K program where every other model
fails.

WHY THE CONVENTION EXISTED ON HARDWARE. In Microsoft BASIC a string
assigned directly from a LITERAL is not copied into string space — the
descriptor points INTO THE PROGRAM TEXT where the literal sits. So
packing early put the bytes at a low, predictable, stable address near
42E9H. It also kept them still: string space is collected, and a packed
string whose VARPTR you have already handed to DEF USR must not move.

MEASURED HERE (probe at 17129, identical output for a 350-byte program
and an 850 KB one):

  42E9H: F4 42 | 01 00 | 8D 20 "9000" 00      line 1, GOTO 9000
  42F4H: 0B 43 | 02 00 | 93 20 5A 5A 5A ...   line 2, REM + payload

The early payload sits at ~42FAH and reads back identically at both
sizes. `VARPTR(B$)` returned 65533 in both, with the packed bytes just
below it. **So both halves of the pattern are size-independent.**

TWO REFINEMENTS TO THE RECOLLECTION:

1. You do not GOTO/GOSUB INTO the machine code — BASIC cannot execute
   it. The jump goes OVER it and the code is entered through USR. That
   is exactly Dancing Demon's `1 GOTO 259` with the payload in fake
   BASIC lines 2..258 (FINDING 19).
2. For STRINGS the convention is unnecessary here, though harmless. The
   interpreter DEVIATES from hardware — p75: "the bytes are a mem[]-
   backed COPY (a literal's bytes are not the program line)" — and
   materialises near HIMEM wherever the assignment appears. That
   deviation is precisely what makes string packing immune to program
   size: on real hardware a literal 600K into an 800K program would sit
   at 617,129 and be unaddressable, which is the failure the user was
   reaching for. Here it cannot happen.

WHY THIS MATTERS BEYOND STYLE: the pattern SIDESTEPS FINDING 23
entirely, because it never POKEs. Measured contrast — a DATA/POKE
loader breaks once the image passes the loader's target (~15 KB for a
routine at 32000); a payload placed early IN the image works at 850 KB.
For goal (1) this is the robust shape, and it is what the acceptance
case already uses.

THREE CAVEATS, so the pattern is not oversold:
- The program image is READ-ONLY, so this executes an embedded payload
  but does not let it modify itself (p75, writable mapping unbuilt).
- The 16-bit next-line links wrap past FFFFH (`% 65536` in pm_build), so
  code that walks the line-record chain — which is how a payload in the
  image is located — is only safe while it stays under 64K. Another
  reason "early" is load-bearing rather than tidy.
- Pack-then-SAVE captures nothing here, because the bytes are a copy
  rather than the program line. On hardware that workflow worked, and
  it was a real period technique; anyone writing NEW packed programs
  (goal 3) needs to know it does not survive here.

CAN A TRANSLATION TABLE REACH PAST 64K? No, and the reason is worth
recording because the question recurs (user, 2026-09-07: machine code
sitting 600K into an 800K program — "any jumps/branches in the embedded
code wouldn't be resolvable").

The obstacle is not resolution, it is REPRESENTATION. `JP nn`, `CALL
nn` and `LD HL,nn` carry a 16-bit operand field. There is no encoding
of any Z80 instruction that names address 617,129, so no table the
interpreter keeps can help: the translated address would have to live
inside the instruction, and there is no room for it. A pointer table
solves VISIBILITY — which bytes the window shows — and cannot solve
ADDRESSABILITY. Those are different problems and only the first is ours
to solve.

THE MECHANISM THAT DOES WORK IS RELOCATION, not translation: copy the
routine into the 16-bit window and run it there. That is already what
a DATA/POKE loader does. Its limit is that relocation is only safe for
POSITION-INDEPENDENT code, and real routines mostly are not — which is
why the intended load address matters and why every loader idiom names
one (`FOR I=32000`, `DEF USR=`, the 408EH vector).
WORKED EXAMPLE, REPLACED 2026-09-09 (FINDING 24 section 9). This passage
used to argue from Dancing Demon that a 10,931-byte routine "necessarily
contains absolute JP/CALL into its own body, and therefore must load
where it was assembled to load". The premise — `JR` and `DJNZ` reach
only +/-127 bytes — is true; the inference is FALSE, and the measurement
inverts it. Over the whole payload by linear sweep: **0 absolute CALLs
into its own body, 0 internal JPs, 3 distinct CALL targets in 10,931
bytes** (01C9H, 4018H, 4028H), with internal control flow `JR` x365 and
`DJNZ` x22. It is not connected by relative jumps ALONE; it is connected
by relative jumps PLUS A DISPATCHER, and the BASIC line-record chain it
walks is a run-time relocation table. So the demon is a 10.9 KB FULLY
POSITION-INDEPENDENT payload — the demonstration that a routine that size
need NOT name an address inside itself. The general claim it was cited
for still stands (relocation is only safe for position-independent code,
and most real routines are not), but this program is the exception, not
the illustration of the rule.

SO THE 600K CASE DOES NOT ARISE FOR GOAL (1), and that is not a dodge:
every rescued listing fits 48K by construction, because the machine it
was written for could not hold more. A program with executable code at
offset 600K is NEW work, not a rescued listing — goal (3) — and there
the binding constraint is the Z80 itself, not the interpreter. Code
that needs to be addressed above FFFFH is not Z80 code.

SELF-MODIFYING CODE, specifically: at a notional 617,129 it cannot
address itself at all, by the same 16-bit argument. And note a gap that
holds regardless of size — the program image is READ-ONLY today
("POKEs into the region land in MEM and are never read back — the
WRITABLE mapping (self-modifying code) stays unbuilt", p75 header), so
self-modifying code inside the program image is unsupported now.
CORRECTION 2026-09-09 (FINDING 24 section 4): this passage used to add
"That sits on the north-star path, since the Dancing Demon payload lives
in the image rather than in a loader." It does NOT. The demon's payload
lives in the image but never writes to it — every real absolute write
goes to system RAM (4019H-402BH, 4100H), and its self-modification
target is the 4018H/4028H trampoline. Measured, not reasoned, and it
confirms the answer already given to trs80basic in
`handoff/to-trs80basic.md`. The read-only image gap is real and remains
unbuilt; it is simply not on the north-star path.

WHAT ACTUALLY DESERVES THE ATTENTION is not 800K but ~15K: FINDING 23
measures ordinary programs silently breaking POKE loaders once the
image grows past the loader's target address. The impossible case is
easy to rule out; the ordinary one is already happening.

IF 64K EVER BINDS, the only historically honest extension is **bank
switching**, a port-selected bank register (the Model 4 reached 128K
this way), which keeps the Z80 at 16 bits so the table, the
disassembler and the assembler go on describing real hardware.
But note what it is NOT: banking does not give machine code a separate
non-colliding space — it MULTIPLEXES the same 16-bit window, so an
address means different things depending on a port, and both VARPTR
addresses and MEMORY-SIZE-reserved addresses stop being meaningful on
their own. Every listing in the corpus assumes a flat 64K, so banking
is actively hostile to goal (1) and could only ever serve goal (3),
where we control both sides of the code. Widening the address bus is
rejected outright: it would make the assembler emit code no Z80 could
run and the disassembler mis-describe the listings goals (2) and (4)
exist to read. Neither is scheduled; recorded so the question is not
reopened from scratch.

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
- North-star for the coprocess (Z80_FINDINGS FINDING 19, 2026-09-02;
  RE-MEASURED AND CORRECTED BY FINDING 24, 2026-09-09):
  "silent Dancing Demon dances". Its 10.9 KB payload lives inside the
  tokenized program image, writes video DURING the USR call, and polls
  the keyboard matrix — so it needs streamed video writes, live key
  state, and cycle pacing. Call-and-return USR (memory in, run, memory
  out) is not enough for that class of program; the protocol has to
  decide this.
  CORRECTION 2026-09-09: this bullet used to end "and calls no ROM ...
  and NOT ROM emulation". It calls ONE — `CALL 01C9H` (CLS) x4, a
  documented Level II entry point, so HLE-trappable but not absent.
  The payload is also not a routine but a SELF-RELOCATING DISPATCHER
  that patches a JP trampoline into 4018H/4028H and finds its 106
  subroutines by walking the BASIC line-record chain, which is what
  makes correct next-line links and a writable, executable 4000-41FF
  hard requirements. Work items: `DANCING_DEMON.md`.
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

## The gate — CLOSED 2026-08-14, kept as the measurement record

(The heading read "do not start the CORE without it" until 2026-09-07.
That instruction was discharged on 2026-08-14 and the imperative was
left standing in the navigation layer, which is the exact hazard this
document keeps warning about. The name "The gate" is unchanged so
CLAUDE.md's reference still resolves.)

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
   still DEFERRED as of 2026-09-07: the big-picture talk that had held
   it was CLOSED that day, but the user's direction is to settle goal
   (1)'s shape first — "we don't need to talk about detailed
   handshaking yet". No handshake/protocol code before that. Nothing of
   this is built.

## Standing practices inherited from the companion repos

- Measure before shipping; findings documents with numbered findings;
  every increment committed and green on a written regression bar.
- Commit messages via `git commit -F <file>` (not heredocs); absolute
  paths in shell commands.
- No third-party copyrighted material in the repo (awk_BASIC_interpreter
  keeps its scan corpus in a local-only sibling git repo — the same pattern
  applies to ROM-derived material and the downloaded test-vector
  suites here).
