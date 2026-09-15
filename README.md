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

**SOUND (2026-09-14): BUILT.** A `USR` routine's port FFH writes -- the
cassette output, the machine's only sound -- are captured with their
T-state positions and rendered to a live player, a WAV file, or both
(`z80/sound.py`; DESIGN.md decision 7; "Run" below).

**STATUS (2026-09-12): STAGE 1 IS BUILT.** The user gave the go ruling
on 2026-09-12 and the core landed the same day in two commits: `20f7a9e`
(`z80/cpu.py`, the execution core, passing **all 1,604,000** pinned
single-step vectors, measured at 2.1-2.7M insn/s against the 313K bar)
and `3164eb2` (`z80/coprocess.py` + `core.py`, PROTOCOL.md's core half;
trs80basic's `sh programs/tests/z80.sh` passes end to end with
`TRS80_Z80="python3 ../trs80_z80_core/core.py --fixture"`, and its t32
transcript is byte-identical to the stub's). 126 tests green. See "Run"
below. **THE DANCING DEMON DANCES** (2026-09-12, the same day, once
trs80basic built its R1 tokenized loader): the image CLOADs
byte-identical, preset show #1 plays 28.6 s of emulated time through the
core with no error (driven through a pseudo-terminal; batch cannot play
it), and frames replayed from the streamed video with
`tools/render_frames.py` show the figure dancing — the numbers are in
DANCING_DEMON.md ("State"). The user confirmed at a real terminal on
2026-09-12 that it dances at period tempo.
[The line this replaced, kept for the record: "STATUS (2026-09-11):
PHASE A COMPLETE, GATE RULED, BIG-PICTURE TALK CLOSED, MEMORY-MODEL
HANDOFF CLOSED, NORTH STAR RE-MEASURED, PROTOCOL RATIFIED AND BUILT ON
THE INTERPRETER SIDE, STAGE 1 (THE CORE) NOT STARTED."] Phase A — the static disassembler/classifier over the
corpus's DATA/POKE loader bytes — ran over 4345 listings and returned
**5** unlocked listings. The one remaining hole in that measurement,
FINDING 7's 96 loaders static extraction could not resolve, was then
closed by building the dynamic extraction oracle (`phasea/oracle.py`,
DESIGN.md's recorded escalation path). Result: the measured
machine-code population more than **doubled, 46 → 107 files** (the static
46 re-measured as 124 on 2026-09-15 once three extractor undercounts,
string packing above all, were fixed, FINDING 26), and the
gate number moved **5 → 6**. What is scarce in this corpus is not
machine code; it is a listing whose ONLY obstacle is the absent Z80.
The user ruled on 2026-08-14 that the rescue count does not justify
the core and no longer has to: the project is wanted for its own sake,
with four goals in priority order (DESIGN.md, "RULED 2026-08-14") —
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
work-item ledger). Stage 1 (the core itself) is BUILT as of 2026-09-12
(it read "NOT started" until that day). Durable artifacts: the
validated 1780-entry opcode table (z80/table.py), disassembler,
extractor/classifier, sweep, the oracle, the pinned single-step vector
suite (tools/fetch_vectors.py), the execution core (z80/cpu.py), the
coprocess (z80/coprocess.py, core.py), 126 tests. The debt to the interpreter —
the one-line `DEF USR 0=` parse fix — was PAID there 2026-08-14.

Read DESIGN.md for everything: goal, staged plan, technical reference
(addresses, ROM entry points, ports), the coprocess seam, testing
strategy, legal constraints, and decisions. PROTOCOL.md is the wire
contract the core must conform to. The session bootstrap is a local file
that is not published.

## Run

Checked out beside trs80basic, as `../trs80_z80_core`, nothing needs
naming: its launcher finds `core.py` by itself, and `USR` routines
execute. Pace the clock, or a long routine runs as fast as Python goes:

    cd ../trs80basic && TRS80_MHZ=1.77408 ./basic prog.bas

From anywhere else, name the core; `TRS80_Z80=` (empty) runs without one:

    TRS80_Z80="python3 /path/to/trs80_z80_core/core.py" ../trs80basic/basic prog.bas

`core.py` is what `TRS80_Z80` names; it speaks PROTOCOL.md version 1 on
stdin/stdout and `USR` routines in `prog.bas` then execute. Python 3,
standard library only. `--fixture`
adds the machine-code routines behind the reference stub's canned entry
addresses (laid out from 7100H and mapped by entry; 7004H and 7008H stay
harness hooks), which is what trs80basic's conformance suite needs:

    cd ../trs80basic && TRS80_Z80="python3 ../trs80_z80_core/core.py --fixture" sh programs/tests/z80.sh

**Sound.** Three environment variables, inherited from the interpreter's
environment (the protocol does not change), turn on machine-code sound:

    TRS80_SOUND="auto"            live playback through an installed player
    TRS80_SOUND_WAV=out.wav       a WAV file of the routines' audio, emulated time only
    TRS80_SOUND_RATE=22050        the sample rate (default; 44100 also sensible)

`auto` picks ffplay wherever it is installed (then ffmpeg's AudioToolbox
device on macOS, aplay, pw-play). `TRS80_SOUND` may instead be any command that
takes raw 16-bit little-endian mono PCM on stdin; `{rate}` in it becomes
the rate, and it runs through `sh -c` with its output discarded:

    TRS80_SOUND="ffmpeg -hide_banner -loglevel quiet -f s16le -ar {rate} -ch_layout mono -i - -f audiotoolbox -"
    TRS80_SOUND="ffplay -nodisp -autoexit -loglevel quiet -f s16le -ar {rate} -ch_layout mono -i -"
    TRS80_SOUND="aplay -q -f S16_LE -r {rate} -c 1"

Live sound needs the core paced, so with a player set and no `TRS80_MHZ`
it paces at 1.77408 MHz. A player that cannot start or that dies turns
live sound off for the session, silently; the WAV, if any, carries on.
The WAV's pitch is true at any pacing, and the same bytes come out paced
or unpaced. From the interpreter, the `sound` metacommand switches both
at the prompt (`sound on`, `sound wav out.wav`). Machine code only:
BASIC's own `OUT 255` stays silent, by ruling.

Tests here:

    python3 -m unittest discover -s tests          # 150 tests; vectors sampled 40/file
    python3 tools/fetch_vectors.py --all           # once: the 1.37 GB pinned suite
    python3 tools/usr_sweep.py                     # the corpus's USR listings through the core (FINDING 25)
    Z80_VECTORS=all python3 -m unittest tests.test_cpu_vectors   # all 1,604,000 cases, ~20 s

## Commands and arguments

Everything runs from this folder with the standard library.

| command | what it does |
|---|---|
| `python3 core.py` | the coprocess the interpreter names in `TRS80_Z80`; PROTOCOL.md on stdin/stdout. `--fixture` adds the conformance routines behind the stub's canned entries. Reads `TRS80_SOUND`, `TRS80_SOUND_WAV`, `TRS80_SOUND_RATE` (above). |
| `python3 -m z80.disasm FILE --base ADDR` | disassemble raw Z80 bytes loaded at ADDR (`0x7F00`, `7F00H` or decimal); `--hex "CD 7F 0A ..."` instead of a file, `--skip N` and `--length N` for a slice. |
| `python3 -m unittest discover -s tests` | the test suite; `Z80_VECTORS=all` runs every CPU vector. |
| `python3 tools/fetch_vectors.py --all` | fetch the pinned CPU test vectors once (never committed; `tools/vectors.lock` pins them). |
| `python3 -m phasea.sweep [--json out/manifest.json]` | Phase A: the static extractor and classifier over the corpus beside this checkout; refuses to publish counts unless the anchor suites pass. |
| `python3 -m phasea.oracle [--hangs --files LIST]` | the dynamic extraction oracle: run a listing under the interpreter's stub and read what its loader deposited. |
| `python3 tools/usr_sweep.py` | the corpus's USR listings executed by this core, three ways, classified (FINDING 25); writes `out/usr_sweep/`. |
| `python3 tools/usr_pty_sweep.py [--class no-usr-reached]` | the same population driven through a pseudo-terminal with a keystroke script, for the listings whose USR call sits behind an INKEY$ menu; writes `out/usr_pty_sweep/`. |
| `sh tools/corelog.sh PREFIX` | as `TRS80_Z80`, runs the core with both directions logged to PREFIX.in / PREFIX.out. |
| `python3 tools/render_frames.py LOG CALL RUN...` | replay a log's video lines into pixel frames of one call. |
| `python3 tools/reconstruct_screen.py CAPTURE` | the 64x16 grid a captured terminal stream actually drew. |
| `python3 tools/tick_probe.py` | measure the interpreter's tick cost under a paced routine, batch and interactive. |

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

## License

Copyright (c) 2026 David Forbis. GNU General Public License v3.0 — see
`LICENSE`. Distributed WITHOUT ANY WARRANTY.

**TRS-80**, **Radio Shack** and **Tandy** are trademarks of their
respective owners, used only to describe compatibility; this project is not
affiliated with or endorsed by them.
