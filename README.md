# trs80_z80_core — machine-language call support for the TRS-80 interpreter

A Z80 CPU core **in Python 3**, scoped to executing machine-language
subroutines **called from BASIC** (`USR`) — never standalone machine
language. Companion sub-project to the TRS-80 LEVEL II BASIC interpreter
at `../awk_BASIC_interpreter` (private GitHub:
davidscan/trs80-basic-interpreter).

Renamed from `awk_Z80_core` 2026-08-13 when the language ruling changed:
the user deemed the machine-language portion outside the scope of BASIC,
so it follows the project's standing split — the interpreter is awk,
non-BASIC tooling is Python (the basclean/detok precedent). The core
attaches to the interpreter as a persistent coprocess with a graceful
stub fallback, so `trs80basic.awk` stays a complete single-file gawk
program (see DESIGN.md "Language and the runtime seam").

**STATUS: PHASE A COMPLETE; GATE RULING DEFERRED (2026-08-14).**
Phase A — the static disassembler/classifier over the corpus's
DATA/POKE loader bytes — ran over 4345 listings and produced the gate
number: **5 blocked listings unlocked by the core (+parent VARPTR),
21-23 correctness gains, Stage 2's candidate traps measured at zero
callers**. See Z80_FINDINGS.md (12 findings; FINDING 8 resolved
2026-08-14). The user's ruling on the gate: **stop here for now,
discuss further** — Stage 1 (the core itself) is NOT started, and no
core code should be written until the user rules the gate met.
Durable Phase A artifacts: the validated 1780-entry opcode table
(z80/table.py), disassembler, extractor/classifier, sweep, 64 tests.
Open lever recorded, not built: the dynamic extraction oracle over
the 96 unresolvable loaders (DESIGN.md escalation path). Owed to the
PARENT repo: the one-line `DEF USR 0=` parse fix (findings
correction 4).

Read DESIGN.md for everything: goal, staged plan, technical reference
(addresses, ROM entry points, ports), the coprocess seam, testing
strategy, legal constraints, and decisions. CLAUDE.md is the session
bootstrap.

## Why this exists (one paragraph)

TRS-80 magazine listings constantly embed short Z80 routines via
`DATA`/`POKE` loaders called through `USR` — sound effects, fast screen
operations, keyboard scans, sorts. The interpreter runs the BASIC but
must stub the `USR` call (since 2026-08-13 the stub evaluates and
returns its argument). The loader pattern already deposits the
machine-language bytes into the interpreter's `mem[]`, video memory
already maps to the simulated screen, the keyboard matrix is live at
the memory level, and a table-driven Python core executes Z80
instructions far faster than the real Model I's 1.77MHz (~440K
instr/s) — so executing those bytes is a bounded, testable,
surprisingly practical build. The expensive part is not the CPU; it is
the high-level emulation of ROM services that real routines call (see
DESIGN.md).
