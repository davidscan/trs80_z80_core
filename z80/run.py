#!/usr/bin/env python3
"""z80/run.py -- run a machine-language program in the core, headless.

    python3 -m z80.run FILE [--org ADDR] [--entry ADDR] [--arg N] [--sp ADDR]
                       [--cycles N] [--screen | --no-screen] [--regs]
                       [--dump ADDR,LEN]... [--quiet]

FILE is a .cmd load module, a .cas SYSTEM tape, raw .bin bytes (then
--org is required) or .asm source, which is assembled first.  The
program is loaded into the core's RAM and called the way `USR` calls a
routine: the sentinel return address on the stack, the argument (--arg)
answered at 0A7FH, HL back through 0A9AH, the three served ROM entries
and `ERR rom` for any other.  There is no screen and no keyboard: video
bytes land in memory and are printed afterwards as the 16 by 64 screen,
and every keyboard-matrix read sees no key.  The tick that would poll
BREAK counts the budget instead: --cycles T-states (default 20 million,
about 11 seconds of the Model I) end a program that never returns, with
exit status 2.

What it prints: how the run ended (returned, 0A9AH with HL, HALT, a ROM
call with no ROM here, the budget), HL, the T-states and the seconds of
emulated time they are at 1.77408 MHz, then the screen if the program
wrote to it (--screen forces it, --no-screen suppresses it), the
registers with --regs, and any --dump ranges as hex.  Exit status 0 when
the program returned or reached 0A9AH, 1 on an error, 2 on the budget.
Standard library only.
"""
import argparse
import sys

from .coprocess import CoreError, Machine, VIDEO_HI, VIDEO_LO
from .load import LoadError, load_file

MHZ = 1.77408
DEFAULT_CYCLES = 20_000_000


class Headless:
    """A Machine with no transport: keys read 0, ticks count the budget."""

    def __init__(self, cycles):
        self.budget = cycles
        self.machine = Machine(self._send, self._recv, 0.0)
        self.last = ''
        self.lines = []

    def _send(self, line):
        self.last = line
        if line.startswith('RET '):
            self.lines.append(line)

    def _recv(self):
        if self.last.startswith('K '):
            return 'K 0'
        if self.machine.cycles >= self.budget:
            return 'BREAK'
        return 'OK'

    def load(self, segments):
        m = self.machine
        for org, data in segments:
            for i, b in enumerate(data):
                m.ram[(org + i) & 0xFFFF] = b
                m.known[(org + i) & 0xFFFF] = 1

    def run(self, entry, arg=0, sp=0xFF00):
        """Returns (how, detail): how is 'ret', 'result', 'budget' or an
        error code ('rom', 'halt', ...); detail is the text."""
        m = self.machine
        try:
            m.run(entry, arg, sp)
        except CoreError as e:
            return e.code, e.text
        fields = dict(f.split('=') for f in self.lines[-1][4:].split())
        if int(fields['break']):
            return 'budget', 'stopped by the budget after %s T-states' % format(m.cycles, ',')
        if int(fields['result']):
            return 'result', 'reached 0A9AH, the result path'
        return 'ret', 'returned'

    def screen(self):
        """16 rows of 64: printable bytes as they are, graphics bytes as
        '#', control bytes as '.', cells never written as blanks."""
        m = self.machine
        rows = []
        for r in range(16):
            a0 = VIDEO_LO + r * 64
            rows.append(''.join(
                ' ' if not m.known[a] else chr(m.ram[a]) if 32 <= m.ram[a] < 127
                else ('#' if m.ram[a] >= 128 else '.')
                for a in range(a0, a0 + 64)))
        return rows

    def wrote_video(self):
        return any(self.machine.known[a] for a in range(VIDEO_LO, VIDEO_HI))


def registers(cpu):
    return ('AF=%04X BC=%04X DE=%04X HL=%04X IX=%04X IY=%04X SP=%04X PC=%04X'
            % (cpu.af, cpu.bc, cpu.de, cpu.hl, cpu.ix, cpu.iy, cpu.sp, cpu.pc))


def hexdump(ram, start, length):
    out = []
    for a in range(start, start + length, 16):
        chunk = ram[a:min(a + 16, start + length)]
        out.append('%04X  %-47s  %s' % (a & 0xFFFF, ' '.join('%02X' % b for b in chunk),
                                        ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)))
    return out


def parse_addr(s):
    from .asm import parse_addr as p
    return p(s)


def parse_range(s):
    try:
        a, n = s.split(',')
        return parse_addr(a), parse_addr(n)
    except ValueError:
        raise argparse.ArgumentTypeError('expected ADDR,LEN, got %r' % s)


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python3 -m z80.run',
                                 description='Run a machine-language program in the core, headless.')
    ap.add_argument('file', help='.cmd, .cas, .bin (with --org) or .asm')
    ap.add_argument('--org', type=parse_addr, metavar='ADDR',
                    help='the load address of a .bin file, or of .asm source with no ORG')
    ap.add_argument('--entry', type=parse_addr, metavar='ADDR',
                    help='where to start (default: the file\'s transfer address, else its first block)')
    ap.add_argument('--arg', type=parse_addr, default=0, metavar='N',
                    help='the USR argument a CALL 0A7FH fetches into HL (default 0)')
    ap.add_argument('--sp', type=parse_addr, default=0xFF00, metavar='ADDR',
                    help='the stack pointer at entry (default 0FF00H)')
    ap.add_argument('--cycles', type=int, default=DEFAULT_CYCLES, metavar='N',
                    help='the T-state budget (default %d, about 11 s of the machine)' % DEFAULT_CYCLES)
    g = ap.add_mutually_exclusive_group()
    g.add_argument('--screen', action='store_true', help='print the screen even if nothing was written to it')
    g.add_argument('--no-screen', action='store_true', help='never print the screen')
    ap.add_argument('--regs', action='store_true', help='print the registers at the end')
    ap.add_argument('--dump', type=parse_range, action='append', default=[], metavar='ADDR,LEN',
                    help='hex-dump this range of memory at the end (repeatable)')
    ap.add_argument('--quiet', action='store_true', help='print nothing but what --dump asks for')
    a = ap.parse_args(argv)

    try:
        segments, entry, name = load_file(a.file, org=a.org, entry=a.entry)
    except (LoadError, OSError) as e:
        sys.stderr.write('%s\n' % e)
        return 1
    h = Headless(a.cycles)
    h.load(segments)
    how, detail = h.run(entry, a.arg, a.sp)
    m = h.machine
    out = []
    if not a.quiet:
        blocks = ', '.join('%d bytes at %04XH' % (len(d), o) for o, d in segments)
        out.append('%s: %s; entry %04XH' % (a.file, blocks, entry))
        out.append('%s; HL = %d (%04XH); %s T-states, %.3f s at %.5f MHz'
                   % (detail, m.cpu.hl, m.cpu.hl, format(m.cycles, ','), m.cycles / (MHZ * 1e6), MHZ))
        if a.regs:
            out.append(registers(m.cpu))
        if a.screen or (h.wrote_video() and not a.no_screen):
            out.append('+' + '-' * 64 + '+')
            out += ['|' + r + '|' for r in h.screen()]
            out.append('+' + '-' * 64 + '+')
    for start, length in a.dump:
        out += hexdump(m.ram, start, length)
    sys.stdout.write('\n'.join(out) + ('\n' if out else ''))
    if how in ('ret', 'result'):
        return 0
    return 2 if how == 'budget' else 1


if __name__ == '__main__':
    sys.exit(main())
