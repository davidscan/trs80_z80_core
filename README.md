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

**STATUS (2026-09-11): PHASE A COMPLETE, GATE RULED, BIG-PICTURE TALK
CLOSED, MEMORY-MODEL HANDOFF CLOSED, NORTH STAR RE-MEASURED, PROTOCOL
RATIFIED AND BUILT ON THE INTERPRETER SIDE, STAGE 1 (THE CORE) NOT
STARTED.** Phase A — the static disassembler/classifier over the
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
write new assembly, disassemble. The big-picture talk that gated Stage 1
from 2026-08-14 was CLOSED by the user 2026-09-07; the active work is
now GOAL (1), integrating machine code into BASIC programming.

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

Working through goal (1) turned up three interpreter-side memory-model
issues, all measured with runnable reproductions and all reported rather
than fixed (this project does not edit trs80basic): FINDING 22 (memory
reserved by MEMORY SIZE? is treated as ABSENT, so the classic
reserve-then-load idiom cannot write it), FINDING 23 (the program image
shadows POKEd bytes), and an uncapped `PEEK(16634)` that can return >255.
Handed over in `handoff/to-trs80basic.md`.

**RESOLVED 2026-09-08.** The handoff channel round-tripped twice: two
shipped on the interpreter side, and FINDING 23 measured at **zero**
across all 4,339 corpus files and deferred by agreement. That side also
found a half this one had missed — `POKE 16561/16562` was silently
dropped too, the programmatic form of the same idiom, 91 corpus listings,
with a confirmed rescue in `wordsmth.bas`. **The durable artifact is
neither the fixes nor the findings: it is "THE ADDRESS-RESOLUTION
CONTRACT" now written in `../trs80basic/src/p75_mem.awk`** — six
precedence rules for resolving one byte per address, which this core must
reproduce byte-for-byte or it will execute the wrong bytes with no error.
Both sides' halves of the exchange are in their `handoff/` directories.

**RE-MEASURED 2026-09-09 (FINDING 24).** The north-star acceptance case
was audited for readiness and FINDING 19 re-derived from its own prose,
because no committed code implemented its extraction recipe. Every number
reproduced; two claims did not. Dancing Demon is not a routine but a
**self-relocating dispatcher** — it patches a JP trampoline into 4018H
and finds its 106 subroutines by walking the BASIC line-record chain — so
correct next-line links and a writable, executable 4000-41FF are hard
requirements. It **does** call the ROM (`CALL 01C9H`, CLS, x4). It needs a
Z80 stack inside the 64K that no document places there. It does **not**
need a writable program image (measured, confirming what was already told
to trs80basic). And it is **fully position-independent**: 0 absolute CALLs
into its own body and 0 internal JPs in 10,931 bytes. (The stack question
was ruled two days later — DD-4, above.) The work items are
in **DANCING_DEMON.md**; three documents were corrected.

**PROTOCOL RATIFIED AND BUILT — ON THE INTERPRETER SIDE — 2026-09-11.**
`PROTOCOL.md` (mirrored byte-for-byte from trs80basic; the two copies must
stay identical) is the USR coprocess contract, version 1: one persistent
gawk coprocess per session, a contract-resolved sparse memory image in
(deltas after the first frame), video streamed out *during* the call, the
keyboard as the only callback, `T` ticks carrying BREAK, a write-set back
applied through the interpreter's `poke_byte`. trs80basic's half is done
and merged to its `main`: the p77 shim (`src/p77_z80.awk`), a reference
stub for THIS side (`programs/tests/z80_stub.py`) and a conformance suite
(`programs/tests/z80.sh`). The stack policy is ruled (DD-4: SP = the
interpreter's SSP, the core owns it for the call, the USR return address
is the sentinel **2FFDH** — DESIGN.md decision 6), and the 42E9H
window-overflow question is ruled (truncate at a whole line). The core's
acceptance bar before any listing is DD-17: pass `z80.sh` with
`TRS80_Z80` pointing at it.

See Z80_FINDINGS.md (24 findings) and DANCING_DEMON.md (the north-star
work-item ledger). Stage 1 (the core itself) is NOT started and no core
code has been written. Durable artifacts: the
validated 1780-entry opcode table (z80/table.py), disassembler,
extractor/classifier, sweep, the oracle, the pinned single-step vector
suite (tools/fetch_vectors.py), 104 tests. The debt to the interpreter —
the one-line `DEF USR 0=` parse fix — was PAID there 2026-08-14.

Read DESIGN.md for everything: goal, staged plan, technical reference
(addresses, ROM entry points, ports), the coprocess seam, testing
strategy, legal constraints, and decisions. PROTOCOL.md is the wire
contract the core must conform to. CLAUDE.md is the session bootstrap.

## Why this exists (one paragraph)

TRS-80 magazine listings constantly embed short Z80 routines via
`DATA`/`POKE` loaders called through `USR` — sound effects, fast screen
operations, keyboard scans, sorts. The interpreter runs the BASIC but
must stub the `USR` call (since 2026-08-13 the stub evaluates and
returns its argument; since 2026-09-11 it also prints one stderr line per
run tallying the calls it did not execute, and `TRS80_USR=strict` raises
?FC instead). The loader pattern already deposits the
machine-language bytes into the interpreter's `mem[]`, video memory
already maps to the simulated screen, the keyboard matrix is live at
the memory level, and a table-driven Python core executes Z80
instructions far faster than the real Model I's 1.77 MHz — measured
2026-09-09, a pre-decoded dispatch with full flag computation runs ~17x
the rate the north-star payload needs (FINDING 24) — so executing those
bytes is a bounded, testable, surprisingly practical build. The expensive
part is not the CPU; it is the high-level emulation of ROM services that
real routines call (see DESIGN.md), and the protocol that streams video
and key state while a routine is still running (PROTOCOL.md, with the
work items in DANCING_DEMON.md).
