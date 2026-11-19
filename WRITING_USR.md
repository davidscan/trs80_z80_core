# Writing USR routines for trs80basic

How to write a NEW BASIC program that hands part of its work to Z80
machine code: for speed, or for sound. Running an old listing that
already carries its own routines needs none of this; the README covers
that.

Read first: the README's **User manual** (a worked seven-byte routine,
the fifteen ROM entries the core serves, and the gotchas), and
`PROTOCOL.md` when you need the exact contract between the interpreter
and the core. This guide is the how-to between them. Every routine and
listing in it is assembled and run by `tests/test_usr_guide.py`, so what
you read here is what the core does today.

## 1. When USR pays

The balance between BASIC and machine code here is not the 1980 one. On
the machine, BASIC was slow and machine code was the only way to go
fast. Here BASIC runs in gawk, many times faster than the machine's own
interpreter, while the core is a Z80 written in Python. Measure before
you write a routine.

Measured by `python3 tools/usr_speed.py` (batch mode, unpaced):

| what | measured |
|---|---|
| BASIC statements a second | 77,000 |
| one USR call to a routine that is a single RET | 0.22 ms |
| fill the screen, 1,024 POKEs in a BASIC loop | 20.3 ms |
| fill the screen, one USR call to a 17-byte LDIR routine | 2.1 ms |
| the core's speed, as a multiple of the Model I's 1.77408 MHz | 15.9 |

Inputs: 2026-11-18, core v2.2.0-12-g90510cc, trs80basic
v2.3.0-10-g52c68b1, Python 3.11.3, gawk 5.4.0, macOS on Apple silicon
(14 cores), load average 2.5-3.1, three repeats, median. Your numbers
will differ; the ratios are what to carry away. Re-run the tool on your
own machine before you trust a decision to them.

What follows from them:

- **A call costs about 17 statements.** A routine that does less work
  per call than that much BASIC makes the program slower, however tight
  its code. Many small calls in a loop lose; one call that does a whole
  job wins.
- **A statement's time buys about 50 Z80 instructions.** The core runs
  about 28 million T-states a second, and a statement takes about 13
  microseconds. Byte work wins by a wide margin: moving, filling,
  searching or comparing memory, bit packing, a screen update (the fill
  above is ten times faster). Arithmetic on BASIC's floating-point
  numbers loses: a single-precision multiply written in Z80 takes
  hundreds of instructions, and gawk does it natively.
- **Data has to get there.** A routine sees memory, not BASIC variables.
  An array or string it can reach through `VARPTR` costs nothing extra
  (section 5); data that BASIC must POKE into place first costs a
  statement a byte, and that can eat the whole gain.
- **At a terminal the core is slower than in batch.** Interactive runs
  answer the core's keyboard reads and BREAK ticks from the live
  terminal, and a long-running routine spends much of its time waiting
  on those answers. `tools/tick_probe.py` measures that path.
- **Look at the interpreter first.** If a program is slow, the cause is
  more often one slow kind of statement than BASIC as a whole: count
  where the statements go (`--steps-report`, and timing sections of
  the program) before deciding that machine code is the answer.

Sound is a different case: it is not about speed at all. Only a USR
routine can make sound (section 6).

## 2. The calling contract

A routine is entered by `X = USR(arg)` (slot 0; `USR0`-`USR9` with Disk
BASIC's `DEF USRn`). The registers at entry are the ROM's (PROTOCOL.md
"The frame"): HL = the entry address, A = the argument's type (2
integer, 3 string, 4 single, 8 double), DE = the string's descriptor
address for a string argument, the others zero.

- **The argument, as an integer:** `CALL 0A7FH` puts it in HL (rounded,
  then floored to -32768..32767; out of range is `?OV`, a string is
  `?TM`).
- **A result:** `JP 0A9AH` returns HL to BASIC as a signed integer. A
  plain `RET` returns the argument unchanged: USR's value is whatever is
  in BASIC's number accumulator (WRA1, 411DH-4124H) when the routine
  ends, and the argument is there until the routine changes it.
- **The stack** is BASIC's: the core enters with SP just below string
  space, with room for ordinary pushes and calls. Leave it balanced, or
  the final `RET` goes somewhere else.
- **ROM calls:** only the fifteen entries listed in the README. Any
  other jump or call into 0000H-2FFFH stops the routine with `?FC` and a
  `USR CORE: rom called ...` line. That is deliberate: the ROM is not
  distributed, and those services are rewritten from their published
  documentation one at a time. A routine that keeps to the list also
  runs on a real machine.
- **Ports:** only port FFH does anything: bits 0-1 are the cassette
  output (sound) and bit 3 the 32/64-column latch. Write bit 3 as 0
  unless you mean 32-column mode.

## 3. Where a routine lives

Put the routine above a fence the program sets itself, and nothing
BASIC does will touch it:

```basic
10 POKE 16561,255: POKE 16562,239: CLEAR 100
```

That lowers the top of BASIC's memory (40B1H) to EFFFH, and `CLEAR`
starts string space below it: F000H-FFFFH, 4K, is now the program's.
`--memsize 61439` on the command line, or that answer to `MEM SIZE?`,
does the same from outside, but a fence in the program itself is the one
that cannot be forgotten.

Why the fence matters here, with the interpreter's memory model in mind
(the contract is in trs80basic's `src/p75_mem.awk`):

- **String space grows down from the fence, and a string variable's
  bytes win over anything stored where it lands.** A routine POKEd
  below the fence can be covered when the program's strings grow.
- **The program's own text grows up from 42E9H, and wins over anything
  stored there.** A routine POKEd at a low address (the period favourite
  is 32000, 7D00H) is covered when the program grows past it, and then
  the core executes program text: no error, wrong behaviour.
- **The stack sits under string space.** The core pushes there during
  the call.
- **Memory nothing stored reads FFH,** which is `RST 38H`. A call to the
  wrong address therefore reports `rom called 0038H ... its memory was
  never written`: check the loader's address against the USR vector.
- **POKE and PEEK above 32767 take negative addresses,** as on the
  machine: subtract 65536 (The Alternate Source, *TRS-80 ROM Routines
  Documented*, 1983, chapter 2). `POKE 61440,0` is `?OV`; write
  `POKE -4096,0`.
- **A program meant for a real 16K machine** has RAM only up to 7FFFH:
  fence at 7EFFH (`POKE 16561,255: POKE 16562,126`) and load at 7F00H.

## 4. Getting the bytes in

Write the routine as source and let the assembler produce the bytes.
Never hand-count: a relative jump's offset is the usual casualty, and a
wrong offset runs without error into the middle of an instruction.

```bash
python3 -m z80.asm fill.asm               # listing: address, bytes, source
python3 -m z80.asm fill.asm -o fill.bin   # the raw bytes
python3 -m z80.asm fill.asm -o fill.bas   # a DATA/POKE loader with a checksum
python3 -m z80.disasm fill.bin --base F000H   # read the bytes back
```

The `.bas` loader is a complete program with a checksum, and its `DATA`
lines can be copied into yours; it sets no fence, so add one (section
3). Or write the loader yourself, as below: a `READ`/`POKE` loop,
then the USR vector (16526/16527, low byte first; Level II's form, where
Disk BASIC would use `DEF USR`). To check a routine without BASIC,
`python3 -m z80.run fill.asm --arg 191 --regs` runs it in the core alone.

The first example fills the screen with the byte it is given:

<!-- example: fill.asm -->
```
; FILL: every screen cell becomes the USR argument (0-255)
        ORG     0F000H
ARG     EQU     0A7FH           ;the USR argument into HL
FILL    CALL    ARG
        LD      A,L
        LD      HL,3C00H        ;the screen, 1,024 cells
        LD      (HL),A
        LD      DE,3C01H
        LD      BC,3FFH
        LDIR                    ;copy each cell into the next
        RET                     ;USR's value: the argument, untouched
        END     FILL
```

<!-- example: fill.bas -->
```basic
10 POKE 16561,255: POKE 16562,239: CLEAR 100
20 FOR I=0 TO 16: READ B: POKE -4096+I,B: NEXT
30 DATA 205,127,10,125,33,0,60,119,17,1,60,1,255,3,237,176,201
40 POKE 16526,0: POKE 16527,240
50 X=USR(191)
60 PRINT PEEK(15360); PEEK(16383); X
```

<!-- expect: fill -->
```
 191  191  191 
```

## 5. Passing data

**Numbers.** One integer goes in through the argument and comes back
through 0A9AH. For more, hand the routine an address: `VARPTR(V%)` is
where an integer's two bytes live (low byte first); a single's four
and a double's eight are in the machine's binary format. A routine that
stores there changes the variable.

**Arrays** are the efficient way to pass a block. An array's elements
are consecutive (two bytes each for an integer array), and the routine
sees all of them when it is handed the address of the first, including
values the program changed since the last call:

<!-- example: sum.asm -->
```
; SUM: USR(VARPTR(A%(0))) adds A%(1) to A%(n), where A%(0) = n (1-255)
        ORG     0F060H
ARG     EQU     0A7FH           ;the USR argument into HL
RESULT  EQU     0A9AH           ;HL back to BASIC as an integer
SUM     CALL    ARG             ;HL = the address of A%(0)
        LD      B,(HL)          ;n, from A%(0)'s low byte
        INC     HL
        INC     HL              ;HL = A%(1): two bytes each, low first
        LD      DE,0
LOOP    LD      A,(HL)
        INC     HL
        ADD     A,E
        LD      E,A
        LD      A,(HL)
        INC     HL
        ADC     A,D
        LD      D,A
        DJNZ    LOOP
        EX      DE,HL
        JP      RESULT
        END     SUM
```

<!-- example: sum.bas -->
```basic
10 POKE 16561,255: POKE 16562,239: CLEAR 100
20 FOR I=0 TO 22: READ B: POKE -4000+I,B: NEXT
30 DATA 205,127,10,70,35,35,17,0,0,126,35,131,95,126,35,138,87,16,246,235,195,154,10
40 POKE 16526,96: POKE 16527,240
50 DIM A%(10): A%(0)=10: FOR I=1 TO 10: A%(I)=I*100: NEXT
60 PRINT USR(VARPTR(A%(0)))
70 A%(10)=-1: PRINT USR(VARPTR(A%(0)))
```

<!-- expect: sum -->
```
 5500 
 4499 
```

`VARPTR` can be negative (it is a signed integer); `CALL 0A7FH` turns it
back into the right address.

**Strings.** Pass the string itself: `USR(B$)` enters with DE pointing at
its three-byte descriptor (the length, then the address of the bytes,
low byte first), and a plain `RET` makes the string USR's value. A
routine that rewrites the bytes rewrites the variable.

One trap: a string assigned from a literal (`A$="Hello"`) shares its
bytes with the program line, as on the machine, so a routine that writes
into it writes into the program. Copy it first: `B$=A$+""` makes new
bytes.

<!-- example: upper.asm -->
```
; UPPER: capitals in place in the string passed as USR's argument
        ORG     0F020H
UPPER   LD      A,(DE)          ;DE = the string's descriptor: length,
        OR      A               ;then the address of its bytes
        RET     Z
        LD      B,A
        INC     DE
        LD      A,(DE)
        LD      L,A
        INC     DE
        LD      A,(DE)
        LD      H,A
LOOP    LD      A,(HL)
        CP      'a'
        JR      C,NEXT
        CP      'z'+1
        JR      NC,NEXT
        SUB     32
        LD      (HL),A
NEXT    INC     HL
        DJNZ    LOOP
        RET
        END     UPPER
```

<!-- example: upper.bas -->
```basic
10 POKE 16561,255: POKE 16562,239: CLEAR 100
20 FOR I=0 TO 25: READ B: POKE -4064+I,B: NEXT
30 DATA 26,183,200,71,19,26,111,19,26,103,126,254,97,56,7,254,123,48,3
35 DATA 214,32,119,35,16,241,201
40 POKE 16526,32: POKE 16527,240
50 A$="Hello, world": B$=A$+""
60 B$=USR(B$): PRINT A$: PRINT B$
```

<!-- expect: upper -->
```
Hello, world
HELLO, WORLD
```

## 6. Sound

The Model I's only sound is the cassette output, bits 0-1 of port FFH:
write 1, then 2, alternately, for a square wave, and 0 to rest (Barden,
*Programming Techniques for Level II BASIC*, 1981). The pitch is set by
how many T-states pass between the writes, and the core charges every
instruction its exact cost, so the pitch is exact: count the cycles of
the loop and the frequency is 1,774,080 divided by them.

<!-- example: tone.asm -->
```
; TONE: a square wave on the cassette port; USR(D) sets the pitch.
; One cycle is 26*D+60 T-states (D = 1-255), so the pitch is
; 1,774,080 / (26*D+60) Hz on a Model I.  400 cycles, then silence.
        ORG     0F040H
ARG     EQU     0A7FH
TONE    CALL    ARG             ;HL = D
        LD      C,L
        LD      DE,400          ;cycles to play
CYCLE   LD      A,1             ;one polarity        7
        OUT     (0FFH),A        ;                   11
        LD      B,C             ;                    4
HIGH    DJNZ    HIGH            ;13*D-5
        LD      A,2             ;the other          7
        OUT     (0FFH),A        ;                   11
        LD      B,C             ;                    4
LOW     DJNZ    LOW             ;13*D-5
        DEC     DE              ;                    6
        LD      A,D             ;                    4
        OR      E               ;                    4
        JR      NZ,CYCLE        ;                   12
        XOR     A               ;rest
        OUT     (0FFH),A
        RET
        END     TONE
```

<!-- example: tone.bas -->
```basic
10 POKE 16561,255: POKE 16562,239: CLEAR 100
20 FOR I=0 TO 29: READ B: POKE -4032+I,B: NEXT
30 DATA 205,127,10,77,17,144,1,62,1,211,255,65,16,254,62,2
35 DATA 211,255,65,16,254,27,122,179,32,237,175,211,255,201
40 POKE 16526,64: POKE 16527,240
50 FOR D=100 TO 50 STEP -50: X=USR(D): NEXT
```

D = 100 is 1,774,080 / 2,660 = 666.95 Hz for 0.60 s, then D = 50 is
1,304.47 Hz for 0.31 s. The test measures both in the WAV and holds
them to 0.1%.

Hearing it and checking it:

```bash
TRS80_SOUND=auto ./basic tone.bas             # live, through ffplay (or another player)
TRS80_SOUND_WAV=tone.wav ./basic tone.bas     # a WAV file, no speakers needed
```

- Set `TRS80_MHZ=1.77408` (or `speed 1.77408` at the prompt) for
  anything timed against the screen; live sound paces itself, a WAV
  holds the right pitch at any speed.
- A USR call blocks BASIC until it returns, as it did on the machine: a
  tone plays, then the program goes on. There is no background music.
- `OUT 255` from BASIC is silent. Only a routine's writes make sound.
- Check sound by measurement, not only by ear: count the WAV's rising
  zero crossings over the tone's length (the test does it in a dozen
  lines of Python's `wave` module), and compare with the cycle count.

## 7. Testing

**Silent wrong output is the failure that matters.** A routine with a
bad address or offset usually finishes, and the program prints something
plausible. So test by running, and assert on what comes out.

- `TRS80_USR=strict` makes any USR call that the core did not execute a
  `?FC`. Without it, a missing core turns every USR into "return the
  argument" with only a line on stderr at the end, and a test can pass
  with no machine code run at all.
- Run in batch (`./basic prog.bas`) and compare stdout with what you
  expect; read memory back with `PEEK` and print it.
- `--steps N` bounds a run deterministically; a routine's cycles count
  toward it (1,000 a statement), so even a routine that never returns
  stops at the same place every time.
- Test a routine alone first with `python3 -m z80.run`: `--arg`,
  `--regs` and `--dump ADDR,LEN` show what it did.
- Batch mode has no keyboard: a routine that scans the keyboard sees no
  key. Test those at the prompt, or through a pseudo-terminal.
- For sound, write a WAV and measure it (section 6).

## 8. Checklist

1. Measured: the work per call is worth far more than 17 statements, or
   it is sound.
2. A fence in the program (`POKE 16561/16562`, `CLEAR`) and the routine
   above it.
3. Source assembled, never hand-counted; bytes read back with the
   disassembler.
4. Addresses above 32767 written as negatives in POKE and PEEK.
5. ROM calls only to the fifteen served entries.
6. Literal strings copied before a routine writes them.
7. A test that runs it with `TRS80_USR=strict` and asserts on output.
