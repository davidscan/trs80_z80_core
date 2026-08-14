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

**STATUS: NOT STARTED — deliberately.** This space holds the agreed
design and context so work can begin cold in a future session. The
start is gated on a measurement: a count of rescued listings actually
blocked on USR (see DESIGN.md "The gate"). The old proxy for that count
dissolved on 2026-08-13 when the parent shipped ML Stage 0 (keyboard
matrix + USR stub) and re-scanned the corpus; the agreed next step is
PHASE A — a static disassembler/classifier over the corpus's DATA/POKE
loader bytes — which produces the real gate number, the Stage 2 trap
priority list, and the sound-exclusion count in one measured pass, and
is this repo's first artifact.

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
