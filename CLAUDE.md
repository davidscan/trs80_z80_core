# CLAUDE.md — session bootstrap for trs80_z80_core

You are in the planning space for a Z80 core in PYTHON 3 that will give
the TRS-80 LEVEL II BASIC interpreter (../awk_BASIC_interpreter) the
ability to execute machine-language routines called from BASIC via USR.
It attaches to the awk interpreter as a persistent coprocess with a
stub fallback (language and seam RULED 2026-08-13 — see DESIGN.md).

READ ORDER on a fresh session:
1. README.md (one screen: what and why)
2. DESIGN.md (the authoritative context: language/seam ruling, staged
   plan incl. Phase A, technical reference, testing strategy, the gate,
   decisions)
3. ../awk_BASIC_interpreter/STATUS.md — the parent's resume doc; its
   roadmap entries "Machine-language call support" and "Program-memory
   mapping" are the coordination points, and its RESUME INSTRUCTIONS
   explain the parent's build/test workflow.

STANDING RULES (do not relearn these the hard way):
- PHASE A BEFORE THE CORE (DESIGN.md "The gate"): the first artifact is
  the static disassembler/classifier over the parent corpus's DATA/POKE
  loader bytes. Do not write opcode-execution code until its numbers
  are in and the user has ruled the gate met. Phase A itself is in-gate
  (measurement, not emulator) — confirmed with the user 2026-08-13.
- ANCHORS BEFORE TRUST (Phase A discipline, ruled 2026-08-13; wording
  corrected 2026-08-14): validate before believing, in this order.
  (1) The opcode table must pass a validation set against known-good
  disassembly BEFORE any classifier output is trusted. (2) The
  classifier must be checked against the two ground-truth anchors —
  Space Chase and ENDGAME/BAS SCAN3 — and its buckets for them
  reconciled with the evidence, BEFORE its corpus-wide counts mean
  anything. A count produced without both checks passing is not a
  measurement. (Parent's standing lesson — plausible heuristics die
  under measurement — applied prophylactically.)
  NOTE, and the reason the wording changed: this rule originally said
  the classifier must bucket endgame as a KEYBOARD scan. It is not one.
  SCAN3 is the event-clock scan and is PURE COMPUTE, with no
  3800H-38FFH access anywhere (Z80_FINDINGS FINDING 2, corroborated by
  the parent's own FINDING 29 notes and by line 1240's
  `KJ=USR 1(VARPTR(IC(1)))`). The anchor earned its keep by refuting
  its own stated expectation — so the rule is "check the anchor", never
  "make the anchor come out the way we assumed". An anchor that cannot
  be wrong is not an anchor.
  (3) Applies to any NEW measurement instrument too, not just the
  classifier: the dynamic extraction oracle was validated against the
  payloads static extraction already resolved, and had to contradict
  none of them, before its output on the unresolvable 96 counted
  (FINDING 13).
- THE GATE RULING IS A REVIEWED CHECKPOINT: Phase A ends in a findings
  document (Z80_FINDINGS.md, numbered like basclean's) plus the gate
  count, presented to the USER for the go/no-go ruling on the core.
  Do not slide from measurement into Stage 1 in the same breath —
  present, stop, and let the user rule (they may bring a heavier
  review to the numbers).
- NEVER commit ROM bytes, ROM disassembly text, or verbatim code from
  ROM-derived repositories. HLE traps are reimplemented from documented
  behavior only. (Same rule that kept the parent repo releasable.)
  The downloaded JSON test-vector suites are also never committed:
  fetch script + gitignore.
- IN THE PARENT REPO, DOCUMENTATION ONLY — ASK BEFORE ANY CODE CHANGE
  (ruled 2026-08-14, after this was got wrong). From a session in THIS
  repo, edits to ../awk_BASIC_interpreter are limited by default to its
  DOCUMENTATION: STATUS.md, README.md, RELEASE_NOTES.md and the like.
  Everything else there — `src/p*.awk`, the built `trs80basic.awk`,
  `programs/tests/t*.txt`, the launcher, the corpus — is CODE, and
  changing it needs the user's EXPLICIT permission for that specific
  change. If the permission is not 100% clear, STOP AND ASK before
  making the change, not after.
  Do NOT infer permission from: a measured defect owed to the parent's
  queue, a fix being obviously correct or one line long, a general
  "go ahead", or an instruction to "make the changes in the parent" —
  that last phrasing was meant as "update the parent's docs" on
  2026-08-14 and was read as authorization to patch its source. The
  two fixes made that day (FINDINGS 16/17, parent 8c38dca6) were KEPT
  by the user's ruling — do not revert them — but the standing rule is
  ask first.
  Reporting a parent-side defect and offering to fix it is always fine;
  writing the fix without a clear yes is not.
- Parent-owned items (string packing/VARPTR, program-memory mapping)
  stay in the PARENT repo — do not build them here. (Keyboard-matrix
  PEEK and the USR stub shipped there 2026-08-13; VARPTR/string
  packing, program-memory mapping, and the FINDING 8 DEF USR parse fix
  shipped there 2026-08-14, as did the FINDING 16/17 fixes — the 400CH
  DOS probe and the USR call-site space. Note: parent VARPTR does NOT
  give integer arrays a contiguous 2-byte image — VARPTR-array loaders
  still route through the extractor; see DESIGN.md.)
- The parent's regression bar is part of THIS project's bar: any
  AUTHORIZED change that touches the interpreter (see the ask-first
  rule above) must leave t1-t28 exiting 0 (t7's RND line varies run to
  run) and batch exit codes unchanged; the coprocess fallback path (no
  python3) must behave exactly like the shipped stub. Baseline the
  transcripts BEFORE editing, so "unchanged" is a diff and not a
  belief, and keep the pre-change build around to tell an inherent
  variance apart from a regression.
- Commit with `git commit -F <msgfile>`; use absolute paths in shell
  commands; every increment committed and green before the next.
- Remote: private GitHub davidscan/trs80-z80-core (created 2026-08-14
  at the user's direction; hyphenated to match the parent's naming).
  KEEP IT PRIVATE — the findings quote one-line loader excerpts from
  magazine listings. No LICENSE file yet (user ruling 2026-08-14);
  GPLv3 mirroring the parent remains the default assumption when one
  is added.
