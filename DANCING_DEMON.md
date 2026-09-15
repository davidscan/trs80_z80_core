# DANCING_DEMON.md — the north-star acceptance case, as work items

The single acceptance target for the coprocess (DESIGN.md "Testing
strategy", Z80_FINDINGS FINDING 19): **"silent Dancing Demon dances."**
This file is the work-item ledger for that run — what must be true, who
owns it, and what is already measured. It is not a plan of record and
schedules nothing; Stage 1 was BUILT 2026-09-12 (it read "still not
started" until then) and the measure-before-building rule (DESIGN.md
non-goals: measure first) still governs what comes next.

EVIDENCE BASE: FINDING 19 (2026-09-02, the profile) and **FINDING 24
(2026-09-09, the re-measurement)**, which reproduced FINDING 19 exactly
and then corrected it on two points and added four. Read FINDING 24
before acting on anything here — several items exist only because of it.

## Definition of done

A BASIC program that is one of the 15 Dancing Demon images runs under
trs80basic with the core attached, and the demon animates on the
simulated screen at approximately period tempo, responding to keys,
with the two sound `OUT`s suppressed (since 2026-09-14: captured and
played when sound is on) and no other behavioural change.
Visually self-verifying; no transcript can assert it.

STATE 2026-09-13: DONE. The image loads intact (trs80basic R1, DD-14);
driven through a pseudo-terminal with the core attached, preset show #1
plays 28.6 s of emulated time with no error, streams 82 KB of video,
polls the keyboard 72 times and stops on the space bar (the run is under
"Reproducing the measurements"), and frames replayed from the protocol
log (tools/render_frames.py) show the figure dancing. The tempo
judgement was the user's, at a real terminal with `TRS80_MHZ=1.77`
(trs80basic's real-terminal checklist): CONFIRMED 2026-09-12, the demon dances
center stage at period tempo. Measured 2026-09-13 on that same path: a
paced USR routine of 4.57 s emulated time ran in 4.74 s of wall time
from RUN to its result, interactive, the keyboard polled every tick.

## What the target actually is (measured, FINDING 24)

| | |
|---|---|
| payload | 10,931 bytes, loads and runs at **42F6H** |
| where it lives | inside the tokenized program image, as 106 fake BASIC lines 2..258 — **not** a DATA/POKE loader |
| entry | `PEEK(16549)*256+PEEK(16548)+13`, POKEd to the 16526/16527 USR vector |
| structure | a **self-relocating dispatcher**: patches a JP trampoline into 4018H/4028H and walks the BASIC line-record chain to find routines by line number |
| opcodes needed | 169 distinct encodings, 23 mnemonics, main + 4 ED + 4 DD/FD. No CB page, no DAA, no block ops, no interrupts |
| ROM calls | **01C9H (CLS) x4** — one documented entry point, not zero |
| devices | video 3C00-3FFF (34 sites), keyboard 38FFH (1 site), port FFH (2 sites) |
| stack | CALL x268, RET x51, PUSH/POP x14, EXX x20, `EX AF,AF'` x138 |
| relocation | **fully position-independent** — 0 absolute CALLs into its own body, 0 internal JPs in 10,931 bytes; internal flow is `JR` x365 / `DJNZ` x22, everything longer-range goes through the trampoline |
| real-time bar | **313,030 insn/s** (mean 5.67 T-states at 1.77 MHz) |
| variants | all 15 images carry the same payload; 8 byte-identical. **One target, not four.** |

## A. This repo — the core (Stage 1: BUILT 2026-09-12 except DD-1)

STATUS 2026-09-12, item by item (the entries below keep their pre-build
text as the record): DD-1 OPEN. DD-2 BUILT — `z80/cpu.py`, all
1,604,000 pinned vectors pass. DD-3 BUILT — pre-decoded closure pages,
measured 2.1-2.7M insn/s. DD-4 RULED and BUILT — SP = SSP, sentinel
2FFDH pushed. DD-5 BUILT — 01C9H served, and 0A7FH/0A9AH with it (the
idiom's two services, not needed by the demon). DD-6 BUILT — every OUT
discarded, `IN A,(FFH)` reads 127.

- **DD-1. An extractor for the program-image idiom.** No committed code
  reads this payload. `phasea/sweep.py` covers `runnable/` + `blocked/`
  only, so the large collection — and therefore this program — has never
  been measured by any committed instrument, and FINDING 19's recipe
  survived as prose until FINDING 24 reimplemented it. Needs a
  detokenizer-aware reader too: the corpus file is a **tokenized** image
  (FF-prefixed) and `phasea/basic.py:read_source` assumes detokenized
  text. The runnable recipe is in FINDING 24 section 8.
  *Blocks: any repeatable measurement of the target.*

- **DD-2. The execution core.** `z80/` is `table.py` + `disasm.py` and
  nothing else — no register file, ALU, flag computation, memory
  interface or instruction loop. Note the table records **which** flags
  each opcode touches (the 6-char S Z H P/V N C mask), never **how** to
  compute them: every flag rule is still to be written, and
  `tests/test_vectors.py` says so in its own docstring ("Nothing in this
  file should be read as validating execution").
  *Scope relief from DD's profile: 169 encodings, no DAA, no CB page.
  That is a subset to reach the demon, NOT a licence to build a partial
  Z80 — goals (2)-(4) need the whole documented set.*

- **DD-3. Pre-decoded dispatch, not decode-per-instruction.** Measured:
  the disassembler's decode path runs 724,554 insn/s against a
  313,030 insn/s bar — 2.3x, with nothing left for memory callbacks,
  video streaming or protocol I/O. A pre-decoded closure dispatch with
  full flag computation measures 5,470,126 insn/s (~17x). Architectural
  constraint, settled by measurement before the code exists.

- **DD-4. A stack policy. — RULED 2026-09-11 (user, via the interpreter
  session): SP = the interpreter's SSP at call time (carried as `sp=` in
  every CALL), the core owns SP for the call and pushes into its own RAM
  beneath it (those bytes return in the write-set), and the USR return
  address is a SENTINEL the core pushes in 0000-2FFFH; PC entering ROM
  space is one mechanism for "frame ends" and for the HLE traps.  See
  PROTOCOL.md "A call".  THE SENTINEL IS **2FFDH**, ruled the same day
  (DESIGN.md decision 6: the documented empty tail of the ROM, above
  every documented entry point).  The record below is kept as the
  reasoning.**
  DESIGN.md places BASIC's stack outside the
  64K, which is right for BASIC and insufficient here: 268 calls need a
  real stack at a real 16-bit address. Undecided — where SP initialises,
  who owns it across the USR boundary, where the USR return address is
  pushed. *Decide before writing the core, not during.*
  INTERPRETER-SIDE PROPOSAL (trs80basic seam audit finding 5, 2026-09-11,
  NOT a ruling): seat SP at `SSP`, the bottom of allocated string space,
  mirroring hardware where the stack sits just below string space, and
  push into ordinary `mem[]` beneath it. Two hazards on the record: `SSP`
  now moves only on genuine string growth (the 2026-09-10 VARPTR fix made
  it steady, though still not fixed for the run), and a stack that grows
  into an SPK region writes through into a packed string — authentic,
  silent. Recorded so the decision starts from a concrete option.
  STRUCK 2026-09-11 (their REPLY 7): the SPK hazard was overstated — SSP
  is the BOTTOM of the packed-string region, so a downward stack moves
  away from it; the only real hazard is a stale SSP, and a frame built at
  call time cannot be stale.

- **DD-5. One HLE trap: 01C9H (CLS).** Documented in four library books,
  so legal under the never-commit-ROM rule, and trivial to reimplement.
  It is **not** on DESIGN.md's Stage 2 trap list, which was measured
  over a population that excludes this program. Adding it does not
  reopen the corpus-driven rule — it applies it to a listing the sweep
  never saw.
  *Not needed for the demon: 0A7FH/0A9AH. The payload never converts the
  USR argument and never sets a result; it just RETs.*
  The trap does what the ROM's does, and both halves of its 64-column
  restore matter: it emits `MODE 0` (the hardware latch, so the figure is
  drawn at full width) and clears bit 3 of the port image at 403DH in the
  write-set (the ROM's print flag, so the BASIC PRINTs that paint the
  stage after the call step one byte). The second half was missing from
  2026-09-13, when the interpreter split the latch from the flag, to
  2026-09-15: the stage rows landed on every other cell, the "background
  not clearing". test_coprocess pins both; z80.sh entry 700D pins it
  through the protocol.

- **DD-6. The two sound `OUT`s: captured when sound is on (2026-09-14,
  `z80/sound.py`, DESIGN.md decision 7), discarded otherwise — and
  keep the delay loops.** [As written before the build: "Suppress the
  two sound `OUT`s — and keep the delay loops."]
  Port FFH bit 3 selects 32-character video mode, but both writes carry
  02H/01H with bit 3 clear, so suppression has no display side effect.
  The surrounding `DJNZ` loops are the tempo and must still execute.
  INTERPRETER STATE 2026-09-11 (their REPLY 9): `INP(p)` exists there —
  port FFH reads 127 in 64-character mode and 63 in 32-character mode,
  every other port 255 — so a core executing `IN A,(FFH)` should agree
  with the interpreter's mode. `OUT` is discarded on that side and the
  bit-3 width switch is built nowhere; for the demon nothing changes.

## B. This repo — the protocol (specified in PROTOCOL.md; both halves built as of 2026-09-12)

STATUS 2026-09-12: the core's half of DD-7 through DD-10 is BUILT in
`z80/coprocess.py` — video stores stream as `V` lines at every tick and
before `RET` (DD-7); a read of 3800H-38FFH is the `K` callback (DD-8);
when HELLO carries an mhz the call is paced to real time at each tick
(DD-9; the cycle column it leans on is now vector-validated); `T` ticks
every 8870 T-states carry BREAK and keep the interpreter alive (DD-10).
The entries below keep their pre-build text as the record.

- **DD-7. Streamed video, not memory-at-RET. — PROTOCOL DONE 2026-09-11:
  `V` lines during the call, drawn as they arrive; the frame in is the
  interpreter's sparse contract-resolved image with delta frames after
  the first; `K` is the only callback; `T` ticks carry BREAK.  See
  PROTOCOL.md; the interpreter's shim is built (`src/p77_z80.awk`, their
  `76b95a0`, MERGED to their main the same day) and
  `programs/tests/z80_stub.py` there is the reference implementation of
  THIS side.  What remains of DD-7 is the core's half.** The animation writes
  3C00-3FFF *during* the USR call. FINDING 19's central point and still
  the one that decides the protocol's shape: call-and-return USR
  (memory in, run, memory out) cannot serve this class of program.
  RELATED (finding 4, 2026-09-11): whatever the frame carries as "memory,"
  it is NOT trs80basic's raw `mem[]` — the payload at 42F6H, the packed
  strings and the system pointers are `dopeek` projections, so the frame's
  memory image must be resolved through the address-resolution contract,
  not read out of `mem[]`. See DESIGN.md's corrected CALL FRAME bullet.

- **DD-8. Live key state into coprocess reads of 3800-38FFH.** One site,
  `LD HL,38FFH`, the all-rows poll. The interpreter's keyboard layer
  already holds the state (Stage 0, shipped 2026-08-13).

- **DD-9. Cycle pacing.** The demon must dance at 1.77 MHz tempo, not as
  fast as Python goes. The cycle column exists for this and is
  **largely unvalidated** — one external check covers 92 index-half
  entries (FINDING 21). Pacing this program leans on the column for real
  for the first time.

- **DD-10. Sustained execution. — the protocol half exists (T ticks,
  READ_TIMEOUT guard, pid kill, NEED resend, version handshake, all in
  PROTOCOL.md and exercised by the interpreter's z80.sh).** Long-running USR with the interpreter
  responsive, plus whatever the version handshake and clean-mismatch
  error require (ratified 2026-09-02).

## C. Interpreter-side dependencies — REPORT, NEVER BUILD

Owned by trs80basic. Until 2026-09-12 this side reported and never built
there; since then one session works both repos, so an item here is built
there directly and the handoff files are a dated record. **NOT
AUDITED in the 2026-09-09 pass** — the audit was scoped to this project
at the user's direction; the statuses marked DONE/CORRECTED below were
reported by that side in its handoff replies (2026-09-10/11) and read
from its tree, not measured here. Anything owed there went through
the handoff exchange (a dated record, kept in this repo's history) with a
runnable reproduction and its expected
effect on their bar, t1-t33 as of 2026-09-11 (t32 needs the reference
stub in `TRS80_Z80`).

- **DD-11. The tokenized image mapped at 42E9H with correct next-line
  links.** The chain is the dispatch mechanism, not decoration — a wrong
  link is a jump into garbage with no error. DESIGN.md used to flag the
  `% 65536` wrap in `pm_build`; RULED AND FIXED on the interpreter side
  2026-09-11 (their `b2c4cca`): the image truncates at a whole line before
  RAMTOP, writes the 00 00 terminator, 40F9H reports that end. Correct
  links now hold for every program size; nothing outstanding.
- **DD-12. 4000-41FF writable AND executable. — CORRECTED 2026-09-11: the
  write contract shipped 2026-09-09 (4b5f7cd) and the store primitive is
  now `poke_byte` (96d439f); the write-set is applied through it, so a
  store to 4018H lands in the interpreter's MEM[] and comes back in the
  next frame.  Nothing outstanding.** The payload writes C3H
  to 4018H and a target to 4019H, then calls it. [Until 2026-09-11 this
  read: whether writes there reach the core's RAM or fall into a
  projection is the `st_poke` asymmetry raised with trs80basic and still
  outstanding, the contract covering `dopeek` only. The write side of
  the contract is now written in their `src/p75_mem.awk`.]
- **DD-13. 40A4H/40A5H reads 42E9H** — via `PEEK(16548/16549)` in BASIC
  and `LD HL,(40A4H)` in the payload. Both halves must agree.
- **DD-14. LOAD of a tokenized program image. — DONE on the interpreter
  side 2026-09-12 (their R1).** `CLOAD` of an FF-headed image now keeps
  every line's original body bytes in a per-line escrow and images those
  bytes verbatim, relinked at 42E9H; the demon file loads byte-identical
  (14,506 bytes) and `PEEK` sees the payload's CR bytes intact. Their
  three user-visible decisions: LIST shows the detokenized text (keyword
  spacing included); the loader is one-way (CSAVE/SAVE write text);
  the escrow is dropped by a typed replacement, DELETE, NEW, a MERGE
  over the line, and NAME (renumber drops every line's). [As written
  until then: the corpus files are
  tokenized, not detokenized text. Their item R1, UNBUILT as of 2026-09-11
  and the one Dancing Demon item still owed on that side (their STATUS,
  "WHERE TO PICK UP" 2). Their REPLY 3 measured why it matters to the
  core: `CLOAD` of the tokenized file fails, and the sanctioned detok
  path rewrites 14 newline bytes, all inside the payload — 0DH is `DEC C`
  — so today no supported path loads the payload intact. Check the bytes
  before the core.]
- **DD-15. The USR call frame must carry the slot digit. — DONE on the
  interpreter side 2026-09-10.** The spaced-call fix used to dispatch
  `USR n(` as name `USR`, discarding the digit. trs80basic now folds the
  digit into the name and its `usr_resolve()` fills a frame per call:
  USR_SLOT, USR_ENTRY (DEF USRn wins; slot 0 falls back to the 408EH POKE
  vector; slots 1-9 and an unwritten vector resolve UNDEFINED = entry -1,
  which this core reads as ?FC), and USR_ARG. DEF USRn addresses are stored
  in USRDEF[0..9]. `TRS80_USR_TRACE=1` dumps the frame; `programs/tests/usr.sh`
  asserts it. (trs80basic session, user's permission, 2026-09-10; handoff
  REPLY 5.) CONSUMED since 2026-09-11: the p77 shim's `z80_usr()` hands the
  frame to the core (`CALL slot= entry= arg=`, PROTOCOL.md).
- **DD-16. The core must reproduce THE ADDRESS-RESOLUTION CONTRACT**
  (`../trs80basic/src/p75_mem.awk`) byte-for-byte, including the
  post-fix order: `a in SPK` outranks the program image, HIMEM no longer
  bounds the shadow, unwritten memory reads **255**, not 0, and (since
  2026-09-12) a WRITTEN image address reads back the written byte, not the
  crunched original -- the image is writable RAM.
  AS BUILT 2026-09-12: the core reproduces NOTHING of the contract, by
  PROTOCOL.md's ruling — the frame carries bytes already resolved
  through `dopeek`, the core keeps a flat 64K initialised to 255 and
  applies runs over it, and any address no frame named reads 255. The
  contract lives on one side only.

- **DD-17. Conform to PROTOCOL.md (mirrored here from trs80basic; the
  shim, stub and suite are on their main since 2026-09-11).** The
  core's acceptance bar before any listing: `TRS80_Z80="python3
  /path/to/core" sh programs/tests/z80.sh` in trs80basic passes, with the
  stub's canned entries (7000H-700AH, listed in the stub) implemented as
  real machine code in the frame.  The shim does not adapt to the core.
  Announce `pid=` in the `Z80` hello line and exit on EOF.
  **CONFORMANT 2026-09-12:** `cd ../trs80basic && TRS80_Z80="python3
  ../trs80_z80_core/core.py --fixture" sh programs/tests/z80.sh` prints
  `Z80 FIXTURE OK`, and t32 there is byte-identical to the stub's run.
  The fixture lays the routines out from 7100H and maps each canned
  entry to its routine (the entries are one byte apart); 7004H and
  7008H stay harness hooks as in the stub.

## D. Not needed — do not build on spec

- **A writable program image. — NEEDED AFTER ALL, and BUILT on the
  interpreter side 2026-09-12.** The static "not needed" call below was
  wrong, and it named its own blind spot: the 172 HL-indirect writes it
  could not resolve.  The demon's SCORE and DANCE editors (menu 1 and 2)
  keep their buffer INSIDE the loaded image at 6B9BH and append to it one
  HL-indirect store per keypress.  With the image read-only, every USR
  frame re-delivered the original crunched byte and clobbered the letter
  the routine had stored, so the editor overwrote instead of appending.
  trs80basic made the image writable (dopeek returns MEM[a] when an image
  address was written, else the crunched byte; RUN/LIST still work from
  the source text) -- see its `42f576a` and the updated address-resolution
  contract.  The core needs no change: it keeps flat RAM and just reads
  back its own write-set. *The original static reasoning, kept as the
  record of the miss:* every real absolute write goes to system RAM
  (4019H-402BH, 4100H); the four apparent in-image writes are ASCII text
  mis-decoded as `LD (nn),A`; but 172 HL-indirect and 14 stack writes were
  statically unresolvable -- strong evidence, not proof, and the editor
  fell in the unresolved set.
- **The 42E9H window-overflow policy** — RULED 2026-09-11 on the
  interpreter side: truncate at a whole line (see DD-11). It never bound
  here anyway: the image spans 42E9H-7DE5H, 15,100 bytes, 33,307 clear of
  FFFFH.
- **0A7FH / 0A9AH traps** — see DD-5.
- **Relocation machinery of any kind.** The payload never names an
  address inside itself (FINDING 24 section 9), so it runs wherever the
  image places it. Its load address is a consequence of the image
  mapping, not a requirement to be satisfied — which is also why DD-11's
  correct next-line links matter more than any load-address handling.
- **ROM emulation beyond CLS**, DAA, the CB page, block instructions,
  interrupt modes, bank switching.

## Open questions this file does not settle

1. ~~**Where does the Z80 stack live** (DD-4)~~ — SETTLED 2026-09-11: SP
   at SSP, the core owns it for the call, the return sentinel is 2FFDH
   (DD-4, DESIGN.md decision 6). Kept so the numbering below holds.
2. ~~**How much video traffic per second** the protocol must carry~~ —
   MEASURED 2026-09-12 from the protocol log of the pty-driven run: the
   28.6 s preset show #1 streamed 5,440 `V` runs / 82,148 video bytes
   (2.9 KB/s, 190 runs/s); the intro's curtain 262 runs / 4,068 bytes
   over 2.7 s (1.5 KB/s); the stage setup 2,773 bytes in 0.09 s (a
   31 KB/s burst — its CLS, one 1,024-byte run). Negligible for a text
   pipe; the per-tick batching in `Machine.flush_video` is more than
   enough. [As written: the
   34 static write sites say nothing about dynamic volume; measuring it
   needs a running core, so this was the first item that could not be
   settled by measurement before building.]
3. **How faithful the pacing must be** to read as "dancing" (DD-9) —
   a perceptual bar, not a numeric one. ANSWERED 2026-09-12 by the user
   at a real terminal (`TRS80_MHZ=1.77`, trs80basic's real-terminal checklist): it
   reads as dancing at period tempo. Measured 2026-09-13: paced execution
   on that interactive path tracks real time within 4% ("State" above);
   the 2026-09-12 pty run itself was unpaced (mhz=0).

## Reproducing the measurements

The extraction recipe is in FINDING 24 section 8 (runnable, ~15 lines) until
DD-1 lands. The profile is a linear sweep plus a recursive-descent trace
seeded from 42F6H and the 106 fake-line body addresses; `z80/disasm.py`
decodes all 8,068 instructions with zero undecodable, and every count in
this file was produced by resolving addresses through the table rather
than by matching text (the corpus-counting rule: resolve through the
table, never match text).

The 2026-09-12 run behind "State": a Python `pty.fork` driver typing
'\r' (MEMORY SIZE), CLOAD of the image, RUN, '6', '20\r', '1\r', a wait,
then ' ', with `TRS80_Z80="sh tools/corelog.sh /tmp/x"` logging the
protocol. Six USR calls at entry 42F6H, no ERR: the intro's curtain
(routine 39: 2.7 s, 262 V runs, 5 K polls) and bow (29: 6.1 s, 55 runs /
800 bytes), the stage setup (27: 0.09 s, 2,773 bytes — its CLS), preset
show #1 (routine 37: 28.6 s emulated, 5,440 V runs / 82,148 video bytes
= 2.9 KB/s, 5,706 ticks, 72 K polls, ended by the space bar), then two
bows. `python3 tools/render_frames.py /tmp/x.out 4 400 1200 2000 2800
3600 4400` replays the streamed video.
