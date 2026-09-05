# trs80_z80_core — machine-language call support for the TRS-80 interpreter

A Z80 CPU core **in Python 3**, scoped to executing machine-language
subroutines **called from BASIC** (`USR`) — never standalone machine
language. Companion project to the TRS-80 LEVEL II BASIC interpreter at
`../trs80basic` (private GitHub: davidscan/trs80basic) — an independent
peer, not a sub-project.

Renamed from `awk_Z80_core` 2026-08-13 when the language ruling changed:
the user deemed the machine-language portion outside the scope of BASIC,
so it follows the project's standing split — the interpreter is awk,
non-BASIC tooling is Python (the basclean/detok precedent). The core
attaches to the interpreter as a persistent coprocess with a graceful
stub fallback, so `trs80basic.awk` stays a complete single-file gawk
program (see DESIGN.md "Language and the runtime seam").

**STATUS (audited 2026-09-04): PHASE A COMPLETE, GATE RULED, STAGE 1
NOT STARTED.** Phase A — the static disassembler/classifier over the
corpus's DATA/POKE loader bytes — ran over 4345 listings and returned
**5** unlocked listings. The one remaining hole in that measurement,
FINDING 7's 96 loaders static extraction could not resolve, was then
closed by building the dynamic extraction oracle (`phasea/oracle.py`,
DESIGN.md's recorded escalation path). Result: the measured
machine-code population more than **doubled, 46 → 107 files**, and the
gate number moved **5 → 6**. What is scarce in this corpus is not
machine code; it is a listing whose ONLY obstacle is the absent Z80.
The user ruled on 2026-08-14 that the rescue count does not justify
the core and no longer has to: the project is wanted for its own sake,
with four goals in priority order (CLAUDE.md "WHERE THINGS STAND") —
run BASIC with embedded machine code, run magazine assembly listings,
write new assembly, disassemble. Stage 1 waits on a big-picture talk,
not on a number.

The oracle also turned up two **interpreter-side** defects each worth
more listings than the core is: `USR n(` at the call site raised ?SN (134
listings — FINDING 8's sibling), and `PEEK(16396)` answered 255 where a
cassette Level II answers 201, sending 88 listings down their Disk
branch into CMD. Both were interpreter-owned, and **both SHIPPED there
2026-08-14** (`8c38dca6`, pre-split; the code now lives in trs80basic):
**53 blocked listings improved, 28 of them now running to completion,
zero regressions**, the interpreter's bar held (t1-t28 exit 0). The
corpus archive's `blocked/` re-scan followed the same evening: 280
files moved to runnable/, including four of the six gate files —
without any of them running to completion (FINDING 20).

See Z80_FINDINGS.md (20 findings). Stage 1 (the core itself) is NOT
started and no core code has been written. Durable artifacts: the
validated 1780-entry opcode table (z80/table.py), disassembler,
extractor/classifier, sweep, the oracle, the pinned single-step vector
suite (tools/fetch_vectors.py), 98 tests. The debt to the interpreter —
the one-line `DEF USR 0=` parse fix — was PAID there 2026-08-14.

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
