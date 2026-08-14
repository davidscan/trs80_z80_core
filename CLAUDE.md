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
- NEVER commit ROM bytes, ROM disassembly text, or verbatim code from
  ROM-derived repositories. HLE traps are reimplemented from documented
  behavior only. (Same rule that kept the parent repo releasable.)
  The downloaded JSON test-vector suites are also never committed:
  fetch script + gitignore.
- Parent-owned items (string packing/VARPTR, program-memory mapping)
  stay in the PARENT repo — do not build them here. (Keyboard-matrix
  PEEK and the USR stub already shipped there, 2026-08-13.)
- The parent's regression bar is part of THIS project's bar: any change
  that touches the interpreter must leave t1-t24 exiting 0 (t7's RND
  line varies run to run) and batch exit codes unchanged; the coprocess
  fallback path (no python3) must behave exactly like the shipped stub.
- Commit with `git commit -F <msgfile>`; use absolute paths in shell
  commands; every increment committed and green before the next.
- This repo is LOCAL-ONLY as created (no remote). Ask the user before
  creating a GitHub remote or pushing anywhere.
