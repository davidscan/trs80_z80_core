# To the trs80basic session — memory-model findings from trs80_z80_core

**Written 2026-09-07 by the trs80_z80_core session. Direction: core → interpreter.**
Three items, all interpreter-owned. Each is measured and reproducible; run the
repros before taking any of it on faith.

**I did not and will not edit trs80basic.** Standing rule from the user
(2026-09-07): no edits there at all — not `main`, not a development branch, not
docs. Everything is reported; the change is yours to make or decline. Reading
your `src/` is all I did, plus `phasea/oracle.py`'s instrumented scratch copy,
which modifies nothing in place.

**Authoritative detail** (all committed in `../trs80_z80_core`):
- `Z80_FINDINGS.md` — FINDING 22 (protected vs absent RAM), FINDING 23 (program
  image shadows POKEs)
- `DESIGN.md` — section "The address space", for the invariant these sit under

**Context you may not have:** this repo is building a Z80 core that will attach
to trs80basic as a companion coprocess for USR. Nothing below blocks your public
release unless you decide it does — see "What I am not asking for" at the end.

---

## Triage

| # | Item | Breaks legal legacy listings? | Corpus population | Fix size |
|---|---|---|---|---|
| 1 | MEMORY SIZE reserves unusable memory | **YES**, interactively | 36 listings | small |
| 2 | `PEEK(16634)` can return > 255 | no | 0 | one line |
| 3 | Program image shadows POKEd bytes | no (see correction) | ~0 | design call |

---

## 1. Memory reserved by MEMORY SIZE? cannot be written — the region is treated as ABSENT, not PROTECTED

**Highest real-world impact of the three, because it breaks listings that were
legal on hardware.**

### Reproduce (from your repo root)

```sh
printf '32000\n10 POKE 40000,123\n20 PRINT "PEEK 40000 =";PEEK(40000)\nRUN\nBYE\n' \
  | TRS80_DUMB=1 gawk -f trs80basic.awk
```
→ `PEEK 40000 = 255`, and the poked byte is gone.

Control — press ENTER at the prompt instead of reserving:
```sh
printf '\n10 POKE 40000,123\n20 PRINT "PEEK 40000 =";PEEK(40000)\nRUN\nBYE\n' \
  | TRS80_DUMB=1 gawk -f trs80basic.awk
```
→ `PEEK 40000 = 123`. Works.

### Mechanism

`src/p80_stmt.awk` — `st_peek`: `if (a > HIMEM) return 255`; `st_poke`:
`else if (a > HIMEM) { }`. Both treat above-HIMEM as absent RAM.

### Why it is wrong

On a Model I the MEMORY SIZE? answer does not make memory absent. It makes it
**protected** — present, readable, writable RAM that BASIC will not allocate
into. That is the entire purpose of the prompt, and the region is exactly where
machine code is meant to live. The classic idiom is therefore half-implemented:
the shielding works (string space correctly descends from HIMEM), but the
reserved region cannot be written.

### Corpus impact — measured

**61** listings in `../awk_BASIC_interpreter/programs/{runnable,blocked}` mention
"memory size"; **36 of those also use USR** — the exact intersection where a
listing says "reserve memory, then load machine code there". Magazine text
instructing this is real: *Encyclopedia for the TRS-80* Vol. 1 tells the reader
to "set the memory size to 32697 in order to reserve room for" a routine.

Caveat: mentioning MEMORY SIZE does not prove a listing POKEs above it. 36 is
the candidate population, not a confirmed failure count.

Batch mode is unaffected — it forces `HIMEM = 65535`, so nothing is ever above
the ceiling. This is interactive-only.

### What it needs

Two quantities where there is currently one:

- **RAMTOP** — the machine's physical RAM top (FFFFH for 48K). Above it memory
  genuinely is absent: 255 on read, discard on write. Authentic, keep it.
- **HIMEM** — the MEMORY SIZE? answer, at or below RAMTOP. Between HIMEM and
  RAMTOP is **protected RAM**: present, readable, writable, simply never
  allocated by string space.

`PEEK(16561/16562)` keeps reporting HIMEM (already correct). `sp_materialize()`
keeps descending from HIMEM (already correct). Only the two absent-RAM tests
change, to test RAMTOP. This also gives "what size machine is this?" a single
home, which the core will need to agree with.

---

## 2. `PEEK(16634)` can return a value greater than 255

Plain bug, independent of everything else. A PEEK must return 0–255.

### Reproduce

Any program whose tokenized image exceeds ~48 KB, so `PMEND > 65535`:

```sh
python3 -c 'print("\n".join("%d REM %s"%(10+i,"X"*60) for i in range(1200)));
print("9000 PRINT PEEK(16633);PEEK(16634)")' > /tmp/big.bas
./basic /tmp/big.bas < /dev/null
```
Measured: **381** for a 1200-line program, **3468** for a 13000-line one.

### Mechanism

`src/p75_mem.awk` — `pm_sysptr()`: 40F9H/40FAH serve `PMEND % 256` and
`int(PMEND / 256)`, uncapped.

### Impact

Zero on the corpus — the largest listing is 43,960 bytes of source, and none
reaches the ~48 KB tokenized threshold. It affects new or generated programs
only. Listed because it is unambiguous and cheap, not because it is urgent.

---

## 3. The program image shadows POKEd bytes — and a correction to my own first estimate

### The behaviour

`pm_build()` serialises the program from 42E9H upward and sets
`PMEND = 17129 + crunched size + 2`. `st_peek()` then resolves any address in
`[17129, min(PMEND, HIMEM)]` from `PMEM[]`, while `st_poke()` writes `MEM[]`.
The two never meet, so a POKE below PMEND is written and then invisible.

This is documented in your own `p75` header ("POKEs into the region land in MEM
and are never read back — the WRITABLE mapping (self-modifying code) stays
unbuilt"), so the mechanism is not news to you. What follows is scope.

### Reproduce

```sh
python3 -c 'print("\n".join("%d REM %s"%(10+i,"X"*60) for i in range(300)));
print("9000 POKE 20000,222 : PRINT PEEK(20000)")' > /tmp/med.bas
./basic /tmp/med.bas < /dev/null
```
→ prints **88** (`X`, the program image) instead of 222. At 13000 padding lines
every address from 20000 to 65000 returns 88.

### CORRECTION — I first estimated this as ~123 affected USR listings. That was wrong.

I applied a fixed target address (32000) to every listing. Real listings each
have their own target, and that changes the conclusion:

**A legal legacy listing cannot trigger this.** Shadowing requires
`POKE target < PMEND`, i.e. the routine landing inside the program's own image —
which on real hardware is precisely the condition that would have corrupted the
program. A 20 KB program cannot legally POKE at 32100, because its own image
already reaches 37129; such a listing targets 40000 or 60000 instead. The target
always sits above PMEND in anything that ran on hardware.

So the corpus impact is **approximately zero**, and magazine/book listings are
fine on this axis. Please do not prioritise this from my earlier number.

### Where it does matter

- **For the Z80 core**, which is why it is here: once something executes what was
  poked, a silently-empty region becomes a wrong answer with no error.
- **For new or large programs** — the threshold is `target - 17129` bytes, about
  14.8 KB for a routine at 32000. That is an ordinary size for a modern program.
- **Self-modifying code** in the program image is unsupported at any size, which
  matters for us: the Dancing Demon payload lives inside the program image at
  42F6H rather than in a loader.

### A question I cannot answer and you may be able to

**Does any corpus listing POKE a routine and then verify it by reading it
back?** A checksum-verifying loader would fail *visibly today*, with no core
involved — that would move this from "matters after the core" to "matters now".
I have not measured it and it is closer to your tooling than mine.

---

## What I am not asking for

Priority is yours. These came from reading your code against a goal that is not
yours, and without the core none of it produces a visible failure except item 1.
A program whose POKE loader silently deposits nothing was already a program that
did nothing. Item 1 is the only one I would call a real defect in shipped
behaviour; item 2 is a freebie; item 3 is a design decision that the core will
eventually need settled, not a bug report.

If you disagree with any of it, say so — I would rather be corrected than have
you build to a wrong assumption of mine. The `123` correction above is exactly
why.

## Reverse channel

The user proposed a symmetric convention. This file is
`trs80_z80_core/handoff/to-trs80basic.md`. The mirror would be
`trs80basic/handoff/to-trs80-z80-core.md` — yours to create; I will not write
into your repo. Findings you have that bear on the Z80 core, the USR seam, or
the memory model belong there and I will read it.

Also note, still open on your side and recorded in your STATUS: the spaced-call
fix dispatches `USR n(` as name `USR`, discarding the slot digit. Harmless under
the stub, but the coprocess call frame must carry the slot, so that dispatch
point needs to pass it through when the plumbing is built.
