# CLAUDE.md — session bootstrap for trs80_z80_core

You are in the planning space for a Z80 core in PYTHON 3 that will give
the TRS-80 LEVEL II BASIC interpreter (../trs80basic) the
ability to execute machine-language routines called from BASIC via USR.
It attaches to the awk interpreter as a persistent coprocess with a
stub fallback (language and seam RULED 2026-08-13 — see DESIGN.md).

READ ORDER on a fresh session (local files only — cross-repo pointers rot,
so they live in COMPANION REPOS below and are not part of the read order):
1. README.md (one screen: what and why)
2. Z80_FINDINGS.md — start at "THE GATE NUMBER"; 20 numbered findings
3. DESIGN.md (the authoritative context: language/seam ruling, staged
   plan incl. Phase A, technical reference, testing strategy, the gate,
   decisions)

COMPANION REPOS — this is an INDEPENDENT project with two peers, not a
sub-project of either. Neither is a "parent".
- `../trs80basic` — the TRS-80 LEVEL II BASIC interpreter this core attaches
  to. Integration shape ratified 2026-09-04: COMPANION ENGINE, NEVER
  VENDORED — a p77 shim in trs80basic, `TRS80_Z80` discovery, releases may
  bundle. NOT BUILT YET: as of 2026-09-04 there is no p77 shim and no
  `TRS80_Z80` reference in its `src/`. Its working notes are
  `STATUS.local.md` there (gitignored — exists only in a local checkout),
  which holds the coordination entries "Machine-language call support" and
  "Program-memory mapping".
- `../awk_BASIC_interpreter` — the private CORPUS ARCHIVE, measurement data
  only (`programs/`, `programs/runnable/`, `OCRsamples/`, `blocked/`). It
  is NOT the interpreter any more; that moved to trs80basic on 2026-08-28.

REFERENCE LIBRARY (assembled 2026-09-05 — scanned books, not code; local
only, never committed): `../trs80_references/trs80_z80_core/` holds the 21
PDFs selected for this project after a table-of-contents scan of all 76
documents in `../trs80_references/`; its `goal2/` subdirectory holds 16
more for goal (2), magazine listings (the ten Wayne Green Encyclopedia
volumes, Barden's subroutine book, the Richcraft Disassembled Handbooks,
Custom TRS-80, TRS-80 Graphics). Which to reach for:
- HLE trap semantics (documented behaviour only): ROM Routines Documented
  (has the Model I vs III entry-point comparison), the Micro-80 Level II
  ROM Reference Manual (text layer), Farvour "Microsoft BASIC Decoded"
  chapters 2 and 4 ONLY — its chapters 7-8 are commented ROM disassembly
  and fall under the NEVER-commit rule, as do Richcraft volumes 1-2.
- Opcode table / T-state cross-checks: the Zilog Z80 CPU Technical Manual
  (two scans of one book), Leventhal, the Reston Z80 Users Manual, Osborne
  "Z80 Programming for Logic Design"; the Nano Systems reference card
  lists the undocumented IX/IY half-register instructions.
- Loader idioms the extractor classifies (string packing, DATA/POKE, array
  packing, USR argument passing): Level II ROMs (Tab) ch. 2-3, Barden
  "More TRS-80 Assembly-Language Programming" ch. 4-5, Fast BASIC part II
  (the five BASIC tables, VARPTR).
- Model I address-space side effects (3800H keyboard, 3C00H video, port
  FFH): the 1978 TRS-80 Technical Manual; Assembly Language Made Simple
  ch. 4 for the memory map.
The user reorganises that tree themselves (BASIC-side books sit in
`../trs80_references/trs80basic/`, parked items in "Future reference"), so
search the whole tree before assuming a file's location.

WHERE THINGS STAND (audited 2026-09-04 against the companion repos, a
sweep re-run, and the session records; the 2026-08-14 handoff had
missed two same-day events, recorded below)
- THE GATE IS RULED. Measured to completion 2026-08-14: gate number
  **6** (Phase A 5; the oracle added varptr/engindb3.bas). The gate
  never set a numeric threshold. The user RULED the same day, in the
  companion session (recorded in awk_BASIC_interpreter's
  PROJECT_MAP.md, "set 2026-08-14"): the rescue count does not justify
  the core and no longer has to — the project is re-founded on its own
  merits. The user's words: "I do want to have a standalone
  assembler/de-assembler in addition to the in-BASIC machine code
  handling." FOUR GOALS, in the user's priority order: (1) run BASIC
  programs that contain embedded machine code — string packing,
  DATA/POKE loaders, USR — i.e. the core plus a thin optional bridge;
  (2) extract assembly-language listings from magazines and run them
  (probably an OCR revisit); (3) write new assembly, "for the joy of
  it" — needs the assembler; (4) disassemble, e.g. the code embedded in
  BASIC programs — mostly built. Stage 1 planning proceeds from these
  goals, not from the gate number.
- STAGE 1 IS NOT STARTED. No opcode-execution code and no protocol
  code exists. What gates it now is the BIG-PICTURE TALK the user asked
  for on 2026-08-14 ("I need us to step back to project-level and
  discuss big picture concepts"); protocol work is DEFERRED to that
  talk. Agenda constraints already ratified (2026-09-02): companion
  engine, never vendored; p77 shim in trs80basic; TRS80_Z80 discovery;
  releases may bundle; the first protocol message carries a version and
  a mismatch is a clean error. Do not start handshake/protocol code
  before the talk. FINDING 19 (Dancing Demon) is input to it: call-and-
  return USR is not enough for that class of program.
- THE blocked/ RE-SCAN WAS PAID 2026-08-14 (awk_BASIC_interpreter
  9ee96ca3 + 89d9269b) and verified from this side the same evening,
  but never written into this repo until now — Z80_FINDINGS FINDING 20.
  Effect: 280 files moved to runnable/, varptr/ retired, blocked/ 1065
  → 779; the FINDING 16 cmd/ confound was measured by reachability (238
  BLOCKED-RUNS-ANYWAY) rather than re-filed and contributed ZERO to the
  gate; four of the six gate files (MAIL32, MAIL48, m3t1s2d, engindb3)
  now sit in runnable/ without any of them running to completion. The
  gate reads 2 by its literal wording and 6 by its intent.
- Built and green: the 1780-entry opcode table + disassembler, the
  extractor/classifier/sweep, the dynamic oracle (phasea/oracle.py),
  and the pinned single-step vector suite (tools/fetch_vectors.py,
  1604 files fetched into the gitignored tests/vectors/). 98 tests:
  `python3 -m unittest discover -s tests`.
- WHERE THE CODE LOOKS (repointed 2026-09-04): phasea/oracle.py builds
  its scratch interpreter from ../trs80basic/src and tests/test_oracle.py
  diffs against ../trs80basic/trs80basic.awk; the sweep, the oracle and
  the anchor tests read listings from ../awk_BASIC_interpreter (corpus
  only — its duplicate src/ is scheduled for deletion there). Re-
  validated after the repoint: 22 exact / 7 patched / 16 silent / 0
  contradictions, identical to FINDING 13. Sweep re-run 2026-09-04:
  4339 listings (was 4345), 560 USR listings, 91 unresolvable loaders
  (was 96), gate population still the same 46 files, now 17 blocked /
  29 runnable (was 25 / 21). Z80_FINDINGS.md keeps the 2026-08-14
  numbers as measured; FINDING 20 carries the deltas.
- The user's own standing view, recorded so it is not relitigated: the
  two INTERPRETER-side defects the oracle found were each worth more
  listings than the core is. Both shipped 2026-08-14 (8c38dca6, in
  awk_BASIC_interpreter's history — pre-split; that code now lives in
  trs80basic and was confirmed present there 2026-09-04).
- KNOWN LATENT ISSUE, recorded not fixed (DESIGN.md decision 3): the
  interpreter's spaced-call fix dispatches `USR n(` as name `USR`,
  DISCARDING the slot digit, while `USRn(` keeps it. Harmless under the
  stub (which ignores the slot), but the coprocess call frame must carry
  the slot, so that dispatch point has to pass it through when the
  plumbing is built.
- COMPANION-SIDE STATE (2026-09-04): trs80basic/STATUS.local.md's
  "Machine-language call support" entry was rewritten the same day as a
  PEER coordination entry (integration shape, seam rules, state on this
  side, what trs80basic owns) and points back at this block as the
  authoritative state here — keep the two in step when either changes.
  Still stale, reported not edited: the archive's README.md describes
  itself as the interpreter (its own STATUS already lists deleting the
  duplicate src/ as owed).

STANDING RULES (do not relearn these the hard way):
- PHASE A BEFORE THE CORE (DESIGN.md "The gate") — SATISFIED 2026-08-14,
  kept because the discipline recurs: the first artifact was the static
  disassembler/classifier over the corpus archive's DATA/POKE loader
  bytes, and no opcode-execution code was written until its numbers
  were in and the user had ruled (see WHERE THINGS STAND). Phase A
  itself was in-gate (measurement, not emulator) — confirmed with the
  user 2026-08-13. The same rule applies to the next build: measure
  before building, and the next reviewed stop is the big-picture talk.
- ANCHORS BEFORE TRUST (Phase A discipline, ruled 2026-08-13; wording
  corrected 2026-08-14): validate before believing, in this order.
  (1) The opcode table must pass a validation set against known-good
  disassembly BEFORE any classifier output is trusted. (2) The
  classifier must be checked against the two ground-truth anchors —
  Space Chase and ENDGAME/BAS SCAN3 — and its buckets for them
  reconciled with the evidence, BEFORE its corpus-wide counts mean
  anything. A count produced without both checks passing is not a
  measurement. (The corpus project's standing lesson — plausible
  heuristics die
  under measurement — applied prophylactically.)
  NOTE, and the reason the wording changed: this rule originally said
  the classifier must bucket endgame as a KEYBOARD scan. It is not one.
  SCAN3 is the event-clock scan and is PURE COMPUTE, with no
  3800H-38FFH access anywhere (Z80_FINDINGS FINDING 2, corroborated by
  awk_BASIC_interpreter's own FINDING 29 notes and by line 1240's
  `KJ=USR 1(VARPTR(IC(1)))`). The anchor earned its keep by refuting
  its own stated expectation — so the rule is "check the anchor", never
  "make the anchor come out the way we assumed". An anchor that cannot
  be wrong is not an anchor.
  (3) Applies to any NEW measurement instrument too, not just the
  classifier: the dynamic extraction oracle was validated against the
  payloads static extraction already resolved, and had to contradict
  none of them, before its output on the unresolvable 96 counted
  (FINDING 13).
- THE GATE RULING IS A REVIEWED CHECKPOINT (DONE 2026-08-14; the
  pattern stands for the next checkpoint): Phase A ended in a findings
  document (Z80_FINDINGS.md, numbered like basclean's) plus the gate
  count, presented to the USER for the go/no-go ruling on the core.
  Do not slide from measurement into building in the same breath —
  present, stop, and let the user rule (they may bring a heavier
  review to the numbers).
- NEVER commit ROM bytes, ROM disassembly text, or verbatim code from
  ROM-derived repositories. HLE traps are reimplemented from documented
  behavior only. (Same rule that kept the interpreter repo releasable.)
  The downloaded JSON test-vector suites are also never committed:
  fetch script + gitignore.
- CHANGES TO trs80basic LAND ON A DEVELOPMENT BRANCH, NEVER main. The
  two projects interact both ways, but trs80basic's main is staged for a
  public release, so integration work (the p77 shim, the call frame
  carrying the slot digit, TRS80_Z80 discovery) goes on a development
  branch there and is merged by the user. Reporting a defect and
  offering a fix is always fine. This replaces the older "documentation
  only, ask first" rule, written 2026-08-14 when that repo was this
  project's parent and held the only copy of the interpreter. The
  incident behind it still stands as the thing to avoid: "make the
  changes in the parent" was meant as "update the docs" and was read as
  authorization to patch interpreter source.
- Interpreter-owned items (string packing/VARPTR, program-memory
  mapping) stay in trs80basic — do not build them here. (Keyboard-matrix
  PEEK and the USR stub shipped there 2026-08-13; VARPTR/string packing,
  program-memory mapping, and the FINDING 8 DEF USR parse fix shipped
  there 2026-08-14, as did the FINDING 16/17 fixes — the 400CH DOS probe
  and the USR call-site space. Note: the interpreter's VARPTR does NOT
  give integer arrays a contiguous 2-byte image — VARPTR-array loaders
  still route through the extractor; see DESIGN.md.)
- trs80basic's regression bar is part of THIS project's bar: any change
  that touches the interpreter (see the development-branch rule above)
  must leave t1-t28 exiting 0 (t7's RND line varies run to run) and
  batch exit codes unchanged; the coprocess fallback path (no python3)
  must behave exactly like the shipped stub. Baseline the transcripts
  BEFORE editing, so "unchanged" is a diff and not a belief, and keep
  the pre-change build around to tell an inherent variance apart from a
  regression.
- Commit with `git commit -F <msgfile>`; use absolute paths in shell
  commands; every increment committed and green before the next.
- Remote: private GitHub davidscan/trs80-z80-core (created 2026-08-14 at
  the user's direction; hyphenated to match the naming
  of the repo that was then the parent). KEEP IT PRIVATE — the findings quote one-line loader
  excerpts from magazine listings. No LICENSE file yet (user ruling
  2026-08-14); GPLv3 mirroring trs80basic remains the default assumption
  when one is added.
