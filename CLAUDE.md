# CLAUDE.md — session bootstrap for trs80_z80_core

You are in the planning space for a Z80 core in PYTHON 3 that will give
the TRS-80 LEVEL II BASIC interpreter (../trs80basic) the
ability to execute machine-language routines called from BASIC via USR.
It attaches to the awk interpreter as a persistent coprocess with a
stub fallback (language and seam RULED 2026-08-13 — see DESIGN.md).

READ ORDER on a fresh session (local files only — cross-repo pointers rot,
so they live in COMPANION REPOS below and are not part of the read order):
1. README.md (one screen: what and why)
2. Z80_FINDINGS.md — start at "THE GATE NUMBER"; 24 numbered findings.
   FINDING 24 (2026-09-09) is the most recent and corrects three
   documents, FINDING 19 among them — read it before quoting anything
   about Dancing Demon.
3. DESIGN.md (the authoritative context: language/seam ruling, staged
   plan incl. Phase A, technical reference, testing strategy, the gate,
   decisions)
4. DANCING_DEMON.md (the north-star acceptance case as a work-item
   ledger, DD-1..DD-17: core, protocol, interpreter-side dependencies,
   and an explicit do-not-build-on-spec list). Read it when the topic is
   Stage 1 shape, the protocol, or what "does it run Dancing Demon"
   actually requires.
5. PROTOCOL.md (the USR coprocess contract, version 1, MIRRORED from
   trs80basic 2026-09-11 — the two copies must stay byte-identical, so
   never edit it here; changes come from that side). Read it before
   writing any protocol or frame code: it is the core's acceptance bar
   (DD-17).
6. The two docstrings that ARE the core, since 2026-09-12: `z80/cpu.py`
   (the execution core — what is modelled and why, how decode consumes
   the table) and `z80/coprocess.py` (the machine around it — frames,
   sentinel, the three HLE traps, streaming, ticks, the fixture's
   entry-address mapping, the one known port-FFH divergence).

COMPANION REPOS — this is an INDEPENDENT project with two peers, not a
sub-project of either. Neither is a "parent".
- `../trs80basic` — the TRS-80 LEVEL II BASIC interpreter this core attaches
  to. Integration shape ratified 2026-09-04: COMPANION ENGINE, NEVER
  VENDORED — a p77 shim in trs80basic, `TRS80_Z80` discovery, releases may
  bundle. BUILT AND MERGED 2026-09-11 (their `cc57dfc`, fast-forwarded
  into main the same day by the user): `src/p77_z80.awk` is the shim,
  `programs/tests/z80_stub.py` is the REFERENCE IMPLEMENTATION OF THIS
  SIDE (canned behaviour per entry address 7000H-700AH), and
  `sh programs/tests/z80.sh` is the conformance suite; `t32` runs the
  protocol in a transcript and needs `TRS80_Z80="python3
  programs/tests/z80_stub.py"`. Their bar is t1-t33 as of that day. The
  shim does not adapt to the core. Its working notes are
  `STATUS.local.md` there (gitignored — exists only in a local checkout),
  which holds the coordination entries "Machine-language call support" and
  "Program-memory mapping". TWO MORE THINGS THERE as of 2026-09-08:
  `handoff/to-trs80-z80-core.md`, their half of the channel — gitignored on
  that side like STATUS.local.md, so it exists only in a local checkout;
  READ it, NEVER write it. And, COMMITTED in their `fe99d4b`, in
  `src/p75_mem.awk`, **"THE ADDRESS-RESOLUTION CONTRACT"** — the six-rule
  precedence order `dopeek` resolves a byte by, written at this project's
  request as a contract the core must reproduce exactly. It is the single
  most load-bearing thing on that side for core work.
- `../awk_BASIC_interpreter` — the private CORPUS ARCHIVE, measurement data
  only (`programs/`, `programs/runnable/`, `OCRsamples/`, `blocked/`). It
  is NOT the interpreter any more; that moved to trs80basic on 2026-08-28.

REFERENCE LIBRARY (assembled 2026-09-05 — scanned books, not code; local
only, never committed): 21 PDFs selected for this project after a
table-of-contents scan of all 76 documents in `../trs80_references/`,
plus 16 more in a `goal2/` subdirectory for goal (2), magazine listings
(the ten Wayne Green Encyclopedia volumes, Barden's subroutine book, the
Richcraft Disassembled Handbooks, Custom TRS-80, TRS-80 Graphics).
**THE PDFs MOVED OUT 2026-09-08** at the user's direction, to an archive
whose location this side has not been told; `../trs80_references/
trs80_z80_core/` now holds only `md/` (36 MB, was 531 MB). The TEXT
LIBRARY below is unaffected and is what you actually read. Ask the user
for the archive path if you need a PDF, and set `TRS80_PDF_ROOT` to it —
`split_core.py` and `verify_library.py` both pick it up, and only
re-OCR (`build_core_library.py`) is blocked without it. The book-to-PDF
paths survive in `md/_tools/pdf_manifest.json`; do not delete it (see
that directory's README for why a rebuild without it silently destroys
the `goal2/` provenance). Which to reach for:
- HLE trap semantics (documented behaviour only): ROM Routines Documented
  (has the Model I vs III entry-point comparison), the Micro-80 Level II
  ROM Reference Manual (text layer), Farvour "Microsoft BASIC Decoded"
  chapters 2 and 4 ONLY — its chapters 7-8 are commented ROM disassembly
  and fall under the NEVER-commit rule, as do Richcraft volumes 1-2.
- Opcode table / T-state cross-checks: **Sybex "Programming the Z-80" 3rd
  ed. FIRST** — measured 2026-09-08, it carries timing language on 151 of
  its 630 pages against Leventhal's 19, the Zilog manuals' 12 and 10, the
  Osborne "Z80 Programming for Logic Design" 9 and the Reston Z80 Users
  Manual 6. It was named nowhere in this file until that audit, which had
  been sending this work to the weaker sources for a month. Then Zilog,
  Leventhal, Reston, Osborne as corroboration; the Nano Systems reference
  card lists the undocumented IX/IY half-register instructions.
  The two Zilog manuals ("Z-80 CPU Technical Manual" and "Z80 and Z80A
  Technical Manual", both 1977) are TWO SCANS OF ONE BOOK — same section
  numbering, same figures, 83 vs 82 pages. They can never corroborate each
  other. Their use is the opposite: when OCR mangles a hex table in one,
  read it in the other. The Z80/Z80A scan is the better one.
- Loader idioms the extractor classifies (string packing, DATA/POKE, array
  packing, USR argument passing): Barden "More TRS-80 Assembly-Language
  Programming" **chapter 5, titled "Embedded Machine Code in BASIC"**
  (p. 102, part 5) — the single most on-target chapter in the library for
  goal (1), and the place to start; then its ch. 4 (loading and executing),
  Level II ROMs (Tab) ch. 2-3, Fast BASIC part II (the five BASIC tables,
  VARPTR — VARPTR appears on 49 of its pages, USR on 35).
- Model I address-space side effects: the 1978 TRS-80 Technical Manual has
  the memory map and the **3800H keyboard** matrix (pp. 6 and 12) and that
  is ALL it has — measured 2026-09-08, its 42 pages (the whole PDF; not a
  truncated scan) contain no occurrence of 3C00, 15360, "port FF" or "FFH"
  by any spelling. This file claimed it as the source for all three until
  that audit. For the **3C00H video base** go to Encyclopedia Vol 04 or
  Fast BASIC (12 pages each), TRS-80 Graphics (11) or Custom TRS-80 (10).
  Assembly Language Made Simple ch. 4 for the memory map.
- Books in the library with no other assignment, and what they are for:
  Osborne "Z80 Assembly Language Subroutines" (512 pp) and the Sams
  "Z-80 Microcomputer Handbook" (308 pp) are general Z80 routine and
  hardware references for goals (3)-(4); Prentice Hall "TRS-80 Assembly
  Language" (194 pp) and Radio Shack "TRS-80 Assembly Language
  Programming" (226 pp) are TRS-80 assembly tutorials. The "Level II BASIC
  Reference Manual" (196 pp) and the "Model 3 Operation and BASIC Language
  Reference Manual" (274 pp) are BASIC-side and belong to trs80basic's
  domain, not this one — the Model III manual in particular measured 0 ROM
  entry points, 0 timing content and 0 assembly-listing pages, and its one
  distinctive job (Model I vs III) is already done better by ROM Routines
  Documented, which carries both models on 19 pages. Do not reach for
  either of those two for core work.
- SAFE, contrary to what the volume number suggests: Richcraft
  "Disassembled Handbook" **Volume 3 is not ROM disassembly** — measured
  2026-09-08 at 0 pages of ROM-range disassembly. It is about WRITING a
  disassembler (a BASIC disassembler contest), which makes it the
  library's most on-point book for goal (4). The never-commit rule above
  names volumes 1-2 for exactly this reason and is correct as written.
TEXT LIBRARY (built 2026-09-05/06, rebuilt 2026-09-07 and 2026-09-08) —
`../trs80_references/trs80_z80_core/md/`: all 37 PDFs (10,063 pages)
OCR'd to `md/_full/<book>.md` and split on page boundaries into
`md/<book>/part-NN_pages-AAAA-BBBB.md` (336 parts, each one read), with
a per-book `INDEX.md` and, for 18 listing-heavy books, an `ADDRESSES.md`
mapping address -> line -> page. Top-level `md/INDEX.md`. **Grep the
book directories OR `_full/`, not both** — same text. Parts are
chapter-aligned, and a page-map cell says what its page holds (a
heading, a listing's address span, or an honest "(no heading
recognized)"). Regenerate with `md/_tools/` (build_core_library.py,
split_core.py, audit_library.py, README.md — read that README before
changing the splitter). 36 MB, outside the repo, NEVER committed: it
contains OCR of ROM disassembly.
AUDITED 2026-09-08 against the source PDFs and `_full/`, by a checker
built independently of the generator so a bug in it could not hide
itself — kept as `md/_tools/verify_library.py`, run it after any
rebuild, it exits non-zero on any finding. The generated tables of
contents are STRUCTURALLY EXACT: page counts matched `pdfinfo` 37/37,
parts cover every page once with no gaps or overlaps, 8,864 page-map
rows and 16,921 address-index rows all point at the right
part/page/anchor, every address-index line is verbatim on the page it
cites, and 37/37 books are lossless. Every defect found was in the AUDIT
INSTRUMENT (it was skipping 6% of rows and never reading landmark
titles, so it reported 64% useful where the honest figure is 61%) or in
a LABEL (10 landmarks named after OCR debris; 3 appendices named for a
divider tab). All fixed and rebuilt the same day; see
`md/_tools/README.md`, "What the audit says about it".
**Seven books have NO detected chapter landmarks** — their `INDEX.md`
says `**None detected.**` — so the "one chapter is one part" rule does
not hold for them; three are large (Z80 Users Manual 338 pp,
Encyclopedia Vol 01 288 pp, Barden's Subroutines 244 pp). Navigate
those by the page map.
NOTE the books cannot validate the opcode table's T-states wholesale —
their instruction tables OCR to 0-1 parseable rows each. The one
exception is FINDING 21. This is a limit of the OCR, not of the books,
and it does not contradict the Sybex recommendation above: Sybex's 151
timing pages are prose and per-instruction discussion, which survive OCR
and support SPOT checks, while the column-aligned summary tables that
would allow a wholesale diff do not survive in any book. Wholesale
validation still needs a machine-readable source, not a scan.
AND THE SPOT CHECK MEANS THE PDF, NOT THE OCR. Every index in the text
library ends with "find the page, then read the value off the PDF", and
that is not boilerplate — the OCR is untrustworthy for exactly what the
core needs: hex, timing, opcodes, listings. FINDING 21 came from reading
a page. Since 2026-09-08 that costs a trip to the archive; take it
anyway for anything load-bearing, and never promote an OCR'd hex value
to a measurement because the PDF was inconvenient.
The user reorganises that tree themselves (BASIC-side books sit in
`../trs80_references/trs80basic/`, parked items in "Future reference"), so
search the whole tree before assuming a file's location.

WHERE THINGS STAND (audited 2026-09-04 against the companion repos, a
sweep re-run, and the session records; the 2026-08-14 handoff had
missed two same-day events, recorded below. EXTENDED 2026-09-06/07 with
the reference-library cross-check, FINDINGS 21-23, and the goal-(1)
rulings — those bullets carry their own dates.)
- THE GATE IS RULED. Measured to completion 2026-08-14: gate number
  **6** (Phase A 5; the oracle added varptr/engindb3.bas). The gate
  never set a numeric threshold. The user RULED the same day, in the
  companion session (recorded in awk_BASIC_interpreter's
  PROJECT_MAP.md, "set 2026-08-14"): the rescue count does not justify
  the core and no longer has to — the project is re-founded on its own
  merits. The user's words: "I do want to have a standalone
  assembler/de-assembler in addition to the in-BASIC machine code
  handling." FOUR GOALS, in the user's priority order: (1) run BASIC
  programs that contain embedded machine code — string packing,
  DATA/POKE loaders, USR — i.e. the core plus a thin optional bridge;
  (2) extract assembly-language listings from magazines and run them
  (probably an OCR revisit); (3) write new assembly, "for the joy of
  it" — needs the assembler; (4) disassemble, e.g. the code embedded in
  BASIC programs — mostly built. Stage 1 planning proceeds from these
  goals, not from the gate number.
- THE BIG-PICTURE TALK IS CLOSED (user, 2026-09-07). It had gated
  Stage 1 since 2026-08-14. The user's purpose in asking for it was to
  step back far enough to see what was being worked on — "I got lost in
  some of the details" — and that purpose is served; it was never an
  agenda of open questions. WHAT REPLACES IT AS THE ACTIVE WORK: nail
  down GOAL (1), integrating machine code into BASIC programming, which
  the user calls the highest bang-for-the-buck piece. Detailed protocol
  handshaking is still NOT the topic yet.
- STAGE 1 IS BUILT ON THIS SIDE (2026-09-12; the user gave the go
  ruling that day). `z80/cpu.py` is the execution core — decode is a
  consumer of `z80/table.py`, closures pre-built into seven 256-slot
  pages — and it passes ALL 1,604,000 pinned single-step vectors
  (`tests/test_cpu_vectors.py`, `Z80_VECTORS=all`), which also validates
  the cycle column by execution; measured 2.1-2.7M insn/s against the
  313K bar. `z80/coprocess.py` + `core.py` are PROTOCOL.md's core half:
  trs80basic's `sh programs/tests/z80.sh` passes with
  `TRS80_Z80="python3 ../trs80_z80_core/core.py --fixture"` (DD-17) and
  their t32 transcript is byte-identical to the stub's; 126 tests green
  (`python3 -m unittest discover -s tests`). Commits e5dd614, 3eb73d6.
  [SUPERSEDED that day, kept for the record: "STAGE 1 IS NOT STARTED ON
  THIS SIDE. No opcode-execution code exists here and no protocol code
  exists here; `z80/` is still the table and the disassembler."]
  THE INTERPRETER'S HALF WAS DONE FIRST (2026-09-11): the
  protocol is written (PROTOCOL.md, mirrored here), the shim is on their
  main, and the go ruling for the core build was the user's — GIVEN
  2026-09-12, see WHERE TO PICK UP. Constraints ratified 2026-09-02 and
  still standing, now all embodied in PROTOCOL.md: companion engine,
  never vendored; p77 shim in trs80basic; TRS80_Z80 discovery; releases
  may bundle; the first protocol message carries a version and a
  mismatch is a clean error. Dancing Demon stands as the
  north-star acceptance case: call-and-return USR is not enough for that
  class of program. RE-MEASURED 2026-09-09 — read FINDING 24 and
  `DANCING_DEMON.md`, not FINDING 19 alone: the payload is a
  self-relocating dispatcher that walks the BASIC line-record chain, it
  DOES call the ROM (01C9H/CLS x4), it needs a Z80 stack inside the 64K
  (placed 2026-09-11 — DD-4 below), and it is fully position-independent.
  It does NOT need a writable program image.
- RULED 2026-09-07 in the goal-(1) discussion, three assumptions the
  user put and this side agreed with one correction:
  (a) ONE GENERAL ENGINE, not a per-program package. The core is a
      general Z80 the interpreter drives at run time; a listing's
      machine code is just bytes loaded into the shared image. Nothing
      is pre-packaged per program. This is the ratified companion-engine
      shape and it is what lets the same engine serve goals (2)-(4).
  (b) THE CORE IS OPTIONAL and the interpreter degrades without it —
      correct, but "no-op" is the wrong word and the difference matters.
      The shipped stub EVALUATES AND RETURNS THE ARGUMENT (USRn(x) -> x).
      CORRECTED 2026-09-11: it had NO notice at all until that day; it now
      prints ONE stderr line per run tallying the calls not executed by
      entry address, and TRS80_USR=strict raises ?FC (interpreter commit
      a46b5da).  POKEd machine-code bytes still land in
      mem[], so only EXECUTION is stubbed and the memory image stays
      consistent for a later core. The measured hazard: 8 of the 11
      trs-80.com string-packing techniques fail SILENTLY today — a
      side-effect routine produced no effect, no error, exit 0 — which
      is what the per-run tally now answers. Whether the fallback should
      get louder STILL is not ruled, but it is no longer silent, and
      PROTOCOL.md "Fallback" fixes the current behaviour as contract.
  (c) 64K IS A HARD CEILING and no interpreter generosity changes it —
      the Z80 address bus is 16 bits, so 65,536 bytes, of which a fully
      expanded Model I gives 48K of RAM (4000H-FFFFH) and we can offer
      all of it. The asymmetry the question sensed is real but works
      the other way: BASIC program text, variables and strings live in
      the interpreter's awk structures, NOT in the 64K, so they do not
      COMPETE for it — assembly gets more USABLE room than a real 48K
      machine ever gave, without the address space growing. Two live
      consequences: ROM is absent (0000-2FFF holds no bytes, by the
      never-commit-ROM rule), so code that READS the ROM cannot be
      served, only code that CALLS documented entry points; and a BASIC
      program can outgrow the 42E9H window that shows it — RULED
      2026-09-11 on the interpreter side (their `9036f81`): the image
      TRUNCATES at a whole line before RAMTOP, writes the 00 00
      terminator there, 40F9H reports that end, one stderr note per
      build; the last visible next-line link is never garbage, which is
      what a chain walker of the Dancing Demon kind needs. Bank
      switching is the only honest extension if 64K ever binds; widening
      the bus is rejected. Full treatment in DESIGN.md "The address
      space".
- THREE INTERPRETER-SIDE MEMORY-MODEL ISSUES FOUND 2026-09-07 while
  working goal (1), all MEASURED with runnable reproductions, all
  REPORTED not fixed (we do not edit trs80basic), all handed over in
  `handoff/to-trs80basic.md`.
  **ANSWERED 2026-09-08 — the channel round-tripped TWICE. Two shipped
  (their `fe99d4b`), one measured at zero and deferred by agreement; their
  side is `../trs80basic/handoff/to-trs80-z80-core.md` (gitignored there,
  local only) and ours is the REPLY / REPLY 2 sections of
  `handoff/to-trs80basic.md`.** Verified from this side, not taken on
  faith (t1-t31 exit 0, repros flipped, build invariant holds).
  **THE DURABLE ARTIFACT IS NOT ANY OF THE THREE FIXES — it is "THE
  ADDRESS-RESOLUTION CONTRACT" now written in `../trs80basic/src/
  p75_mem.awk`**, six precedence rules the core MUST reproduce
  byte-for-byte or it will execute the wrong bytes with no error. Read it
  before writing any core memory path. THE WRITE HALF, asked 2026-09-08,
  is CLOSED: the write contract shipped 2026-09-09 (their `efc1c02`) and
  the store primitive is `poke_byte` (their `a42c41a`, `src/p80_stmt.awk`;
  `st_poke` is now only the POKE parser in front of it). The core never
  reproduces either side: PROTOCOL.md rules that the frame IN is built by
  `fr_build` reading every defined address through `dopeek` (so every
  byte is what PEEK would return, unlisted addresses read 255) and the
  write-set OUT is applied through `poke_byte` (so a Z80 store lands
  where a POKE would). The four asymmetric write ranges are OUT OF SCOPE
  for any image diff between the sides, by agreement. THREE THINGS A FUTURE
  SESSION MUST NOT RELEARN THE HARD WAY: (a) they found a HALF THIS SIDE
  MISSED — `POKE 16561/16562` was silently dropped too, 91 corpus listings,
  the form needing no user cooperation, and it produced a confirmed rescue
  (`wordsmth.bas`); (b) the post-fix memory resolution order changed and
  FINDING 23's `min(PMEND, HIMEM)` bound is STALE — HIMEM no longer bounds
  the shadow, `a in SPK` outranks the program image, and unwritten memory
  reads **255** not 0, so the core must model it that way to agree;
  (c) AD-HOC `grep` COUNTS OVER THIS CORPUS ARE THE WEAK LINK — they
  produced TWO wrong numbers in this one exchange, and `phasea/` produced
  none. Two independent traps. FIRST, grep silently UNDERCOUNTS: 455 of
  4,343 files (10.5%) are not valid UTF-8 and BSD grep reports no match on
  them with no error unless `LC_ALL=C` or `-a` is passed. SECOND, text
  patterns miss SPELLINGS: `POKE 16561` is also written `POKE&H40B1`, and
  low-byte-only (`POKE&H40B1,20`), so a decimal regex undercounted the
  reserve idiom 88 where the true figure is 91. `phasea/` is immune to both
  (byte-safe `latin-1` reader; `&H` literal rule plus an expression
  evaluator) BECAUSE IT RESOLVES ADDRESSES RATHER THAN MATCHING TEXT —
  which is the general rule for loader idioms. Do not publish a corpus
  number that came from a bare grep. The three items as originally reported:
  * FINDING 22 — memory reserved by MEMORY SIZE? is treated as ABSENT
    rather than PROTECTED, so the classic reserve-then-load idiom
    cannot write the reserved region. Interactive only (batch forces
    HIMEM 65535). THE ONLY ONE OF THE THREE THAT BREAKS LISTINGS WHICH
    WERE LEGAL ON HARDWARE: 61 corpus listings mention "memory size",
    36 of those also use USR. Needs RAMTOP (physical top, absent above)
    split from HIMEM (the MEMORY SIZE answer, protected between them).
  * FINDING 23 — the program image shadows POKEd bytes for any address
    below PMEND. Documented in their p75 header; what is new is the
    SCOPE. Corpus impact approximately ZERO — a legal listing cannot
    trigger it, because the shadowing condition is exactly what would
    have corrupted the program on real hardware. It matters for the
    CORE, for large or new programs, and for self-modifying payloads.
    CAUTION: an earlier estimate of "~123 affected USR listings" in
    this session was WRONG (it applied a fixed target address to every
    listing) and was corrected in FINDING 23 and in the handoff — do
    not resurrect the number.
  * `PEEK(16634)` can return >255 (measured 381, 3468) — uncapped
    PMEND high byte. Zero corpus impact, one-line fix.
- FINDING 21 (2026-09-07) — the opcode table checked against an OUTSIDE
  source for the first time, the Nano Systems reference card. SLL was
  misflagged as documented, which matters because `undoc` drives the
  inverse (assembler) index; corrected split was 1780 = 1033
  documented + 747 undocumented (previously reported 1043 + 737), and
  is **1032 + 748** since 2026-09-11, when the IM documented set was
  found inverted too (commit 7f42678; the table's decode is the core's,
  so every `undoc` flag is load-bearing).
  The card's stated timing rule (index-half = H/L form + 4 T-states)
  holds 92/92 — the first and so far ONLY external validation of any
  part of the cycle column.
- THE blocked/ RE-SCAN WAS PAID 2026-08-14 (awk_BASIC_interpreter
  9ee96ca3 + 89d9269b) and verified from this side the same evening,
  but never written into this repo until now — Z80_FINDINGS FINDING 20.
  Effect: 280 files moved to runnable/, varptr/ retired, blocked/ 1065
  → 779; the FINDING 16 cmd/ confound was measured by reachability (238
  BLOCKED-RUNS-ANYWAY) rather than re-filed and contributed ZERO to the
  gate; four of the six gate files (MAIL32, MAIL48, m3t1s2d, engindb3)
  now sit in runnable/ without any of them running to completion. The
  gate reads 2 by its literal wording and 6 by its intent.
- Built and green: the 1780-entry opcode table + disassembler, the
  extractor/classifier/sweep, the dynamic oracle (phasea/oracle.py),
  and the pinned single-step vector suite (tools/fetch_vectors.py,
  1604 files fetched into the gitignored tests/vectors/). 104 tests,
  green 2026-09-11: `python3 -m unittest discover -s tests`. NOTE the
  oracle's p60 patch point BROKE TWICE in two days (usr_resolve on
  2026-09-10, the z80_usr() call on 2026-09-11) because it matched the
  USR block's whole body; since `6c30f58` it anchors on the block's
  opening line only. A failed anchor sys.exits the build and takes the
  suite down with NO summary — a run that prints dots and then a
  "patch point ... matched 0 times" line is a red suite, not a warning.
- WHERE THE CODE LOOKS (repointed 2026-09-04): phasea/oracle.py builds
  its scratch interpreter from ../trs80basic/src and tests/test_oracle.py
  diffs against ../trs80basic/trs80basic.awk; the sweep, the oracle and
  the anchor tests read listings from ../awk_BASIC_interpreter (corpus
  only — its duplicate src/ is scheduled for deletion there). Re-
  validated after the repoint: 22 exact / 7 patched / 16 silent / 0
  contradictions, identical to FINDING 13. Sweep re-run 2026-09-04:
  4339 listings (was 4345), 560 USR listings (the sweep's classifier
  count — a plain grep for the token reports ~604, because it also hits
  USR inside REM and string text; do not mix the two), 91 unresolvable loaders
  (was 96), gate population still the same 46 files, now 17 blocked /
  29 runnable (was 25 / 21). Z80_FINDINGS.md keeps the 2026-08-14
  numbers as measured; FINDING 20 carries the deltas.
- The user's own standing view, recorded so it is not relitigated: the
  two INTERPRETER-side defects the oracle found were each worth more
  listings than the core is. Both shipped 2026-08-14 (8c38dca6, in
  awk_BASIC_interpreter's history — pre-split; that code now lives in
  trs80basic and was confirmed present there 2026-09-04).
- LATENT ISSUE, FIXED on the interpreter side 2026-09-10 (DESIGN.md
  decision 3, DD-15): the spaced-call fix used to dispatch `USR n(` as name
  `USR`, DISCARDING the slot digit. trs80basic now folds the digit into the
  name and resolves a full USR frame per call (slot, entry address from
  USRDEF[0..9] or the 408EH vector, argument) in usr_resolve(); undefined
  slots resolve to entry -1 (?FC). CONSUMED since 2026-09-11: the p77 shim
  hands the frame to the core as the `CALL` header (PROTOCOL.md).
  `TRS80_USR_TRACE=1` in trs80basic dumps the frame, `=2` dumps the whole
  memory image it would send.
- COMPANION-SIDE STATE (2026-09-04): trs80basic/STATUS.local.md's
  "Machine-language call support" entry was rewritten the same day as a
  PEER coordination entry (integration shape, seam rules, state on this
  side, what trs80basic owns) and points back at this block as the
  authoritative state here — keep the two in step when either changes.
  Still stale, reported not edited: the archive's README.md describes
  itself as the interpreter (its own STATUS already lists deleting the
  duplicate src/ as owed).
- WHAT HAPPENED 2026-09-09 (kept as history): a readiness audit of THIS
  repo against the north star, at the user's request. It re-derived
  FINDING 19 from its own prose, reproduced every number, and corrected
  FINDING 19, README and DESIGN.md on five points — FINDING 24, sections
  1-9. It wrote no core code; it sharpened what Stage 1 must build. It
  left three opens, all inside goal (1); every one was answered on
  2026-09-11, recorded below so they are not reopened.
- WHAT HAPPENED 2026-09-10/11 — THE INTERPRETER SIDE BUILT ITS HALF AND
  THE THREE OPENS CLOSED. Fourteen commits went out on trs80basic in one
  day (their STATUS.local.md lists them; main == origin/main == f4012de
  at the end of it) and two commits in THIS tree were written by that
  session with the user's permission (3614cf1, 410b9a5) — read their
  messages, they are the record. State, verified from this side:
  (i) DD-4 THE STACK IS RULED (user, 2026-09-11): SP = the interpreter's
  SSP at call time, carried as `sp=` in every CALL; the core owns SP for
  the call and pushes into its own RAM beneath it (those bytes come back
  in the write-set, so BASIC can PEEK the stack afterwards); the USR
  RETURN ADDRESS IS A SENTINEL, **2FFDH**, ruled the same day on this
  side's recommendation — DESIGN.md decision 6 (fbac111). PC entering
  0000H-2FFFH is the one fetch-time check: 2FFDH ends the frame,
  01C9H/0A7FH/0A9AH are the served HLE traps, anything else is `ERR rom`.
  The "stack grows into SPK" hazard first recorded on DD-4 was
  WITHDRAWN by its author: SSP is the BOTTOM of string space, a downward
  stack moves away from it.
  (ii) THE STUB IS NOT SILENT (their `a46b5da`): one stderr tally line
  per run, `TRS80_USR=strict` raises ?FC; see (b) above.
  (iii) THE 42E9H OVERFLOW IS RULED: truncate at a whole line; see (c)
  above. DESIGN.md's UNDECIDED is closed.
  ALSO THAT DAY: the frame's memory is NOT raw `mem[]` (their seam-audit
  finding 4 — `mem[]` holds none of the packed strings, the program
  image or the pointers, those are `dopeek` projections), so the frame
  is a CONTRACT-RESOLVED SPARSE IMAGE built by `fr_build`, full on the
  first call and DELTA after (screen, 14 constant/pointer bytes plus the
  20-byte system-variable window, every SPK cell, the image when
  rebuilt, every MEM[] address written since) — a callback per memory
  read was MEASURED OUT (12 us per gawk `|&` round trip caps a core at
  ~80,000 reads/s, a quarter of the demon's 313,030 insn/s bar) and the
  keyboard read of 3800H-38FFH is the ONLY callback. Video is STREAMED
  out during the call as `V` lines (DD-7's protocol half), `T` ticks
  carry BREAK and keep the timeout guard quiet (DD-10's protocol half),
  and the write-set comes back after `RET`, last write wins per address.
  VARPTR was made IDEMPOTENT 2026-09-10 (it used to re-allocate on every
  call, marching SSP down to ?OM; 162 corpus files call it twice on one
  string). And REPLY 9 shipped four things the core will eventually
  model but nothing asks for yet: `INP(p)` (port FFH reads 127/63 by
  screen mode, all others 255; OUT is still discarded, so an OUT (FFH)
  with bit 3 set that switches width would be seen in the core first),
  the SYSTEM-VARIABLE WINDOW (cursor, printer, clock, current line,
  AUTO, TRON cells live, +20 bytes in every frame), the 400CH BREAK
  vector honoured by value, and the device vectors 401E/401FH and
  4026/4027H seeded with the ROM driver addresses (32 corpus files
  install a custom driver at 4026H; the interpreter keeps the default
  route because it cannot run it — a future core hook, not asked for).
- WHERE TO PICK UP (state read 2026-09-11, end of session). NOTHING IS
  BLOCKED on trs80basic and nothing of theirs on us; their one remaining
  Dancing Demon item is R1, the tokenized-payload loader (DD-14),
  independent of the core. THE CORE IS NOW THE ONLY PIECE BETWEEN A
  LISTING AND A RUNNING USR ROUTINE, and its acceptance bar is written:
  DD-17, `TRS80_Z80="python3 /path/to/core" sh programs/tests/z80.sh`
  passing in trs80basic with the stub's canned entries implemented as
  real machine code — MET 2026-09-12. The docs here were audited in one
  pass on 2026-09-11 after the sentinel ruling, and again 2026-09-12
  after the build. THE AGENDA, in order:
  0. THE DANCING DEMON END-TO-END RUN is blocked ONLY on trs80basic's R1
     tokenized loader (their item, DD-14): no supported path there loads
     the 10,931-byte payload intact today (detok rewrites 14 bytes
     inside it). The core is ready for it. Once R1 lands, the two open
     questions this side could never measure before a running core —
     video traffic volume (open question 2) and how faithful the pacing
     must be to read as dancing (question 3) — can be measured.
     TWO THINGS TO KNOW BEFORE THAT RUN: (a) the ONE KNOWN DIVERGENCE —
     port FFH reads 127 here regardless of display mode, because the
     interpreter's 32/64-character mode is not in the frame; BASIC's
     INP(255) says 63 in 32-character mode. The demon's two OUTs are
     discarded (DD-6) and it never reads the port. (b) `--fixture` is
     NOT contiguous code at 7000H-700AH: the stub's entry addresses are
     one byte apart, so the fixture lays the routines out from 7100H
     and maps each canned entry to its routine; 7004H (never answers)
     and 7008H (forgets) remain harness hooks exactly as in the stub.
  1. THE USER'S STAGE 1 GO RULING — GIVEN 2026-09-12 ("Go ahead with
     #1"), and the core was built the same day (WHERE THINGS STAND).
     [Kept for the record: the standing rule
     said no core code before goal (1)'s shape was settled; the protocol,
     the stack, the frame and the overflow policy were all settled by
     2026-09-11, and the USAGE SKETCH (the session a user actually has:
     "I typed in a listing with an embedded routine, now what?") was
     offered 2026-09-09 as the instrument and never ruled on — the user
     ruled build first.]
  2. ITEMS THEIR REPLY 4 (2026-09-10) FOUND ON THIS SIDE, all
     reproduced there; (d) and (e) were FIXED 2026-09-11 (7f42678), (a)-(c)
     are still open: (a) `phasea/extract.py` finds READ/POKE
     only after a FOR on the SAME LINE, so a loader split across lines
     is filed `no-ml-in-listing` with no flag — a silent undercount in a
     published number; (b) no `STRING$`/`CHR$` recognition, so
     string-packed routines are absent from every static count; (c)
     `RESTORE` with no argument reads as "adjacent", a preceding-line
     `RESTORE` is ignored, and the POKE value expression is unpacked and
     never used (`POKE I,255-A` extracts raw DATA at confidence high);
     (d) FIXED: `z80/table.py` had the `IM` undocumented flags INVERTED
     (ED46/ED5E marked undocumented, ED4E/ED6E/ED76 documented) so the
     inverse index resolved `IM 0` to ED 4E, and `DAA`'s flag string
     marked H unaffected; both corrected, the pinned split is 1032/748;
     (e) FIXED/REFUTED: `fetch_vectors.py`'s "176 vectors" corrected to
     the measured 185; the `tests/__init__.py` claim was measured false
     here — `python3 -m unittest discover -s tests` runs 104 without it,
     because the start directory is the top level.
  3. THE PDF PAGE CHECK OWED ON THE SENTINEL: decision 6 cites the OCR
     text of two books for "2FFBH-2FFFH holds nothing"; the standing
     rule says read the page. Needs the archive path (`TRS80_PDF_ROOT`).
     It could only move the sentinel within the same five-byte tail.
  4. FOUR SMALL TO-DOS, none urgent, unchanged since 2026-09-09: DD-1,
     an extractor for the program-image idiom plus a tokenized-file
     reader (FINDING 24 section 8 carries the runnable recipe; `phasea`
     cannot currently read the north-star file at all, and
     `LargeCollection/` is outside the sweep population); give
     `z80/disasm.py` a CLI (goal (4) is "mostly built" but UNREACHABLE
     from a shell); a README "Commands and arguments" section (the
     sweep/oracle/fetch_vectors invocations exist only inside
     Z80_FINDINGS prose); and a LICENSE (GPLv3 assumed, user ruling
     still pending from 2026-08-14). A USER GUIDE was considered
     2026-09-08 and DEFERRED — there is no user-facing surface yet;
     revisit when a BASIC program with an embedded routine first runs
     end-to-end.
  NOT ON THE AGENDA, recorded so they are not re-asked: the write
  contract (closed), the stack (ruled), the overflow policy (ruled), the
  "should the stub get louder" question (answered by the tally; the
  further question is dormant, not open), and the protocol's shape
  (ratified and built — the core conforms to PROTOCOL.md, it does not
  negotiate it).

STANDING RULES (do not relearn these the hard way):
- PHASE A BEFORE THE CORE (DESIGN.md "The gate") — SATISFIED 2026-08-14,
  AND THE GATE IS PASSED: the core was built 2026-09-12 on the user's
  go ruling, after every measurement the rule asked for was in.
  The rule's discipline stands for the next build.
  kept because the discipline recurs: the first artifact was the static
  disassembler/classifier over the corpus archive's DATA/POKE loader
  bytes, and no opcode-execution code was written until its numbers
  were in and the user had ruled (see WHERE THINGS STAND). Phase A
  itself was in-gate (measurement, not emulator) — confirmed with the
  user 2026-08-13. The same rule applies to the next build: measure
  before building. The big-picture talk that used to be the next
  reviewed stop was CLOSED 2026-09-07; goal (1)'s shape was settled
  piece by piece through 2026-09-11 (protocol, frame, stack, overflow);
  the next reviewed stop is the user's Stage 1 go ruling (WHERE TO PICK
  UP, item 1), and no core code before it.
- ANCHORS BEFORE TRUST (Phase A discipline, ruled 2026-08-13; wording
  corrected 2026-08-14): validate before believing, in this order.
  (1) The opcode table must pass a validation set against known-good
  disassembly BEFORE any classifier output is trusted. (2) The
  classifier must be checked against the two ground-truth anchors —
  Space Chase and ENDGAME/BAS SCAN3 — and its buckets for them
  reconciled with the evidence, BEFORE its corpus-wide counts mean
  anything. A count produced without both checks passing is not a
  measurement. (The corpus project's standing lesson — plausible
  heuristics die
  under measurement — applied prophylactically.)
  NOTE, and the reason the wording changed: this rule originally said
  the classifier must bucket endgame as a KEYBOARD scan. It is not one.
  SCAN3 is the event-clock scan and is PURE COMPUTE, with no
  3800H-38FFH access anywhere (Z80_FINDINGS FINDING 2, corroborated by
  awk_BASIC_interpreter's own FINDING 29 notes and by line 1240's
  `KJ=USR 1(VARPTR(IC(1)))`). The anchor earned its keep by refuting
  its own stated expectation — so the rule is "check the anchor", never
  "make the anchor come out the way we assumed". An anchor that cannot
  be wrong is not an anchor.
  (3) Applies to any NEW measurement instrument too, not just the
  classifier: the dynamic extraction oracle was validated against the
  payloads static extraction already resolved, and had to contradict
  none of them, before its output on the unresolvable 96 counted
  (FINDING 13).
- THE GATE RULING IS A REVIEWED CHECKPOINT (DONE 2026-08-14; the
  pattern stands for the next checkpoint): Phase A ended in a findings
  document (Z80_FINDINGS.md, numbered like basclean's) plus the gate
  count, presented to the USER for the go/no-go ruling on the core.
  Do not slide from measurement into building in the same breath —
  present, stop, and let the user rule (they may bring a heavier
  review to the numbers).
- NEVER commit ROM bytes, ROM disassembly text, or verbatim code from
  ROM-derived repositories. HLE traps are reimplemented from documented
  behavior only. (Same rule that kept the interpreter repo releasable.)
  The downloaded JSON test-vector suites are also never committed:
  fetch script + gitignore.
- HANDOFF CHANNEL to trs80basic (convention set by the user 2026-09-07):
  `handoff/to-trs80basic.md` in THIS repo carries findings owed to the
  interpreter; the user points that session at the file. The mirror,
  `trs80basic/handoff/to-trs80-z80-core.md`, is THEIRS to create and
  ours to read — never write it. Keep the file self-contained (that
  session does not share our context), give every item a runnable
  reproduction, and say plainly what is a defect versus a design call
  that is theirs to decline.
- ALWAYS `cd` BACK, OR USE ABSOLUTE PATHS / `git -C`. The Bash tool's
  working directory PERSISTS between calls, so a `cd ../trs80basic` to
  read something leaves later commands pointed there. On 2026-09-07 a
  `git add -A` intended for this repo ran in trs80basic that way. It
  staged nothing — that session had just committed, so the tree was
  clean — and no commit was created, but the command should never have
  reached that repo. Address every git command with `git -C <abs path>`.
- DO NOT EDIT trs80basic AT ALL (user, 2026-09-07). Not main, not a
  development branch, not its docs. READ it freely — the oracle builds
  a scratch copy of its src/ and that is fine, because it modifies
  nothing there. Everything owed to that side is REPORTED, and the user
  makes the change: a defect, a patch offered as text, the p77 shim,
  the call frame carrying the slot digit, TRS80_Z80 discovery. This
  TIGHTENS the 2026-09-04 rule (development branch, never main), which
  had itself replaced a "documentation only, ask first" rule from
  2026-08-14. The incident behind the whole lineage is the thing to
  avoid: "make the changes in the parent" was meant as "update the
  docs" and was read as authorization to patch interpreter source.
- Interpreter-owned items (string packing/VARPTR, program-memory
  mapping) stay in trs80basic — do not build them here. (Keyboard-matrix
  PEEK and the USR stub shipped there 2026-08-13; VARPTR/string packing,
  program-memory mapping, and the FINDING 8 DEF USR parse fix shipped
  there 2026-08-14, as did the FINDING 16/17 fixes — the 400CH DOS probe
  and the USR call-site space. Note: the interpreter's VARPTR does NOT
  give integer arrays a contiguous 2-byte image — VARPTR-array loaders
  still route through the extractor; see DESIGN.md.)
- trs80basic's regression bar is part of THIS project's bar, even
  though we no longer edit that repo (see the DO-NOT-EDIT rule above).
  Anything we ASK for there must leave t1-t33 exiting 0 (t7's RND line
  varies run to run; t13 wants their ollama stub; t32 needs
  `TRS80_Z80="python3 programs/tests/z80_stub.py"`) and batch exit codes
  unchanged, and the coprocess fallback path (no `TRS80_Z80`, or no
  python3) must behave exactly like the shipped stub — which is now
  CONTRACT, PROTOCOL.md "Fallback". The count was t1-t28 when this rule
  was written and t1-t31 on 2026-09-08; it grows on their side.
  So a change proposed in handoff/to-trs80basic.md states its expected
  effect on that bar; and when we measure the interpreter to produce a
  finding, baseline first so "unchanged" is a diff and not a belief.
- Commit with `git commit -F <msgfile>`; use absolute paths in shell
  commands; every increment committed and green before the next.
- Remote: private GitHub davidscan/trs80-z80-core (created 2026-08-14 at
  the user's direction; hyphenated to match the naming
  of the repo that was then the parent). KEEP IT PRIVATE — the findings quote one-line loader
  excerpts from magazine listings. No LICENSE file yet (user ruling
  2026-08-14); GPLv3 mirroring trs80basic remains the default assumption
  when one is added.
