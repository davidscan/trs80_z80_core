"""Z80 flow tracer -- recursive descent over z80.disasm.decode().

The linear sweep in z80/disasm.py decodes every byte as if it were code,
so data mixed into a program comes out as nonsense instructions.  This
tracer decodes only what control flow can reach: it starts at the entry
points and follows each instruction's successors.

    a fall-through                  most instructions
    a target, no fall-through       JP nn, JR e
    a target and a fall-through     JP cc / JR cc / DJNZ / CALL / RST
    a fall-through only             RET cc
    nothing                         RET, RETI, RETN, HALT
    INDIRECT                        JP (HL) / (IX) / (IY): the target is
                                    known only at run time; the path stops
                                    and the jump is reported

Every byte an instruction occupies is CODE.  A byte nothing reaches stays
UNKNOWN: it is not called data, because nothing proves that either.  A
path that lands inside an instruction already decoded, or whose
instruction would overlap one, is a CONFLICT: it is reported and that
path stops; the first decoding keeps the bytes.

Targets outside the loaded bytes (a call into the ROM) are recorded as
external, never followed.  Undocumented opcodes on a path are code -- the
CPU runs them -- and are reported by kind.

`steps` records the worklist as it runs, one line per step: --explain.

    python3 -m z80.trace FILE.cmd
    python3 -m z80.trace ROUTINE.bin --base 7F00H --entry 7F40H --explain
    python3 -m z80.trace --hex "CD 04 70 C9 C9" --base 7000H
"""

from dataclasses import dataclass, field
from typing import Optional

from .disasm import decode, source_text, db_text

# Undocumented opcodes by kind, and whether the kind is a
# STRONG sign the bytes are data (real code almost never holds one) or a
# WEAK one (a trick some programmers used on purpose).  The tracer only reports
# them; the grade matters to guessed paths, which come later.
UNDOC_STRONG = {
    'hole': True,           # an ED opcode with no instruction: ED 00
    'mirror': True,         # a second encoding of NEG, IM, RETN, NOP, BIT
    'prefix': True,         # DD/FD on an instruction that does not use IX/IY
    'index-half': False,    # IXH, IXL, IYH, IYL
    'sll': False,           # SLL r, SLL (IX+d)
    'index-copy': False,    # DDCB/FDCB that also copies to a register
    'in-out-c': False,      # IN F,(C), OUT (C),0
}

_HALVES = ('IXH', 'IXL', 'IYH', 'IYL')


def undoc_kind(ins):
    """The kind of an undocumented instruction, or None if documented."""
    op = ins.op
    if op is None or op.kind == 'invalid':
        return 'hole'
    if ins.ignored_prefixes:
        return 'prefix'
    if not op.undoc:
        return None
    text = ins.text
    if op.prefix[:1] in ((0xDD,), (0xFD,)):
        if any(h in text for h in _HALVES):
            return 'index-half'
        if 'IX' not in text and 'IY' not in text:
            return 'prefix'
        if op.mnemonic == 'SLL':
            return 'sll'
        if text.count(',') > (1 if op.mnemonic in ('BIT', 'RES', 'SET') else 0):
            return 'index-copy'
        return 'mirror'
    if op.mnemonic == 'SLL':
        return 'sll'
    if op.prefix == (0xED,) and op.opcode in (0x70, 0x71):
        return 'in-out-c'
    return 'mirror'


@dataclass(frozen=True)
class Conflict:
    addr: int                   # where the path tried to decode
    inside: int                 # the instruction already holding the bytes
    source: Optional[int]       # the instruction that led there (None: an entry)


@dataclass
class Result:
    entries: list
    mem: dict                                   # addr -> byte, the loaded image
    insns: dict = field(default_factory=dict)   # head addr -> Insn
    owner: dict = field(default_factory=dict)   # byte addr -> head addr
    conflicts: list = field(default_factory=list)
    indirect: list = field(default_factory=list)    # JP (HL)/(IX)/(IY) addrs
    computed: list = field(default_factory=list)    # RET straight after PUSH
    external: dict = field(default_factory=dict)    # target -> [from, ...]
    truncated: list = field(default_factory=list)   # cut off by the image's end
    undoc: list = field(default_factory=list)       # (addr, kind)
    steps: list = field(default_factory=list)

    def map(self, start, length):
        """'C' per code byte, '.' per unknown, over [start, start+length)."""
        return ''.join('C' if (start + i) & 0xFFFF in self.owner else '.'
                       for i in range(length))

    def summary(self):
        code = len(self.owner)
        total = len(self.mem)
        return '%d of %d bytes code, %d unknown' % (code, total, total - code)


def _successors(ins):
    """(targets, falls_through, indirect) for one decoded instruction."""
    op = ins.op
    nxt = (ins.addr + ins.length) & 0xFFFF
    if op is None or op.kind == 'invalid':
        return [], True, False           # an ED hole runs as a two-byte NOP
    cond = any(o.kind == 'cond' for o in op.operands)
    if op.kind == 'jump':
        if ins.target is None:
            return [], False, True
        return [ins.target], cond or op.mnemonic == 'DJNZ', False
    if op.kind == 'call':
        return [ins.target], True, False
    if op.kind == 'ret':
        return [], cond, False
    if op.mnemonic == 'HALT':
        return [], False, False
    return [], True, False


def _window(mem, addr):
    """The loaded bytes from ADDR on: enough for the longest instruction
    behind a run of prefixes the CPU drops (DD DD DD ... 21 nn nn)."""
    out = bytearray()
    for i in range(32):
        b = mem.get((addr + i) & 0xFFFF)
        if b is None:
            break
        out.append(b)
    return bytes(out)


def _hex4(a):
    return '%04X' % a


def trace(segments, entries):
    """Trace SEGMENTS ([(org, bytes)], as z80.load returns) from ENTRIES."""
    mem = {}
    for org, data in segments:
        for i, b in enumerate(data):
            mem[(org + i) & 0xFFFF] = b
    res = Result(list(entries), mem)
    say = res.steps.append
    say('entry ' + ', '.join(_hex4(e) for e in entries))
    work = [(e & 0xFFFF, None) for e in reversed(entries)]
    fell_from = {}                   # addr -> the instruction falling into it

    while work:
        addr, src = work.pop()
        if addr not in mem:
            res.external.setdefault(addr, []).append(src)
            say('pop %s: outside the loaded bytes (external)' % _hex4(addr))
            continue
        if addr in res.insns:
            say('pop %s: already code' % _hex4(addr))
            continue
        if addr in res.owner:
            head = res.owner[addr]
            res.conflicts.append(Conflict(addr, head, src))
            say('pop %s: CONFLICT, inside the instruction at %s%s'
                % (_hex4(addr), _hex4(head),
                   ' (from %s)' % _hex4(src) if src is not None else ''))
            continue
        ins = decode(_window(mem, addr), 0, addr)
        if ins.truncated:
            res.truncated.append(addr)
            say('pop %s: %s cut off by the end of the bytes: stop'
                % (_hex4(addr), ins.text))
            continue
        span = [(addr + i) & 0xFFFF for i in range(ins.length)]
        clash = next((a for a in span if a in res.owner), None)
        if clash is not None:
            head = res.owner[clash]
            res.conflicts.append(Conflict(addr, head, src))
            say('pop %s: %s CONFLICT, overlaps the instruction at %s'
                % (_hex4(addr), ins.text, _hex4(head)))
            continue
        res.insns[addr] = ins
        for a in span:
            res.owner[a] = addr
        kind = undoc_kind(ins)
        if kind:
            res.undoc.append((addr, kind))
        text = ins.text if ins.op is not None and not ins.invalid \
            else '%s (no instruction)' % ins.text
        note = ' [undocumented: %s]' % kind if kind else ''

        targets, falls, indirect = _successors(ins)
        nxt = (addr + ins.length) & 0xFFFF
        if indirect:
            res.indirect.append(addr)
            say('pop %s: %s%s -> indirect, target unknown: stop'
                % (_hex4(addr), text, note))
            continue
        if ins.op is not None and ins.op.mnemonic == 'RET' and not falls:
            prev = fell_from.get(addr)
            if prev is not None and res.insns[prev].op.mnemonic == 'PUSH':
                res.computed.append(addr)
                note += ' [after PUSH: possible computed jump]'
        queue = list(targets) + ([nxt] if falls else [])
        if falls:
            fell_from[nxt] = addr
        for t in queue:
            work.append((t, addr))
        if queue:
            say('pop %s: %s%s -> queue %s' % (_hex4(addr), text, note,
                                              ', '.join(_hex4(t) for t in queue)))
        else:
            say('pop %s: %s%s -> end of path' % (_hex4(addr), text, note))

    res.conflicts.sort(key=lambda c: c.addr)
    res.indirect.sort()
    res.computed.sort()
    res.truncated.sort()
    res.undoc.sort()
    say('done: ' + res.summary())
    return res


def _runs(mem):
    """The loaded addresses as contiguous runs: [(start, length)]."""
    runs = []
    for a in sorted(mem):
        if runs and runs[-1][0] + runs[-1][1] == a:
            runs[-1][1] += 1
        else:
            runs.append([a, 1])
    return [(s, n) for s, n in runs]


def _lines(res):
    """(addr, raw, text, is_code) for every byte run of the image."""
    for start, n in _runs(res.mem):
        a, end = start, start + n
        while a < end:
            ins = res.insns.get(a)
            if ins is not None and a + ins.length <= end:
                yield a, ins.raw, source_text(ins), True
                a += ins.length
                continue
            b = a + 1
            while b < end and b - a < 8 and b not in res.owner:
                b += 1
            raw = bytes(res.mem[x] for x in range(a, b))
            yield a, raw, db_text(raw), False
            a = b


def source(res, segments=None):
    """Assembler source for the traced image: assembled, it gives the same
    bytes back (an ORG per contiguous run)."""
    out = []
    prev_end = None
    for a, raw, text, _ in _lines(res):
        if a != prev_end:
            out.append(' ORG %04XH' % a)
        out.append(' ' + text)
        prev_end = a + len(raw)
    out.append(' END')
    return '\n'.join(out) + '\n'


def listing(res):
    """Address, bytes, text; unknown bytes as DB marked '?'."""
    out = []
    for a, raw, text, code in _lines(res):
        hexb = ' '.join('%02X' % b for b in raw)
        out.append('%04X  %-23s %s %s' % (a, hexb, ' ' if code else '?', text))
    return '\n'.join(out)


def report(res):
    """The summary lines under a listing."""
    out = [res.summary()]
    for c in res.conflicts:
        out.append('conflict at %s: inside the instruction at %s%s'
                   % (_hex4(c.addr), _hex4(c.inside),
                      ', from %s' % _hex4(c.source) if c.source is not None else ''))
    for a in res.indirect:
        out.append('indirect jump at %s: target unknown' % _hex4(a))
    for a in res.computed:
        out.append('RET after PUSH at %s: possible computed jump' % _hex4(a))
    for t, srcs in sorted(res.external.items()):
        out.append('external %s from %s' % (_hex4(t), ', '.join(
            _hex4(s) if s is not None else 'entry' for s in srcs)))
    for a in res.truncated:
        out.append('cut off at %s' % _hex4(a))
    for a, kind in res.undoc:
        out.append('undocumented at %s: %s (%s)'
                   % (_hex4(a), kind, 'strong' if UNDOC_STRONG[kind] else 'weak'))
    return '\n'.join(out)


def _addr(text):
    t = text.strip()
    return int(t[:-1], 16) if t[-1:] in 'Hh' else int(t, 0)


def main(argv=None):
    """Trace a Z80 program from its entry points and list what is code.

        python3 -m z80.trace PROG.cmd
        python3 -m z80.trace ROUTINE.bin --base 7F00H --entry 7F40H
        python3 -m z80.trace --hex "C3 04 70 FF C9" --base 7000H --explain

    A /CMD file or a SYSTEM tape (.cas) gives its own load addresses and
    entry point; raw bytes load at --base and start there.  --entry adds
    entry points (repeatable).  Addresses: decimal, 0x.., or ..H.
    """
    import argparse
    from .load import load_file, LoadError
    ap = argparse.ArgumentParser(description=main.__doc__.split('\n\n')[0])
    ap.add_argument('file', nargs='?', help='.cmd, .cas, .asm or raw bytes; omit with --hex')
    ap.add_argument('--hex', help='the bytes as hex digits instead of a file')
    ap.add_argument('--base', default=None, help='load address of raw bytes')
    ap.add_argument('--entry', action='append', default=[], help='an entry point (repeatable)')
    ap.add_argument('--explain', action='store_true', help='print the worklist as it runs')
    ap.add_argument('--source', action='store_true',
                    help='print assembler source (gives the same bytes back)')
    a = ap.parse_args(argv)
    try:
        base = _addr(a.base) if a.base is not None else None
        extra = [_addr(e) for e in a.entry]
    except (ValueError, IndexError):
        ap.error('an address is not a number (decimal, 0x.., or ..H)')
    for v in ([base] if base is not None else []) + extra:
        if not 0 <= v <= 0xFFFF:
            ap.error('address %d is outside 0-65535' % v)
    if a.hex is not None:
        try:
            data = bytes.fromhex(a.hex.replace(' ', ''))
        except ValueError as e:
            ap.error('--hex: %s' % e)
        org = base or 0
        segments, entry = [(org, data)], org
    elif a.file:
        try:
            segments, entry, _ = load_file(a.file, org=base if base is not None else 0)
        except (OSError, LoadError) as e:
            ap.error('%s: %s' % (a.file, getattr(e, 'strerror', None) or e))
    else:
        ap.error('a file or --hex is required')
    entries = [entry] + [e for e in extra if e != entry]
    res = trace(segments, entries)
    # Under --source the notes are comments, so the whole output assembles.
    note = (lambda t: '\n'.join('; ' + x for x in t.split('\n'))) \
        if a.source else (lambda t: t)
    if a.explain:
        print(note('\n'.join(res.steps)))
        print()
    print(source(res) if a.source else listing(res))
    print()
    print(note(report(res)))


if __name__ == '__main__':
    main()
