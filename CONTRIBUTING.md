# Contributing

Bug reports, fixes and new tests are welcome. Open an issue first for
anything larger than a fix, so the change can be agreed before you build
it. A security problem goes through [SECURITY.md](SECURITY.md) instead.

## A good bug report

- The BASIC listing or machine-code file, how you ran it, what the core
  did, and what the TRS-80 or the Z80 does instead.
- How you know: the Zilog Z80 manual, a period book, or a run on real
  hardware or an emulator.
- `python3 --version`, your OS, and the commit you are on.

## Building and testing

The core needs only Python 3's standard library. Run the suite from this
folder:

    python3 -m unittest discover -s tests

Some tests need the third-party CPU vectors, fetched rather than committed.
CI fetches them and runs every case; to do the same locally:

    python3 tools/fetch_vectors.py --all
    Z80_VECTORS=all Z80_VECTORS_REQUIRE=1 python3 -m unittest discover -s tests

The core is also judged by the interpreter's suite. With
[trs80basic](https://github.com/davidscan/trs80basic) checked out beside
this repository, run `sh programs/tests/run_all.sh` there; a change to the
core must leave it passing.

## What a change must keep

**The CPU follows the Z80.** A change to `z80/cpu.py` or `z80/table.py`
says which document or vector it follows, and comes with a test that fails
without it. Tests assert on registers, flags, memory and cycles, not just
on a clean exit.

**PROTOCOL.md is the interpreter's.** The copy here is an exact mirror of
trs80basic's. Propose protocol changes there; never edit this copy alone.

**Memory agrees by construction.** The core never re-implements the
interpreter's address rules. What a routine reads comes from the frame the
interpreter builds; what it writes goes back as a write-set the interpreter
applies (PROTOCOL.md). A new memory path follows the same route.

**ROM services come from documentation.** The core answers a small set of
documented ROM entry points itself. A new one reimplements the documented
effect, cites where it is documented, and adds no ROM bytes.

**Machine code is untrusted input.** [SECURITY.md](SECURITY.md) lists what
a routine can and cannot do. No instruction, port or trap may reach the
host: no file, process or network access from emulated code. Only the
user's own settings (`TRS80_SOUND`, `TRS80_SOUND_WAV`) touch the host.

## Licence

The project is GPL-3.0 ([LICENSE](LICENSE)); a contribution is offered
under the same licence. Do not commit the CPU test vectors, ROM bytes,
book text or third-party listings.
