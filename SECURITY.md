# Security

trs80_z80_core runs the machine code that old BASIC listings carry, and
many of the listings people run are ones they found online. This page says
what that machine code can and cannot do on your computer, what the core
promises, and what it does not.

It describes the current `main` branch (v2.1 and the fixes since) on macOS
and Linux. The interpreter's own page,
[trs80basic's SECURITY.md](https://github.com/davidscan/trs80basic/blob/main/SECURITY.md),
covers the BASIC side: what a program can do with files, the shell and the
terminal.

## Who is trusted

| Trusted (yours) | Not trusted |
|---|---|
| Your command line and options | The machine code a program runs: its bytes, everything it computes, every byte it writes |
| Your environment variables (`TRS80_SOUND`, `TRS80_SOUND_WAV` and the rest) | Every file the tools read: `.cmd`, `.cas`, `.bin` and `.asm` files |
| The interpreter that starts the core, and the files in your checkout | |

Anything in the left column can make the core do anything you can do; that
is by design. In particular **`TRS80_SOUND` is a shell command**: any value
other than `auto` is run through `sh -c` and fed the audio. Set it only to
a command you would type yourself. Likewise `TRS80_SOUND_WAV` names a file
the core overwrites when it starts (or, when the interpreter restarts the
core within a session, carries on a capture it recognises). The promises
below are about the right column.

## What machine code can do

- **Read and write the emulated 64K machine.** It sees the memory that
  `PEEK` and `POKE` see, and its writes are handed back to the interpreter,
  which applies them to that same emulated memory (PROTOCOL.md).
- **Write to the emulated screen** (3C00H-3FFFH). The interpreter draws it;
  its page says what reaches your terminal.
- **Read the emulated keyboard**, which the interpreter feeds from yours
  while the routine runs.
- **Make sound.** Port FFH's cassette bits become audio samples, sent to the
  player `TRS80_SOUND` names or written to the `TRS80_SOUND_WAV` file. The
  routine chooses the samples, never the command or the file.
- **Call four documented ROM services** (the USR argument, the USR result,
  CLS and the READY entry), which the core answers itself. Entering any
  other ROM address ends the call with an error. The core holds no ROM.

## What machine code cannot do

- Make a system call, open a file, start a process or reach the network.
  The emulated Z80 has no instruction or port that leaves the emulator:
  `IN` reads fixed values and `OUT` affects only the screen mode and the
  sound.
- Choose the sound command, the WAV file's name, or any other file name.

## What the tools promise about files

- `python3 -m z80.run`, `z80.disasm` and `tools/romcalls.py` read the
  file you name and write nothing. `python3 -m z80.asm` writes only the
  output and listing files you name, and `tools/hexcheck.py` only its
  `--out` file.
- A malformed `.cmd`, `.cas` or `.asm` file is reported as an error with a
  non-zero exit status; it does not run or write anything.
- `tools/fetch_vectors.py` downloads the third-party CPU test vectors into
  `tests/vectors/` and writes nowhere else, except that `--update-lock`
  re-pins to upstream by rewriting `tools/vectors.lock`. It unpacks only
  the files the pin in `tools/vectors.lock` names, and stops at a file
  whose bytes do not match the hash committed for it.

## Known limits

- A routine that never returns runs until it is stopped, as it would on
  the machine. At a terminal, BREAK stops it. In batch mode (`basic
  file.bas` with no terminal) nothing does, so run an untrusted listing
  under a time limit, such as `timeout 60 ./basic file.bas` (`timeout` is
  part of GNU coreutils; on macOS, Homebrew's `coreutils` package).
  `python3 -m z80.run` stops a program after its T-state budget
  (`--cycles`).
- The core trusts the interpreter that starts it: the frames it receives
  are taken as they come. Run it only from trs80basic, as its launcher
  does.
- `TRS80_SOUND` is run by the shell, as described above. A value set by
  someone else, in a shared shell profile or a script you did not write,
  runs with your rights.

## Reporting a problem

Open an issue on GitHub for anything. If you find a way for machine code or
a loaded file to get past the limits above, please use GitHub's private
vulnerability reporting instead (the repository's Security tab, "Report a
vulnerability"), so it can be fixed before it is public.
