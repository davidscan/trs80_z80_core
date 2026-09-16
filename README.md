# trs80_z80_core

## What it is

A Z80 CPU emulator in Python 3 that executes the machine-language routines
TRS-80 LEVEL II BASIC programs call with `USR`. It runs as a companion
process to [trs80basic](https://github.com/davidscan/trs80basic), the BASIC
interpreter, so embedded machine code (`DATA`/`POKE` loaders, string-packed
routines) actually runs. The routine works on the same memory `PEEK` and
`POKE` see; its video writes appear while it runs, the keyboard is live,
and its cassette-port sound can be played or saved to a WAV file. That is
enough to run Dancing Demon, machine code and sound included. It also
includes a standalone Z80 disassembler and an assembler that reads the
Editor/Assembler syntax the period books print. It uses only the standard library,
contains no ROM bytes, and writes no files except a WAV file you name.

## Quick start

```bash
git clone https://github.com/davidscan/trs80basic                 # the interpreter (needs GNU awk >= 5.0)
git clone https://github.com/davidscan/trs80_z80_core             # this core, cloned beside it
cd trs80basic
TRS80_MHZ=1.77408 ./basic <program>.bas                           # USR routines now execute, paced to the Model I clock
```

Substitute any BASIC listing for `<program>.bas`. The interpreter finds the
core by itself when the two repositories sit side by side.

Needs Python 3, plus GNU awk 5.0 or later for trs80basic. Live sound also
needs an audio player: ffplay (part of FFmpeg) anywhere, or ffmpeg alone on
macOS, or aplay or pw-play on Linux; `ffplay -version` checks for it.
Writing a WAV file needs nothing extra.

## Commands and arguments

Everything runs from this folder with Python 3's standard library.

### `python3 core.py`

The coprocess the interpreter starts: it speaks `PROTOCOL.md` over
stdin/stdout. You don't run it by hand. **Writes:** nothing, except the WAV
file named by `TRS80_SOUND_WAV`.

| argument | default | what it does | when you'd use it |
|---|---|---|---|
| `--fixture` | off | adds machine-code routines behind the interpreter's reference stub's canned entry addresses (7000H-700AH) | running trs80basic's conformance suite against the real core: `TRS80_Z80="python3 ../trs80_z80_core/core.py --fixture" sh programs/tests/z80.sh` |

The core reads these from the environment it inherits from the interpreter:

| variable | default | what it does | when you'd use it |
|---|---|---|---|
| `TRS80_SOUND` | unset (silent) | `auto` plays through the first installed player (ffplay, then ffmpeg's AudioToolbox device on macOS, aplay, pw-play); any other value is a shell command fed raw 16-bit little-endian mono PCM on stdin, with `{rate}` replaced by the sample rate | hearing a routine's sound live |
| `TRS80_SOUND_WAV` | unset | writes the routines' audio to this WAV file, overwriting it when the core starts | keeping the sound, or checking it without speakers |
| `TRS80_SOUND_RATE` | `22050` | the sample rate for both | `44100` if your player prefers it |

These belong to the interpreter (see its README) but decide how the core is used:

| variable | default | what it does | when you'd use it |
|---|---|---|---|
| `TRS80_Z80` | the core beside the checkout | the command that runs the core; empty (`TRS80_Z80=`) means no core | a core installed elsewhere: `TRS80_Z80="python3 /path/to/core.py"` |
| `TRS80_MHZ` | unpaced | paces execution to this clock | games, animation and sound; `1.77408` is the Model I |
| `TRS80_Z80_TIMEOUT` | `5000` | milliseconds to wait for each reply from the core | a slow machine |
| `TRS80_USR` | unset | `strict` makes a `USR` call that no core executed raise `?FC` | making sure a listing never runs with its routines skipped |

### `python3 -m z80.disasm`

Disassembles raw Z80 bytes. **Writes:** nothing; the listing goes to stdout.

| argument | default | what it does | when you'd use it |
|---|---|---|---|
| `FILE` | none | the file of raw bytes to disassemble | a routine saved from memory or cut out of a program image |
| `--hex HEX` | none | the bytes as hex digits instead of a file; spaces allowed | bytes copied from a listing's `DATA` lines |
| `--base ADDR` | `0` | address of the first byte disassembled (after `--skip`), as decimal, `0x7D00` or `7D00H` | always, so the address column and `JP`/`CALL` targets match where the listing POKEs the code |
| `--skip N` | `0` | bytes to skip at the start of the file | code that follows a header or data |
| `--length N` | to the end | how many bytes to disassemble | stopping before data that follows the code |

### `python3 -m z80.asm SOURCE`

Assembles a Z80 source file written the way the period books print
Editor/Assembler listings: an optional line number, a label (colon
optional), the instruction, `;` comments; hex with a trailing `H` and a
leading digit (`0FFH`), octal `Q`, binary `B`, `'A'` characters, `$` for
the location counter; `+ - * /` and `.AND. .OR. .XOR. .NOT. .MOD. .SHL.
.SHR.`; `ORG`, `EQU`, `DEFB`/`DB`, `DEFW`/`DW`, `DEFM`/`DM`, `DEFS`/`DS`,
`END entry`. Every instruction comes from the same opcode table the core
executes and the disassembler prints from, so a disassembly listing is
valid source again. Errors are printed as `file:line: message`, all of
them, and nothing is written. **Writes:** the `-o` file and the `--list`
file; with neither, the listing goes to stdout.

| argument | default | what it does | when you'd use it |
|---|---|---|---|
| `SOURCE` | required | the source file | always |
| `-o OUT` | none | where the object goes; the extension picks the format: `.bin`, `.cmd`, `.cas`, `.bas` | producing something to load or run |
| `--format {bin,cmd,cas,bas}` | from the extension, else `bin` | `bin` a raw image (gaps between `ORG` blocks zero-filled); `cmd` a TRS-80 load module; `cas` a Model I SYSTEM tape as a byte stream; `bas` a BASIC `DATA`/`POKE` loader with a checksum, `DEFUSR` and `PRINT USR(0)` on line 60 | an output name without a telling extension |
| `--name NAME` | the source file's name | the six-character program name inside a `cmd` or `cas` file | matching what a listing expects |
| `--org ADDR` | none | the load address when the source has no `ORG` (`32000` or `7D00H`) | a fragment without one |
| `--entry ADDR` | the first `ORG` | the entry address when `END` names none | a routine whose entry is not its first byte |
| `--list FILE` | stdout when there is no `-o` | writes the listing (address, bytes, source) here; `-` for stdout | keeping the listing beside the object |
| `--symbols` | off | prints the symbol table after the listing | finding an address to `PEEK` |

### `python3 -m z80.run FILE`

Runs a machine-language program in the core with no screen and no
keyboard: a `.cmd` load module, a `.cas` SYSTEM tape, raw `.bin` bytes
(with `--org`) or `.asm` source, assembled first. The program is called
the way `USR` calls a routine, with the same three ROM entries served and
`ERR rom` for any other. Keyboard reads see no key; video bytes land in
memory and are printed afterwards as the 16 by 64 screen. It prints how
the run ended, HL, the T-states and the seconds of Model I time they
represent. Exit status 0 when the program returned or reached 0A9AH, 1 on
an error, 2 when the T-state budget stopped it. **Writes:** nothing.

| argument | default | what it does | when you'd use it |
|---|---|---|---|
| `FILE` | required | the program: `.cmd`, `.cas`, `.bin` or `.asm` | always |
| `--org ADDR` | none | the load address of a `.bin` file, or of `.asm` source with no `ORG` | raw bytes |
| `--entry ADDR` | the file's transfer address, else its first block | where execution starts | a routine whose entry is not its first byte |
| `--arg N` | `0` | what `CALL 0A7FH` fetches into HL, as `USR(N)` would | routines that take an argument |
| `--sp ADDR` | `0FF00H` | the stack pointer at entry | code that assumes a stack somewhere else |
| `--cycles N` | `20000000` (about 11 s of the machine) | the T-state budget; a program still running then is stopped | programs that never return, or a shorter wait |
| `--screen` / `--no-screen` | the screen prints if the program wrote to it | force or suppress the screen dump | checking a display routine; keeping output short |
| `--regs` | off | prints AF BC DE HL IX IY SP PC at the end | debugging a routine |
| `--dump ADDR,LEN` | none | hex-dumps that range at the end; repeatable | checking what a routine stored |
| `--quiet` | off | prints nothing but the `--dump` ranges | scripting |

### `python3 -m unittest discover -s tests`

The test suite. **Writes:** `out/oracle/`, a scratch build of the
interpreter, when `../trs80basic` is present.

| variable | default | what it does | when you'd use it |
|---|---|---|---|
| `Z80_VECTORS` | 40 cases per vector file | `all` runs every case of the CPU test vectors (about 20 s) | after any change to `z80/cpu.py` or `z80/table.py` |
| `Z80_VECTORS_FILES` | every file | comma-separated vector files, by name without `.json` (`ed b2`) or by prefix (`cb`) | reproducing one failure by the case name it printed |

Test groups skip when their input is missing: the CPU vectors until
`tools/fetch_vectors.py` has run, the anchor tests without the listing
archive, and the oracle tests without `../trs80basic` and gawk. A good run
ends in `OK (skipped=N)`.

### `python3 tools/fetch_vectors.py`

Fetches the third-party single-step CPU test vectors (SingleStepTests/z80,
MIT), pinned to the commit in `tools/vectors.lock`. With no arguments it
reports what is present and uses no network. **Writes:** `tests/vectors/`,
which is not committed; `--update-lock` rewrites `tools/vectors.lock`.

| argument | default | what it does | when you'd use it |
|---|---|---|---|
| `--all` | off | downloads the whole suite as one tarball (about 1.3 GB extracted) | once, before running `Z80_VECTORS=all` |
| `--pages P,...` | none | fetches only those pages: `main,cb,dd,ed,fd,ddcb,fdcb` | working on one prefix group without the full download |
| `--limit N` | no cap | at most N files per page | a quick smoke test |
| `--coverage` | off | compares the vectors' encodings with `z80/table.py` | after changing the opcode table |
| `--update-lock` | off | re-pins to upstream's latest commit | deliberately moving to corrected upstream vectors |
| `--force` | off | fetches again what is already present | a damaged or partial download |

### `sh tools/corelog.sh PREFIX`

Runs the core with both directions of the protocol logged. Name it as the
interpreter's core. **Writes:** `PREFIX.in` (what the interpreter sent) and
`PREFIX.out` (what the core answered).

| argument | default | what it does | when you'd use it |
|---|---|---|---|
| `PREFIX` | required | path prefix for the two logs | debugging a routine: `TRS80_Z80="sh ../trs80_z80_core/tools/corelog.sh run" ./basic prog.bas` |

### `python3 tools/render_frames.py LOG CALL MARK...`

Replays the video from a `corelog.sh` log and draws the 64x16 screen at
chosen moments, semigraphics included, as text. **Writes:** nothing.

| argument | default | what it does | when you'd use it |
|---|---|---|---|
| `LOG` | required | a `PREFIX.out` log | always |
| `CALL` | required | which `USR` call in the log, counting from 1 | a program that calls its routine more than once |
| `MARK` | required | a number N draws the screen after the call's Nth video update; `end` draws it at the call's return | checking what a routine drew without watching it |

### `python3 tools/reconstruct_screen.py CAPTURE`

Replays a raw capture of the interpreter's terminal output (for example
from `script`) into the grid a person would have seen. **Writes:** nothing.

| argument | default | what it does | when you'd use it |
|---|---|---|---|
| `CAPTURE` | required | the captured terminal bytes | telling a display bug in the interpreter from one in the routine's video |

### `python3 tools/mkgame.py`

Writes CATCH, a machine-language reflex game, as a BASIC listing with a
DATA loader and a checksum: a block falls, the arrow keys slide a paddle
along the bottom row, catching it speeds the next one up, three misses
end it, and the score comes back through `USR`. Every byte is assembled
from the opcode table's inverse index and the frame delay from its cycle
column, so the listing is generated, never hand-counted. Set a clock
first -- `speed 1.77` at the prompt -- or the frame delay runs as fast as
the host can. **Writes:** `demo/catch.bas`.

| argument | default | what it does | when you'd use it |
|---|---|---|---|
| `--out PATH` | `demo/catch.bas` | where the listing goes | keeping a variant |
| `--org N` | `32000` | where the routine is POKEd | leaving room for other code |
| `--fps N` | `30` | frames a second, which sets the frame delay | a faster or slower game |
| `--scan N` | `0` | extra keyboard reads a frame | stressing the interactive path |
| `--disasm` | off | prints the routine instead of writing it | checking the generated code |
| `--selftest` | off | plays it in the core with a bot at the keyboard | checking the game logic |
| `--frames N` | `400` | frames for `--selftest` | a longer self-test |

### Corpus measurement tools

The next four read a local archive of period listings that is not
published. They find it through a `corpus` link at this repository's root
(`ln -s /path/to/archive corpus`; gitignored) or the `TRS80_CORPUS`
variable, and refuse to run without it. All but `phasea.sweep` also run
`../trs80basic`.

#### `python3 -m phasea.sweep`

Statically extracts and classifies every machine-code loader in the archive.
It refuses to report counts unless the two anchor test suites pass.
**Writes:** the manifest.

| argument | default | what it does | when you'd use it |
|---|---|---|---|
| `--json PATH` | `out/manifest.json` | where the manifest of extracted payloads goes | keeping two sweeps side by side |

#### `python3 -m phasea.oracle`

Runs listings under an instrumented copy of the interpreter, with no Z80,
and reads back the bytes their loaders POKEd. It covers loaders static
extraction cannot resolve. **Writes:** `out/oracle/`, plus the `--json` file.

| argument | default | what it does | when you'd use it |
|---|---|---|---|
| `--files PATH` | none | a JSON list of archive-relative listing keys; every mode below runs only these, so without it nothing runs | always |
| `--validate` | off | checks the oracle against listings static extraction already resolves; exits 1 on any contradiction | before trusting `--run` |
| `--run` | off | extracts from the listings | loaders the sweep could not resolve |
| `--hangs` | off | traces listings that never finish, to see whether they wait on a `USR` result | a listing that hangs rather than fails |
| `--timeout S` | `10.0` | seconds per listing | slow loaders |
| `--limit N` | all | only the first N listings | a quick trial |
| `--json PATH` | none | saves the results | keeping them |
| `--verbose` | off | a progress line per listing | watching a long run |
| `--rebuild` | off | rebuilds the instrumented interpreter | after the interpreter changes |

#### `python3 tools/usr_sweep.py`

Runs every archive listing that mentions `USR` three ways in batch mode:
without a core, with the core, and with the core again as a control. Each
run is classified by what the core changed. It takes about ten minutes.
**Writes:** `out/usr_sweep/`. It has no arguments.

#### `python3 tools/usr_pty_sweep.py`

The same listings, driven through a pseudo-terminal with a keystroke script,
for routines that sit behind an `INKEY$` menu batch mode cannot reach.
**Writes:** `out/usr_pty_sweep/`.

| argument | default | what it does | when you'd use it |
|---|---|---|---|
| `--class CLS` | `no-usr-reached` | takes the listings `usr_sweep.py` put in this class, or `all` | the normal follow-up to `usr_sweep.py` |
| `--files KEY...` | none | archive-relative listings instead of a class | re-running a few |
| `--workers N` | `5` | listings run in parallel | a slower or faster machine |

### Measurement probes

#### `python3 tools/tick_probe.py`

Times a sound-shaped routine three ways: the core alone, through the
interpreter in batch mode, and through a pseudo-terminal. **Writes:**
`out/tick_probe.json` and `out/tick_probe.json.bas`.

| argument | default | what it does | when you'd use it |
|---|---|---|---|
| `--basic PATH` | `../trs80basic` | the interpreter checkout | one that lives elsewhere |
| `--passes N` | `12` | passes of 256 tone cycles | longer runs for steadier timings |

#### `python3 tools/kbd_probe.py`

Times what one keyboard read costs through the interpreter: the `dd | od`
pipeline it started at a terminal until 2026-09-16 (kept as the
reference), the core alone, batch mode,
a pseudo-terminal with no key and with a key held, and BASIC's own `PEEK`
and `INKEY$` loops. With `--listing` it measures a program whose routine
keeps running instead, four ways: speed, keyboard reads and ticks a
second, and the share of time spent waiting on each. With `--rates` it
runs a routine that polls at each given rate, paced, to find where a
program falls behind real time. **Writes:** `out/kbd_probe/`.

| argument | default | what it does | when you'd use it |
|---|---|---|---|
| `--basic PATH` | `../trs80basic` | the interpreter checkout | one that lives elsewhere |
| `--reads N` | `20000` | reads in the core-alone and batch runs, 1-65535 | steadier batch timings |
| `--tty-reads N` | `1000` | reads in each terminal run, 1-65535 | steadier terminal timings |
| `--loops N` | `1000` | passes of each BASIC loop at the terminal | steadier BASIC timings |
| `--pipe-runs N` | `200` | runs of the pipeline alone | a noisy host |
| `--listing FILE` | none | measures that listing instead | what a real program loses at a terminal |
| `--seconds N` | `15` | seconds measured per way with `--listing`, per rate with `--rates` | longer windows |
| `--rates R,R...` | none | a routine polling at each rate, paced, at the terminal | where a program falls behind real time |
| `--work DIR` | `out/kbd_probe` | where the programs and logs go | keeping runs apart |

#### `python3 tools/sound_probe.py {synth,sinks}`

`synth` measures the pitch accuracy and cost of a prototype synthesizer.
`sinks` sends silent streams to the installed players, about 40 s, to see
how far each buffers ahead. **Writes:** nothing, except the `--wav` file.

| argument | default | what it does | when you'd use it |
|---|---|---|---|
| `synth --wav PATH` | none | also writes a C-major arpeggio | hearing the synthesizer |

## User manual

### Workflow

A BASIC listing loads a routine's bytes into memory, points a `USR` vector
at them, and calls `USR`. With the core attached, the interpreter passes
the memory to the core. The core executes from the entry address until the
routine returns to BASIC. Video writes reach the screen while the routine
runs, and the keyboard is read live. Every byte the routine stores comes
back, so `PEEK` sees it afterwards.

A worked example. Save this as `double.bas`. It POKEs seven bytes at 7D00H
(32000), sets the `USR` vector at 16526/16527 to that address, and calls it:

```basic
10 FOR I=0 TO 6: READ B: POKE 32000+I,B: NEXT
20 DATA 205,127,10,41,195,154,10
30 POKE 16526,0: POKE 16527,125
40 PRINT USR(21)
```

Run it from the trs80basic checkout:

```bash
./basic double.bas                  # with the core: prints 42
TRS80_Z80= ./basic double.bas       # without it: prints 21, then a USR STUB: line naming 7D00H
```

To see what the routine does, disassemble the same bytes at the same address:

```bash
python3 -m z80.disasm --hex "CD 7F 0A 29 C3 9A 0A" --base 7D00H
```

```
7D00  CD 7F 0A      CALL 0A7FH
7D03  29            ADD HL,HL
7D04  C3 9A 0A      JP 0A9AH
```

It fetches the `USR` argument into HL (ROM entry 0A7FH), doubles it, and
returns HL to BASIC as the result (0A9AH).

The other direction starts from source. Save this as `double.asm`:

```
00100         ORG   7D00H
00110 ARG     EQU   0A7FH        ;the USR argument into HL
00120 RESULT  EQU   0A9AH        ;HL back to BASIC
00130 DOUBLE  CALL  ARG
00140         ADD   HL,HL
00150         JP    RESULT
00160         END   DOUBLE
```

```bash
python3 -m z80.asm double.asm                  # the listing: addresses, bytes, source
python3 -m z80.asm double.asm -o double.bas    # a DATA/POKE loader; edit line 60 to PRINT USR(21)
python3 -m z80.asm double.asm -o double.cmd    # a load module, for later
```

The `.bas` file runs in the interpreter exactly like the hand-written
listing above. Because the assembler, the disassembler and the core share
one opcode table, the bytes it emits are the bytes the disassembler reads
back and the core executes.

### Decision points

- **Is the core attached?** Look at the end of the run. A `USR STUB:` line
  means no routine executed: the core is not beside the interpreter,
  `TRS80_Z80` is empty, or `python3` is missing. No line at all means the
  core ran every call.
- **Pace or not?** Leave it unpaced for routines that compute (sorts,
  searches). Set `TRS80_MHZ=1.77408` for anything you watch or hear: an
  unpaced delay loop takes almost no time.
- **A `?FC` at a `USR` call, with a `USR CORE:` line.** Read the text:
  - `no ROM here` means the routine called a ROM routine the core does not
    provide (see Gotchas).
  - `its memory was never written` means the loader never ran or put the
    code somewhere else. Check the address the listing POKEs against the
    `USR` vector.

### Gotchas

- **The ROM is not there.** You might expect a routine that calls any
  LEVEL II ROM routine to work. Actually it stops with `?FC` and
  `USR CORE: rom called 0500H, no ROM here`. The ROM is copyrighted and not
  distributed, so ROM services are rewritten from their documentation one
  at a time. Three are provided: 01C9H (CLS), 0A7FH (the `USR` argument
  into HL) and 0A9AH (HL back to BASIC as the result). Code that reads ROM
  bytes gets nothing meaningful either.
- **Empty memory reads FFH, which is `RST 38H`.** You might expect a call to
  an address nothing was loaded at to fail at that address. Actually the
  message names 0038H: `rom called 0038H, no ROM here -- no routine at
  C800H: its memory was never written`. The second half is the useful part.
- **Port FFH always reads 127.** You might expect it to report the screen
  width as BASIC's `INP(255)` does (63 in 32-character mode). Actually the
  core does not know the display mode. Every other port reads 255.
- **Batch mode has no keyboard.** You might expect a routine that scans the
  keyboard to read piped input in batch mode. Actually it sees no keys, and
  BREAK once input runs out. Run such programs at the interactive prompt.
- **Only machine code makes sound.** You might expect BASIC's `OUT 255` to
  click. Actually it stays silent. Only a `USR` routine's writes to port
  FFH bits 0-1 produce sound.
- **Live sound paces the core.** With a player set and no `TRS80_MHZ`, the
  core paces itself at 1.77408 MHz, since a player cannot keep up with an
  unpaced stream. The WAV's pitch is right at any speed.
- **The WAV has no gaps.** You might expect it to follow wall-clock time.
  Actually it holds only the time routines spent running, with consecutive
  calls joined and nothing for the BASIC that ran between them.
- **A failed player is silent.** A player that cannot start, or that exits,
  turns live sound off for the session without a message. The core may not
  write to the terminal. The WAV carries on.
- **`core.py` has no `--help`.** Started by hand, it silently waits for the
  interpreter's first message. Leave with Ctrl-D.
- **`tools/usr_sweep.py` ignores its arguments.** `--help` starts the
  ten-minute sweep.

### Undo / recovery

The core changes no files except the WAV named by `TRS80_SOUND_WAV`; delete
that file to undo it. If the core stops answering, the interpreter prints
a `USR CORE:` line and runs `USR` as the stub for the rest of the session.
Restart the interpreter to attach a fresh core. Everything under `out/` and
`tests/vectors/` can be regenerated by the command that wrote it.

### Tips

- `sound on` and `sound wav out.wav` at the interpreter's prompt switch
  sound without restarting.
- Bytes in a listing's `DATA` lines are decimal. Convert them for `--hex`
  with `python3 -c "print(bytes([205,127,10,41]).hex(' '))"`.
- To see exactly what a routine drew, log the call with `tools/corelog.sh`,
  then replay it: `python3 tools/render_frames.py run.out 1 end`.
- The disassembler sweeps linearly. Data mixed into code decodes as nonsense
  instructions; trim with `--skip` and `--length`.

### Not supported

- ROM routines other than the three listed above, and code that reads the
  ROM.
- Interrupts. A routine that `HALT`s to wait for one stops with `?FC`.
- Cassette and disk I/O from machine code. Port FFH output is sound only.
- Running machine code outside a BASIC program. The core runs only routines
  a program calls with `USR`; the disassembler is the one standalone tool.
- An assembler.

## Files and logs

| path | what it holds | written by | safe to delete? |
|---|---|---|---|
| `core.py` | the entry point the interpreter runs | you | no |
| `z80/` | the CPU (`cpu.py`), the opcode table everything decodes from (`table.py`), the disassembler, the coprocess, sound | you | no |
| `phasea/` | the loader extractor, classifier, sweep and oracle | you | no |
| `tools/` | the scripts above; `vectors.lock` pins the test vectors | you | no |
| `tests/` | the test suite | you | no |
| `tests/vectors/` | the downloaded CPU test vectors, about 1.3 GB, never committed | `fetch_vectors.py` | yes; fetch again |
| `out/manifest.json` | payloads and classifications from the static sweep | `phasea.sweep` | yes; regenerable |
| `out/oracle/` | the instrumented interpreter build and its scratch listings | `phasea.oracle`, the test suite | yes; rebuilt on demand |
| `out/usr_sweep/` | `results.json`, per-listing protocol logs in `runs/`, and the working directory | `usr_sweep.py` | yes; `usr_pty_sweep.py --class` reads `results.json` |
| `out/usr_pty_sweep/` | `results.json` and per-listing logs | `usr_pty_sweep.py` | yes |
| `out/tick_probe.json`, `.json.bas` | the latest tick timings and the program used | `tick_probe.py` | yes |
| `out/kbd_probe/` | the probe's programs, key files and proxy logs | `kbd_probe.py` | yes |
| `demo/catch.bas` | the CATCH listing, ready to CLOAD | `mkgame.py` | yes; regenerate it |
| `PREFIX.in`, `PREFIX.out` | a session's protocol, both directions | `corelog.sh` | yes |
| the `TRS80_SOUND_WAV` file | routines' audio | the core | yes |
| `corpus` | a link to the local listing archive | you | yes; the corpus tools then refuse to run |
| `PROTOCOL.md` | the wire contract between interpreter and core; a mirror of trs80basic's copy, kept identical | trs80basic | no |
| `LICENSE` | GNU GPL v3 | you | no |

## License

Copyright (c) 2026 David Forbis. GNU General Public License v3.0; see
`LICENSE`. Distributed WITHOUT ANY WARRANTY.

**TRS-80**, **Radio Shack** and **Tandy** are trademarks of their
respective owners, used only to describe compatibility. This project is
not affiliated with or endorsed by them.
