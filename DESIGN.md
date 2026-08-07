# DESIGN — Z80 core for USR calls from BASIC

Agreed with the user 2026-08-07 (conversation in the parent repo's
session; summarized in ../awk_BASIC_interpreter/STATUS.md under
"Machine-language call support"). This document is the authoritative
context for starting the work.

## Goal and non-goals

GOAL: unmodified rescued BASIC listings that load short Z80 routines via
DATA/POKE and call them with USR(n) should run — the routine executes
against the interpreter's memory model and returns to BASIC.

NON-GOALS, standing:
- Standalone machine-language programs (SYSTEM tapes as primary
  program). That is full-emulator territory; trs80gp/sdltrs exist. Our
  niche is "runs your OCR-rescued BASIC listing directly".
- Cycle-accurate timing. Sound routines (cycle-counted OUT loops) get
  "returns promptly, silent" semantics — pitch requires cycle accuracy.
- Interrupts, R-register-based timing, undocumented-opcode exotica in
  v1 (document what real listings demand; measure first).
- SHIPPING ROM BYTES — never. The Level II ROM is copyrighted. All ROM
  services are high-level traps (HLE) reimplemented from documented
  behavior (same legal footing as the interpreter itself and the RND
  LCG research: behavior reimplementation from documentation is fine,
  verbatim code/bytes are not).

## The staged plan

STAGE 0 lives in the PARENT repo, not here (interpreter features, no
Z80): (a) memory-mapped keyboard matrix for PEEK (3800H-38FFH), which
unlocks pure-BASIC real-time games with zero emulation; (b) the
hour-sized USR parse-and-stub. Also adjacent but parent-owned: string
packing / VARPTR (mem[]-backed string storage) and program-memory
mapping. See the parent STATUS.md roadmap for all four.

STAGE 1 (this repo's first milestone): the Z80 core + minimal USR
plumbing.
- Core: full documented instruction set (~700 opcodes incl. CB/DD/ED/FD
  prefixes), registers, flags (mind half-carry and DAA — the classic
  correctness traps), 64K address space backed by the interpreter's
  mem[] (default 255 = absent-RAM reads, already authentic).
- USR interface: entry address from the USR vector at 408EH/408FH
  (dec 16526/16527, the classic POKE pair); DEFUSR support arrives with
  the parent repo's Disk BASIC tier.
- Two ROM traps only: 0A7FH (fetch the USR integer argument into HL)
  and 0A9AH (return HL to BASIC as the function result).
- Exit: RET with the entry-call's return address = done.
- This alone runs pure-computation routines (sorts, memory fills) and
  fast-video routines (writes to 3C00H-3FFFH land in the interpreter's
  SCR and RENDER — the mapping already exists).

STAGE 2: the HLE trap table, grown CORPUS-DRIVEN (the basclean
methodology): implement a ROM entry point only when a measured real
listing calls it. Known first candidates (from Microsoft BASIC Decoded
and the Paay ROM reference): 002BH keyboard scan-once, 0049H wait-key,
0033H character-to-display, 003BH character-to-printer (likely
refuse/no-op), 0060H delay. Start Z80_FINDINGS.md on the first real
listing, findings-numbered like basclean's.

## Technical reference (verified in the 2026-08-07 session)

- Model I CPU: Z80 @ 1.77 MHz (~440K instr/s effective). A gawk
  dispatch loop plausibly matches or beats this — "emulation at
  hardware speed"; the parent's `speed` throttle can slow it.
- Memory map (all already meaningful in the interpreter's mem[]):
  3800H-38FFH keyboard matrix (dec 14336-14591; PEEK(14400) = the
  arrow/space row) — Stage 0 makes reads live; the core inherits it.
  3C00H-3FFFH video (dec 15360-16383) — mapped to SCR, renders.
  40A4H program-start pointer, 408EH/408FH USR vector, 42E9H program
  text base (relevant only to the parent's program-mapping item).
- Port FFH (the only port real listings meaningfully touch): bits 0-1
  cassette output levels (the sound trick — alternate 1/2 for a square
  wave through an external amp), bit 3 = 32-column video mode (pairs
  with the parent's CHR$(23) roadmap item). OUT elsewhere: no-op or
  error, decide from corpus evidence.
- USR call convention (Level II): X=USR(n) jumps to the vector address;
  the routine may CALL 0A7FH to get n in HL, computes, optionally loads
  HL and JPs/CALLs 0A9AH to return a value; plain RET returns without
  one.

## Testing strategy

- The core is exquisitely testable BEFORE any TRS-80 semantics: the
  per-instruction JSON test-vector suites (Tom Harte / jsmoo
  single-step tests) validate each opcode against thousands of
  pre/post-state pairs; the classic ZEXDOC/ZEXALL exercisers are the
  integration-level check (need a tiny CP/M-BDOS print trap to run).
  Adopt the parent repo's culture: pin everything in a regression
  suite from day one; the passing suite pins mechanical behavior, not
  "the emulator works" — real-listing acceptance is the bar.
- Acceptance corpus: the parent's rescued listings with USR routines.
  Known today: Space Chase (80 Micro 5/1982; sound-only USR — should
  run with sound silently swallowed) and ENDGAME/BAS (80 Micro 5/1985;
  SCAN3 keyboard routine is load-bearing — the real Stage 2 test).
- Regression contract with the parent: t1-t17 transcripts byte
  identical; batch mode exit codes unchanged; a new t18+ for USR.

## The gate (do not start without it)

Count rescued listings blocked on USR before building Stage 1. As of
2026-08-07 the honest count is ~2 (Space Chase plays stubbed; endgame
can't run). The parent's vision-intake pipeline grows the corpus; the
count is the trigger. This is the estimating twin of the parent's
standing lesson: "measure the refutation before shipping a plausible
heuristic" — here, count the unlocked programs before building the
emulator.

## Open decisions (decide when work starts)

1. SHIP LOCATION: the core probably ships INTO the parent's single-file
   deliverable as src/p95_z80.awk (cat-concatenated like every module),
   with this repo holding development artifacts, tests, and findings —
   mirroring how basclean lives in tools/. Alternative: fully separate
   awk library. The parent's "single gawk script" identity argues for
   the module.
2. LICENSE: parent is GPLv3 (c) 2026 David Forbis; mirroring it here is
   the default assumption. No LICENSE file until code exists.
3. R register: the parent's authentic-RND roadmap item reads R for
   seeding (RANDOM at 01D3H). If the core emulates R (even crudely:
   increment per instruction), the two items can share it. Low stakes.
4. Naming: "awk_Z80_core" chosen 2026-08-07; rename is cheap until
   there's a remote.

## Standing practices inherited from the parent repo

- Measure before shipping; findings documents with numbered findings;
  every increment committed and green on a written regression bar.
- Commit messages via `git commit -F <file>` (not heredocs); absolute
  paths in shell commands.
- No third-party copyrighted material in the repo (the parent keeps its
  scan corpus in a local-only sibling git repo — the same pattern
  applies if test material here ever needs it).
