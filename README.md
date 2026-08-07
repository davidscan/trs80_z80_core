# awk_Z80_core — machine-language call support for the TRS-80 interpreter

A Z80 CPU core in GNU awk, scoped to executing machine-language
subroutines **called from BASIC** (`USR`) — never standalone machine
language. Companion sub-project to the TRS-80 LEVEL II BASIC interpreter
at `../awk_BASIC_interpreter` (private GitHub:
davidscan/trs80-basic-interpreter).

**STATUS: NOT STARTED — deliberately.** This space holds the agreed
design and context so work can begin cold in a future session. The
start is gated on a measurement: a count of rescued listings actually
blocked on USR (see DESIGN.md "The gate"). As of 2026-08-07 that count
is ~2, which does not justify the build. The vision-intake pipeline in
the parent repo keeps rescuing magazine listings; when the count grows,
this project wakes up.

Read DESIGN.md for everything: goal, staged plan, technical reference
(addresses, ROM entry points, ports), testing strategy, legal
constraints, and open decisions. CLAUDE.md is the session bootstrap.

## Why this exists (one paragraph)

TRS-80 magazine listings constantly embed short Z80 routines via
`DATA`/`POKE` loaders called through `USR` — sound effects, fast screen
operations, keyboard scans, sorts. The interpreter runs the BASIC but
must stub or refuse the `USR` call. The loader pattern already deposits
the machine-language bytes into the interpreter's `mem[]`, video memory
already maps to the simulated screen, and a gawk interpreter loop
plausibly executes Z80 instructions at roughly real-Model-I speed
(1.77MHz ≈ 440K instr/s) — so executing those bytes is a bounded,
testable, surprisingly practical build. The expensive part is not the
CPU; it is the high-level emulation of ROM services that real routines
call (see DESIGN.md).
