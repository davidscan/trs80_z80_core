# CLAUDE.md — session bootstrap for awk_Z80_core

You are in the planning space for a Z80 core in GNU awk that will give
the TRS-80 LEVEL II BASIC interpreter (../awk_BASIC_interpreter) the
ability to execute machine-language routines called from BASIC via USR.

READ ORDER on a fresh session:
1. README.md (one screen: what and why)
2. DESIGN.md (the authoritative context: staged plan, technical
   reference, testing strategy, the gate, open decisions)
3. ../awk_BASIC_interpreter/STATUS.md — the parent's resume doc; its
   roadmap entries "Machine-language call support" and "Program-memory
   mapping" are the coordination points, and its RESUME INSTRUCTIONS
   explain the parent's build/test workflow.

STANDING RULES (do not relearn these the hard way):
- CHECK THE GATE FIRST (DESIGN.md "The gate"). If the measured count of
  USR-blocked rescued listings hasn't grown past ~2, the right move is
  usually Stage 0 work in the PARENT repo, not Stage 1 here. Confirm
  with the user before starting the core.
- NEVER commit ROM bytes, ROM disassembly text, or verbatim code from
  ROM-derived repositories. HLE traps are reimplemented from documented
  behavior only. (Same rule that kept the parent repo releasable.)
- Stage 0 items (keyboard-matrix PEEK, USR stub, string packing/VARPTR,
  program-memory mapping) belong to the PARENT repo — do not build them
  here.
- The parent's regression bar is part of THIS project's bar: any change
  that touches the interpreter must leave t1-t17 byte-identical (t7's
  RND line varies) and batch exit codes unchanged.
- Commit with `git commit -F <msgfile>`; use absolute paths in shell
  commands; every increment committed and green before the next.
- This repo is LOCAL-ONLY as created (no remote). Ask the user before
  creating a GitHub remote or pushing anywhere.
