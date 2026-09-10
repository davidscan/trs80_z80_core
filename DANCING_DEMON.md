# DANCING_DEMON.md — the north-star acceptance case, as work items

The single acceptance target for the coprocess (DESIGN.md "Testing
strategy", Z80_FINDINGS FINDING 19): **"silent Dancing Demon dances."**
This file is the work-item ledger for that run — what must be true, who
owns it, and what is already measured. It is not a plan of record and
schedules nothing; Stage 1 is still not started and CLAUDE.md's
"measure before building" rule still governs.

EVIDENCE BASE: FINDING 19 (2026-09-02, the profile) and **FINDING 24
(2026-09-09, the re-measurement)**, which reproduced FINDING 19 exactly
and then corrected it on two points and added four. Read FINDING 24
before acting on anything here — several items exist only because of it.

## Definition of done

A BASIC program that is one of the 15 Dancing Demon images runs under
trs80basic with the core attached, and the demon animates on the
simulated screen at approximately period tempo, responding to keys,
with the two sound `OUT`s suppressed and no other behavioural change.
Visually self-verifying; no transcript can assert it.

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

## A. This repo — the core (all unbuilt; Stage 1)

- **DD-1. An extractor for the program-image idiom.** No committed code
  reads this payload. `phasea/sweep.py` covers `runnable/` + `blocked/`
  only, so `LargeCollection/` — and therefore this program — has never
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

- **DD-4. A stack policy.** DESIGN.md places BASIC's stack outside the
  64K, which is right for BASIC and insufficient here: 268 calls need a
  real stack at a real 16-bit address. Undecided and unrecorded — where
  SP initialises, who owns it across the USR boundary, where the USR
  return address is pushed. *Decide before writing the core, not during.*

- **DD-5. One HLE trap: 01C9H (CLS).** Documented in four library books,
  so legal under the never-commit-ROM rule, and trivial to reimplement.
  It is **not** on DESIGN.md's Stage 2 trap list, which was measured
  over a population that excludes this program. Adding it does not
  reopen the corpus-driven rule — it applies it to a listing the sweep
  never saw.
  *Not needed for the demon: 0A7FH/0A9AH. The payload never converts the
  USR argument and never sets a result; it just RETs.*

- **DD-6. Suppress the two sound `OUT`s — and keep the delay loops.**
  Port FFH bit 3 selects 32-character video mode, but both writes carry
  02H/01H with bit 3 clear, so suppression has no display side effect.
  The surrounding `DJNZ` loops are the tempo and must still execute.

## B. This repo — the protocol (unbuilt; the real work)

- **DD-7. Streamed video, not memory-at-RET.** The animation writes
  3C00-3FFF *during* the USR call. FINDING 19's central point and still
  the one that decides the protocol's shape: call-and-return USR
  (memory in, run, memory out) cannot serve this class of program.

- **DD-8. Live key state into coprocess reads of 3800-38FFH.** One site,
  `LD HL,38FFH`, the all-rows poll. The interpreter's keyboard layer
  already holds the state (Stage 0, shipped 2026-08-13).

- **DD-9. Cycle pacing.** The demon must dance at 1.77 MHz tempo, not as
  fast as Python goes. The cycle column exists for this and is
  **largely unvalidated** — one external check covers 92 index-half
  entries (FINDING 21). Pacing this program leans on the column for real
  for the first time.

- **DD-10. Sustained execution.** Long-running USR with the interpreter
  responsive, plus whatever the version handshake and clean-mismatch
  error require (ratified 2026-09-02).

## C. Interpreter-side dependencies — REPORT, NEVER BUILD

Owned by trs80basic (CLAUDE.md: do not edit that repo at all). **NOT
AUDITED in the 2026-09-09 pass** — the audit was scoped to this project
at the user's direction, so every item below is a stated requirement,
not a verified status. Anything owed there goes through
`handoff/to-trs80basic.md` with a runnable reproduction and its expected
effect on the t1-t28 bar.

- **DD-11. The tokenized image mapped at 42E9H with correct next-line
  links.** The chain is the dispatch mechanism, not decoration — a wrong
  link is a jump into garbage with no error. DESIGN.md already flags the
  `% 65536` wrap in `pm_build`; this program makes it load-bearing.
- **DD-12. 4000-41FF writable AND executable.** The payload writes C3H
  to 4018H and a target to 4019H, then calls it. Whether writes there
  reach the core's RAM or fall into a projection is exactly the
  `st_poke` asymmetry already raised with trs80basic and still
  outstanding (CLAUDE.md; the address-resolution contract covers
  `dopeek` only).
- **DD-13. 40A4H/40A5H reads 42E9H** — via `PEEK(16548/16549)` in BASIC
  and `LD HL,(40A4H)` in the payload. Both halves must agree.
- **DD-14. LOAD of a tokenized program image.** The corpus files are
  tokenized, not detokenized text.
- **DD-15. The USR call frame must carry the slot digit.** Known latent
  issue (DESIGN.md decision 3): the spaced-call fix dispatches `USR n(`
  as name `USR`, discarding the digit. Harmless under the stub, not
  under a core.
- **DD-16. The core must reproduce THE ADDRESS-RESOLUTION CONTRACT**
  (`../trs80basic/src/p75_mem.awk`) byte-for-byte, including the
  post-fix order: `a in SPK` outranks the program image, HIMEM no longer
  bounds the shadow, and unwritten memory reads **255**, not 0.

## D. Not needed — do not build on spec

- **A writable program image.** Measured, not merely reasoned: every
  real absolute write goes to system RAM (4019H-402BH, 4100H); the four
  apparent in-image writes are ASCII text mis-decoded as `LD (nn),A`.
  This confirms the answer already given to trs80basic in
  `handoff/to-trs80basic.md`. *Limit: 172 HL-indirect and 14 stack
  writes are statically unresolvable, so this is strong evidence, not
  proof.*
- **The 42E9H window-overflow policy** (DESIGN.md, UNDECIDED). Does not
  bind here: the image spans 42E9H-7DE5H, 15,100 bytes, 33,307 clear of
  FFFFH. Still open for goal (1) generally, just not on this path.
- **0A7FH / 0A9AH traps** — see DD-5.
- **Relocation machinery of any kind.** The payload never names an
  address inside itself (FINDING 24 section 9), so it runs wherever the
  image places it. Its load address is a consequence of the image
  mapping, not a requirement to be satisfied — which is also why DD-11's
  correct next-line links matter more than any load-address handling.
- **ROM emulation beyond CLS**, DAA, the CB page, block instructions,
  interrupt modes, bank switching.

## Open questions this file does not settle

1. **Where does the Z80 stack live** (DD-4) — the only design decision
   on the critical path with nothing written about it anywhere.
2. **How much video traffic per second** the protocol must carry. The
   34 static write sites say nothing about dynamic volume; measuring it
   needs a running core, so this is the first item that cannot be
   settled by measurement before building.
3. **How faithful the pacing must be** to read as "dancing" (DD-9) —
   a perceptual bar, not a numeric one.

## Reproducing the measurements

The extraction recipe is in FINDING 24 section 8 (runnable, ~15 lines) until
DD-1 lands. The profile is a linear sweep plus a recursive-descent trace
seeded from 42F6H and the 106 fake-line body addresses; `z80/disasm.py`
decodes all 8,068 instructions with zero undecodable, and every count in
this file was produced by resolving addresses through the table rather
than by matching text (CLAUDE.md, "corpus counting traps").
