# SOUND.md — machine-code sound through the cassette port, as work items

The plan for giving USR routines audible sound. The core captures the port
FFH writes a routine makes, stamped with their T-state positions,
synthesizes them into 16-bit PCM, and sends that to a live player, a WAV
file, or both. PLANNED 2026-09-13 at the user's request; **S-1 to S-8
BUILT 2026-09-14** (`z80/sound.py`, `Machine.port_out`/`tick`/`run` in
`z80/coprocess.py`, `tests/test_sound.py`, README "Run", DESIGN.md
decision 7), and S-10, the interpreter's `sound` metacommand, the same
day. S-9, the by-ear check, is the user's. This file is a work-item ledger
in the shape of DANCING_DEMON.md: what must be true, what is measured,
and what is still the user's to decide.

BUILT STATE, 2026-09-14. The open questions were settled at the build,
each by its recommendation (recorded in DESIGN.md decision 7): 1 rest;
2 silent; 3 pace at 1.77408 MHz; 4 emulated time only; 5 `auto` =
ffplay everywhere (S-9 ruling, 2026-09-15; ffmpeg AudioToolbox on macOS
was the interim default); 6 22,050 Hz;
7 the names as proposed. Two things differ from the plan text below.
The live writer's lead policy has hysteresis, because a single
threshold inserts silence on every tick: between calls the stream is
topped up to LEAD (60 ms) whenever it falls more than GRAIN (5 ms)
short, so a call always starts with the same lead; inside a call
silence is inserted only below FLOOR (15 ms), and only enough to reach
FLOOR + GRAIN, since every inserted sample shifts the rest of the call
(z80/sound.py `LiveSink`). And sample boundaries are integer T-states,
`(s * clock) // rate`, with the box filter integrated in integers, so
chunked output is byte-identical to one-shot output by construction;
`tests/test_sound.py` pins it across ticks and across calls. Measured
at the build: 4.4 ms of CPU per audio second at 22,050 Hz, 8.7 at
44,100; the transport test shows the protocol lines byte-identical with
and without the variables; trs80basic's z80.sh and z80core.sh pass with
them set. The one live-sound item on the interpreter side (section B,
the tick poll) was built the same day: pollbrk fills from the real
keyboard on every fourth tick only.

It SUPERSEDES the DESIGN.md non-goal that said "do not build the synth now"
(2026-08-13). That ruling rested on real-time pitch needing cycle accuracy
the core would not have. The core now charges every instruction its exact
T-state cost, checked against all 1,604,000 reference cases, and paces on
those counts (DESIGN.md decision 7, restored to DESIGN.md 2026-09-14 when
the code landed; this file left the private sidecar on 2026-09-15).

EVIDENCE BASE: the 2026-09-13 probes (`tools/sound_probe.py` and
`tools/tick_probe.py`, "Measured" below), FINDING 24 section 6 (the Dancing Demon's sound routine), and the
corpus classification under "Scope".

## Scope (user, 2026-09-13)

- **Machine code only.** BASIC `OUT 255` stays a silent no-op in
  trs80basic. Of the corpus's 530 text listings that write port 255 from
  BASIC, 156 drive only the tape relay, 123 make a click or pulse, 81
  touch only the 32/64-column bit, 62 run a tone loop and 108 are other or
  unclassified (a rough count: text files only, duplicates included). A
  BASIC tone's pitch would follow the interpreter's flat per-statement
  cost, which the user ruled need not be accurate. Machine code is where
  sound lives: 44 of the 63 classified USR payloads in Z80_FINDINGS are
  sound routines.
- **Live playback, a WAV file, or both,** chosen at run time.
- **No change to PROTOCOL.md or trs80basic** for the first build. Sound
  lives entirely in the optional core; without the core there is none.
- **Out of scope:** BASIC `OUT 255`; the tape relay's click (bit 2);
  delaying video to match audio lag; interrupts; Model III hardware
  differences beyond its clock rate.

## Definition of done

1. With the sound variables unset, every protocol line and every test is
   byte-identical to today's.
2. A self-written fixture routine with the OUT, DJNZ, OUT, DJNZ shape, run
   through `Machine` with the file sink, writes a WAV whose measured pitch
   matches `clock / (26*D + 38)` within 0.5% for several delay values D,
   and the WAV is byte-identical whether or not the call was paced.
3. The Dancing Demon's preset show #1 plays its music live, in step with
   the dance, at `TRS80_MHZ=1.77408`. A by-ear check at a real terminal,
   like trs80basic HAND_TEST 14 (which confirmed the dance's own tempo
   on 2026-09-12).

## How the machine made sound (reference)

- Port FFH is a four-bit latch: bits 0-1 the cassette output signal, bit 2
  the cassette relay, bit 3 32-column video mode (Barden, *Programming
  Techniques for Level II BASIC*, 1981, figure 12-9).
- A pulse is written as 1, then 2, then back to 0; alternating 1 and 2
  makes a square wave (Barden, same page). The owner heard it through an
  amplifier on the cassette AUX line (*More TRS-80 BASIC*, 1981, chapter
  8). The Model III manual gives the output as about 800 mV peak-to-peak
  into 1 kilohm.
- Level mapping used here: 0 rest, 1 one polarity, 2 the other. Writing 3
  is not described anywhere in the library; it is treated as rest until a
  schematic says otherwise (open question 1).
- The clock: Model I, a 10.6445 MHz crystal divided by 6, 1.77408 MHz. The
  ROM book's delay figure, 14.6555 microseconds per count, is exactly 26
  T-states at that rate. Model III, 2.02752 MHz: its 14.7964 microseconds
  per count is exactly 30 T-states.
- The Dancing Demon's routine (FINDING 24 section 6) toggles with
  `OUT (C),H` and `OUT (C),L` around two `DJNZ` delays. One cycle costs
  26*D + 38 T-states, where D is the delay register and 0 means 256, so
  its pitch is `clock / (26*D + 38)`. The half-cycles are 13*D + 11 and
  13*D + 27 T-states, a slightly uneven square wave. D = 100 gives 672 Hz
  at 1.77408 MHz.

## Measured 2026-09-13

The prototype synthesizer, pure Python on the development Mac. Five-second
square waves were built from T-state transitions, and pitch was measured
from zero crossings of the output:

| Sample rate | Tone requested | Pitch measured | CPU per audio second |
|---|---|---|---|
| 22,050 Hz | 261.63 Hz | 261.63 Hz | 5.4 ms |
| 22,050 Hz | 440.00 Hz | 440.00 Hz | 4.9 ms |
| 22,050 Hz | 2,000.00 Hz | 2,000.00 Hz | 5.4 ms |
| 44,100 Hz | 261.63 Hz | 261.63 Hz | 9.8 ms |
| 44,100 Hz | 440.00 Hz | 440.00 Hz | 9.9 ms |
| 44,100 Hz | 2,000.00 Hz | 2,000.00 Hz | 10.3 ms |

The players, fed silent raw 16-bit mono PCM at 22,050 Hz (44.1 KB/s); ranges
cover two runs:

| Behaviour | ffplay | ffmpeg `-f audiotoolbox` |
|---|---|---|
| Unpaced writer: when 8 s of audio was accepted | after 2.4 to 2.7 s, so 5.3 to 5.6 s buffered ahead | after 3.5 s, so about 4.5 s buffered ahead |
| Paced writer: median lag | 0.157 to 0.163 s behind its playback clock | 0.044 to 0.047 s behind samples handed to the device, not an acoustic figure |
| Same at 44,100 Hz | 0.201 s | not measured |
| First audio after start | about 0.17 to 0.20 s | not measured |
| Across a 1 s pause | clock keeps counting through the silence; stream survives | device time freezes; resumes with the same lag |

Other facts:

- `afplay` plays files only. `sox`, `aplay`, `mpv` and Python audio modules
  are absent on the development Mac, and the core stays standard-library
  Python.
- ffplay 8 rejects `-ac 1`; the channel option is `-ch_layout mono`.
- ffmpeg 8.1.2 from Homebrew has the `audiotoolbox` output device, which
  opens no window.

The core and the tick, measured 2026-09-13 with `tools/tick_probe.py`: a
demon-shaped OUT/DJNZ loop at D = 100 (2,638 T-states a cycle, 672 Hz),
4.57 s of emulated time. "Paced" is `mhz=1.77408`.

| Path | Wall time | Note |
|---|---|---|
| Core alone, unpaced | 0.25 s | about 18x real time |
| Core alone, paced | 4.57 s | exact |
| Through the interpreter, batch, paced | 4.67 s | includes startup |
| Through the interpreter, interactive pty, paced | 4.74 s | from RUN to the result |
| Through the interpreter, interactive pty, unpaced | 3.0 s | the keyboard poll alone |

The tick round-trip, `T` sent to `OK` received, over 913 ticks, with a
logging proxy between the interpreter and the core:

| Mode | median | p99 | max | of a tick |
|---|---|---|---|---|
| batch | 0.09 ms | 0.18 ms | 0.36 ms | 5 ms |
| interactive | 3.1 ms | 4.1 to 4.2 ms | 7.5 to 9.7 ms (two runs) | 5 ms |

The interactive cost is the interpreter's: its reply to every `T` runs
`pollbrk`, and in interactive mode `kb_fill` (p30) forks a `dd | od`
pipeline, two processes per tick. Steady state holds with about 1.5 ms
of margin per tick; single ticks overrun, which the live sink's lead
absorbs (S-4).

## A. Work items — the core

- **S-1. Capture the signal bits with their T-state positions.** In
  `Machine.port_out`, when `(port & 0xFF) == 0xFF` and `v & 3` differs
  from the last value, append `(self.cycles, v & 3)` to the call's
  transition list. `port_out` runs inside `step()`, before the step's cost
  is added, so a stamp marks the START of the OUT instruction: at most 12
  T-states early, under a sixth of a sample at 22,050 Hz. Bit 3 keeps its
  MODE handling untouched. The last level carries across calls. With sound
  off this costs one attribute test.
- **S-2. `z80/sound.py`, the synthesizer.** A small class fed transitions
  and an up-to T-state mark, returning PCM for the elapsed span. Each
  sample is the time-weighted average level across its T-state window, a
  box filter that keeps a fast square wave from aliasing into noise. A
  one-pole DC blocker follows, so a level held for a long time fades to
  silence instead of sitting as an offset. Fixed amplitude with headroom,
  mono, 16-bit. T-states convert to time at `mhz` from HELLO, or at 1.77408
  MHz when `mhz` is 0, so an unpaced file keeps true pitch. The default
  is the LITERAL 1.77408, not 10.6445e6/6 (1.7740833): the interpreter
  sends `mhz` through awk's %.6g, so a user's 1.77408 arrives exactly,
  and the S-7 byte-identity test needs both paths on one constant. Called from
  `tick()`, every 8,870 T-states or about 110 samples at 22,050 Hz, and
  once more when a call ends or breaks, so the last partial tick is not
  lost. Chunked output must be byte-identical to one-shot output: a
  global sample index across ticks, the level and the DC-blocker state
  carried across ticks and calls, and the transition list consumed each
  tick so it cannot grow for the length of a call.
- **S-3. The WAV sink.** Standard-library `wave`, 16-bit mono at the
  chosen rate. The file holds EMULATED time only: each call's audio is
  appended with no gap for the time BASIC ran between calls, which keeps a
  run deterministic and testable (open question 4). The header must stay
  valid however the session ends. Only the interpreter's give-up path
  (`z80_close`: a timeout or a bad line) kills the core; BYE and stdin
  EOF exit cleanly. So a SIGTERM handler that raises SystemExit, with
  the file closed in a `finally`, is enough; rewriting the RIFF fields
  after every flush is unnecessary (review 2026-09-13).
- **S-4. The live sink.** A player command from the environment, run
  through `sh -c` (the command is the user's, like `dir`), started at
  HELLO when the variable is set — not at the first audio: startup costs
  0.17 to 0.2 s, and the first notes would arrive late or be covered by
  inserted silence; an idle player in a silent session is the price of
  opting in. It is fed raw 16-bit little-endian mono PCM on its stdin.
  Its stdout and stderr go to /dev/null, because the interpreter owns
  the terminal. It runs in its own session so terminal signals do not
  reach it, and it exits on EOF when the core closes the pipe or dies.
  THE LEAD POLICY (review 2026-09-13): a writer thread keeps the stream a
  fixed LEAD ahead of wall-clock — 50 to 100 ms, well over the largest
  tick latency measured (under 10 ms, interactive) — and writes silence only
  when the stream would otherwise fall below that lead. It never writes
  silence merely because its queue is empty: a gap inserted mid-call
  pushes the rest of that call's audio out permanently. Between calls
  the fill keeps the lead; inside a paced call the core's 5 ms bursts
  land within it and nothing is inserted. The two players behave
  differently across a pause, which is why the writer, not the player,
  owns the fill. A broken pipe or a failed start turns live sound off
  for the session, while emulation and the WAV sink carry on (open
  question 2).
- **S-5. Pacing.** Both players buffer seconds ahead of a writer that does
  not pace, so live sound needs the core paced. With live sound on and
  `mhz` 0, pace at 1.77408 MHz (open question 3). Each tick's PCM goes to
  the writer thread as the tick completes, and the lead (S-4) plus the
  players' buffers smooth the core's 5 ms bursts. Sound trails the
  picture by the player's lag plus the lead; the acoustic figure is part
  of S-9. The budget is thin on the interactive path ("Measured": the
  keyboard poll takes 3.1 ms of every 5 ms tick), so section B's poll
  item widens it.
- **S-6. Configuration, proposed names.** `TRS80_SOUND` is the live player
  command; unset means no live sound. `TRS80_SOUND_WAV` is a file path;
  unset means no file. `TRS80_SOUND_RATE` is 22050, the default, or 44100;
  a `{rate}` in the player command is replaced with it, so the two cannot
  drift apart. The core inherits all
  three from trs80basic's environment, so the protocol does not change.
  Player commands:

      # macOS: lowest measured lag, no window
      ffmpeg -hide_banner -loglevel quiet -f s16le -ar 22050 -ch_layout mono -i - -f audiotoolbox -
      # any platform with ffmpeg installed
      ffplay -nodisp -autoexit -loglevel quiet -f s16le -ar 22050 -ch_layout mono -i -
      # Linux, untested
      aplay -q -f S16_LE -r 22050 -c 1
      pw-play --rate 22050 --channels 1 --format s16 -

- **S-7. Tests.** No test may need speakers.
  - Unit, `tests/test_sound.py`: pitch of synthetic square waves within
    0.1%; sample counts; the level map; the box filter at a window
    boundary; the DC blocker settling; silence with no transitions;
    chunked output equal to one-shot output byte for byte.
  - Machine: a SELF-WRITTEN routine with the OUT, DJNZ, OUT, DJNZ shape,
    never the demon's bytes (no third-party listings in the repo), for
    several D. The WAV's pitch equals `clock / (26*D + 38)` within 0.5%,
    and the WAV bytes are identical at `mhz=0` and `mhz=1.77408`.
  - Seam: trs80basic's `programs/tests/z80.sh` passes with the sound
    variables set, and a protocol log taken with sound on is
    byte-identical to one with sound off.
  - Live sink without an audio device: the player command is `cat` into a
    temporary file. The byte count matches the emulated audio plus the
    silence written, and killing the player turns sound off without
    failing the call. The lead policy: PCM handed to the writer later
    than the lead gets a silence gap inserted before it, PCM later by
    less than the lead gets none, byte for byte.
- **S-8. Docs.** README's Run section; DESIGN.md gets decision 7 (held
  privately until then) with the built state; the `z80/coprocess.py` docstring; DANCING_DEMON.md DD-6,
  "suppress the two sound OUTs", becomes "captured when sound is on".
- **S-9. The by-ear check.** Demon preset show #1 at `TRS80_MHZ=1.77408`
  with each recommended player: the music in step with the dance, the lag
  acceptable, no crackle, the terminal intact after BYE, and no window or
  Dock icon from the player.
- **S-10. The `sound` metacommand — AFTER S-9 (user, 2026-09-13).** Not
  part of the first build; it starts once S-9 has passed. Lowercase only
  and tagged EXT, like `speed`. `sound on` and `sound off` switch live
  playback; `sound wav <path>` and `sound wav off` switch the file sink;
  bare `sound` reports the state. The player COMMAND stays in
  `TRS80_SOUND` from the environment and never appears in a metacommand:
  the directive carries switches only, so it can later join the REM META
  whitelist (`rem_meta` in trs80basic's p40: a directive a FILE can fire
  must never run a shell command). `sound on` with no `TRS80_SOUND` uses
  the default player S-9 settles (open question 5). Mechanism, verified
  2026-09-13: the interpreter launches the core lazily on the first USR
  call, and gawk 5.4 passes ENVIRON assignments to a coprocess started
  afterwards, so before the first USR the metacommand only sets or
  deletes the ENVIRON entries. After the core is up it stops the core
  (`z80_stop`) and returns the state to cold, so the next USR call starts
  a fresh core with a full frame; nothing is lost, because the
  interpreter owns memory and every core write came back through
  `poke_byte`. The same restart is what lets a `speed` typed after the
  first USR call reach the core, which today it does not (the clock
  travels on HELLO once). Docs: README, the user guide, a `man sound`
  page in `support/manpages.txt`, and a HAND_TEST entry. Test: a batch
  fixture with the player command `cat` into a file, asserting that
  `sound on` before the first call captures audio, `sound off` after it
  stops the capture at the next call, and that the restart's full frame
  leaves the write-set bytes intact.

## B. Interpreter side — docs only

- trs80basic needs no code for the FIRST BUILD. Its README environment
  table and user guide list the three variables once S-6 is built. The
  `sound` metacommand is S-10, scheduled after S-9 (user, 2026-09-13).
- ONE INTERPRETER ITEM FOR LIVE SOUND, found by the 2026-09-13 review
  ("Measured"): `pollbrk` runs on every core tick and, interactively,
  forks `dd | od` each time, 3.1 ms of the 5 ms tick. Poll the real
  keyboard every fourth tick and answer `OK` from the queue otherwise,
  or make the poll cheaper. Not needed for the file sink or batch. It
  can wait for S-9 to say whether the lead alone is enough.
- A related gap found while scoping, NOT sound — FIXED in trs80basic
  2026-09-13 (its `st_out` drives the latch bit through `s_setwide`,
  fixture `programs/tests/out255.bas`): its BASIC `OUT` discarded bit 3,
  so `OUT 255,8` did not switch to 32 columns. Checked:
  `INP(255)` stays 127 after it, while `CHR$(23)` switches. 81 corpus
  listings use bit 3 from BASIC, mostly to flash the screen. That is an
  interpreter item, independent of this plan.

## C. Not building

- BASIC-level sound (Scope).
- The relay click on bit 2.
- Delaying video to match audio lag, unless S-9 says the lag is a problem.
- A protocol message for sound, unless open question 2 goes that way.
- A separate render-to-file mode: with no live player set, the file sink
  already runs unpaced.

## Open questions

1. **Writing 3 to bits 0-1.** Treated as rest; no library text describes
   it. A Model I schematic would settle it.
2. **Reporting a player that fails.** The core must not write to the
   terminal, and `ERR` fails the USR call with ?FC. Either sound stops
   silently, or PROTOCOL.md gains a non-fatal notice line that the
   interpreter prints. That is a change on both sides, because a version-1
   interpreter treats an unknown line as a dead core. Recommendation:
   silent for the first build, revisit after S-9.
3. **Live sound with pacing unset.** Force 1.77408 MHz while live sound is
   on (recommended), or refuse live sound and write the file only.
4. **File timeline.** Emulated time only, calls butted together
   (recommended: deterministic and testable), or wall-clock gaps between
   calls so the file matches what was heard.
5. **Default player on macOS.** ffmpeg's AudioToolbox device showed the
   lower lag; ffplay is the cross-platform choice. RULED 2026-09-15 after
   S-9: ffplay. Both played the demon in step with the dance and their
   WAVs lined up; the user chose the cross-compatible one "at least for
   now". ffmpeg's device stays the macOS fallback when ffplay is absent.
6. **Sample rate.** 22,050 Hz (about 5 ms of CPU per audio second, 0.16 s
   ffplay lag) against 44,100 Hz (about 10 ms, 0.20 s).
7. **The variable names** in S-6 are proposals.

## Reproducing the measurements

    python3 tools/sound_probe.py synth --wav out/sound/c_major_arpeggio.wav
    python3 tools/sound_probe.py sinks     # silent, about 40 s, skips absent players
    afplay out/sound/c_major_arpeggio.wav  # macOS: hear the prototype synthesizer
    python3 tools/tick_probe.py            # core speed and tick round-trips; needs ../trs80basic, about 20 s

Timings vary by host; the pitch results do not. `out/` is gitignored.
