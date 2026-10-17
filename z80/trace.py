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
    inside: int                 # the instruction (or data range) holding the bytes
    source: Optional[int]       # the instruction that led there (None: an entry)
    kind: str = 'code'          # 'code': an instruction; 'data': a data hint


@dataclass
class Result:
    entries: list
    mem: dict                                   # addr -> byte, the loaded image
    insns: dict = field(default_factory=dict)   # head addr -> Insn
    owner: dict = field(default_factory=dict)   # byte addr -> head addr
    data: dict = field(default_factory=dict)    # byte addr -> (type, range start)
    conflicts: list = field(default_factory=list)
    indirect: list = field(default_factory=list)    # JP (HL)/(IX)/(IY) addrs
    computed: list = field(default_factory=list)    # RET straight after PUSH
    external: dict = field(default_factory=dict)    # target -> [from, ...]
    truncated: list = field(default_factory=list)   # cut off by the image's end
    undoc: list = field(default_factory=list)       # (addr, kind)
    refs: dict = field(default_factory=dict)        # target -> [(from, kind)]
    names: dict = field(default_factory=dict)       # addr -> label
    vars: set = field(default_factory=set)          # names that are RAM vars
    overrides: list = field(default_factory=list)   # names a later file took
    comments: dict = field(default_factory=dict)    # addr -> [text]
    steps: list = field(default_factory=list)

    def map(self, start, length):
        """'C' per code byte, 'D' per byte a hint makes data, '.' per
        unknown, over [start, start+length)."""
        out = []
        for i in range(length):
            a = (start + i) & 0xFFFF
            out.append('C' if a in self.owner else 'D' if a in self.data
                       else '.')
        return ''.join(out)

    def summary(self):
        code = len(self.owner)
        data = sum(1 for a in self.data if a in self.mem and a not in self.owner)
        total = len(self.mem)
        return '%d of %d bytes code, %s%d unknown' % (
            code, total, '%d data, ' % data if data else '',
            total - code - data)


# The kinds of reference, as the listing names them.  `addr` is a 16-bit
# constant that falls inside the loaded bytes (LD HL,nn): perhaps an
# address, perhaps a number; it is labelled, and marked as a guess.
REF_KINDS = ('entry', 'jump', 'call', 'table', 'read', 'write', 'addr')


def _successors(ins):
    """(targets, falls_through, indirect) for one decoded instruction."""
    op = ins.op
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


def _data_refs(ins, mem):
    """(target, kind) for the memory an instruction names by address."""
    out = []
    if ins.op is None:
        return out
    for mode, a, _ in ins.abs_addresses():
        out.append((a, 'write' if mode == 'w' else 'read'))
    if ins.op.kind not in ('jump', 'call') and ins.imm is not None and any(
            o.kind == 'imm16' for o in ins.op.operands) and ins.imm in mem:
        out.append((ins.imm, 'addr'))
    return out


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


def trace(segments, entries, hints=None):
    """Trace SEGMENTS ([(org, bytes)], as z80.load returns) from ENTRIES,
    with HINTS (a z80.hints.Hints) if given."""
    from .hints import Hints
    h = hints or Hints()
    mem = {}
    for org, data in segments:
        for i, b in enumerate(data):
            mem[(org + i) & 0xFFFF] = b
    res = Result([], mem)
    say = res.steps.append

    def ref(target, src, kind):
        res.refs.setdefault(target & 0xFFFF, []).append((src, kind))

    for lo, hi, typ in h.data:
        for a in range(lo, hi + 1):
            res.data[a] = (typ, lo)
    starts = [(e & 0xFFFF, None) for e in list(entries) + h.entries]
    starts += [(lo, None) for lo, _ in h.code]
    for t, n in h.tables:
        for a in range(t, t + 2 * n):
            res.data[a & 0xFFFF] = ('words', t)
        for i in range(n):
            lo, hi = mem.get((t + 2 * i) & 0xFFFF), mem.get((t + 2 * i + 1) & 0xFFFF)
            if lo is not None and hi is not None:
                starts.append((lo | hi << 8, (t + 2 * i) & 0xFFFF))
    uniq = []
    for a, src in starts:
        if (a, src) not in uniq:
            uniq.append((a, src))
            if a not in res.entries:
                res.entries.append(a)
            ref(a, src, 'table' if src is not None else 'entry')
    say('entry ' + ', '.join(_hex4(e) for e in res.entries))
    work = list(reversed(uniq))
    fell_from = {}                   # addr -> the instruction falling into it
    forced = [a for lo, hi in h.code for a in range(lo, hi + 1)]
    popped = set()                   # every address a path has tried

    while True:
        if not work:
            # a `code` hint: its first byte nothing has reached yet starts
            # a new path, until the range is code or will not decode
            nxt = next((a for a in forced if a in mem and a not in res.owner
                        and a not in res.data and a not in popped), None)
            if nxt is None:
                break
            say('code hint: %s not reached yet' % _hex4(nxt))
            work.append((nxt, None))
            continue
        addr, src = work.pop()
        popped.add(addr)
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
        clash = next((a for a in span if a in res.data), None)
        if clash is not None:
            start = res.data[clash][1]
            res.conflicts.append(Conflict(addr, start, src, 'data'))
            say('pop %s: %s CONFLICT, runs into the data hinted at %s'
                % (_hex4(addr), ins.text, _hex4(start)))
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
        drefs = _data_refs(ins, mem)
        for t, k in drefs:
            ref(t, addr, k)
        if drefs:
            note += ' [data ref %s]' % ', '.join(
                '%s %s' % (_hex4(t), k) for t, k in drefs)

        targets, falls, indirect = _successors(ins)
        nxt = (addr + ins.length) & 0xFFFF
        if indirect:
            res.indirect.append(addr)
            say('pop %s: %s%s -> indirect, target unknown: stop'
                % (_hex4(addr), text, note))
            continue
        for t in targets:
            ref(t, addr, ins.op.kind)
        if ins.op is not None and ins.op.mnemonic == 'RET' and not falls:
            prev = fell_from.get(addr)
            if prev is not None and res.insns[prev].op.mnemonic == 'PUSH':
                res.computed.append(addr)
                note += ' [after PUSH: possible computed jump]'
        if falls and ins.op is not None and ins.op.kind == 'call' \
                and ins.target in h.inline:
            n = h.inline[ins.target]
            for i in range(n):
                b = (nxt + i) & 0xFFFF
                if b in res.owner:
                    res.conflicts.append(Conflict(b, res.owner[b], addr, 'data'))
                else:
                    res.data.setdefault(b, ('bytes', nxt))
            note += ' [inline: %d data byte%s]' % (n, 's' if n > 1 else '')
            nxt = (nxt + n) & 0xFFFF
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
    _name(res, h)
    say('done: ' + res.summary())
    return res


def _name(res, h):
    """Labels: the hints' names, then L<addr> for every referenced
    address inside the loaded bytes.  Outside them only a hint names.
    A `var` (a RAM location) names only an address outside the loaded
    bytes: a program loaded over it owns those bytes."""
    res.names = dict(h.labels)
    for a, n in h.vars.items():
        if a not in res.mem:
            res.names[a] = n
            res.vars.add(a)
    res.overrides = list(h.overrides)
    taken = {n.upper() for n in res.names.values()}
    for t in sorted(res.refs):
        if t in res.mem and t not in res.names:
            n = 'L%04X' % t
            while n.upper() in taken:
                n += '_'
            res.names[t] = n
            taken.add(n.upper())
    res.comments = {a: list(c) for a, c in h.comments.items()
                    if not (a in h.vars and a in res.mem)}


def _named_text(ins, res):
    """The instruction's source text with names for the addresses in it;
    the plain source_text when its bytes need the DB form."""
    plain = source_text(ins)
    if plain != ins.text or ins.op is None or ins.invalid:
        return plain
    op = ins.op
    flow = op.kind in ('jump', 'call')
    parts = []
    for o in op.operands:
        t = None
        if o.kind == 'imm16' and ins.imm in res.names and (
                flow or ins.imm in res.mem) and ins.imm not in res.vars:
            t = res.names[ins.imm]
        elif o.kind == 'aimm16' and ins.imm in res.names:
            t = '(%s)' % res.names[ins.imm]
        elif o.kind == 'rel' and ins.target in res.names \
                and ins.target not in res.vars:
            t = res.names[ins.target]
        parts.append(t if t is not None else
                     o.text(imm=ins.imm, disp=ins.disp, addr=ins.target))
    return op.mnemonic + (' ' + ','.join(parts) if parts else '')


def _runs(mem):
    """The loaded addresses as contiguous runs: [(start, length)]."""
    runs = []
    for a in sorted(mem):
        if runs and runs[-1][0] + runs[-1][1] == a:
            runs[-1][1] += 1
        else:
            runs.append([a, 1])
    return [(s, n) for s, n in runs]


def _printable(b):
    return 0x20 <= b <= 0x7E


def _data_text(raw, typ, res):
    """Source for a data run: DM for text, DW for words, DB otherwise."""
    if typ == 'text' and all(_printable(b) for b in raw):
        return "DM '%s'" % raw.decode('ascii').replace("'", "''")
    if typ == 'words' and len(raw) % 2 == 0:
        ws = [raw[i] | raw[i + 1] << 8 for i in range(0, len(raw), 2)]
        return 'DW ' + ','.join(_word(w, res) for w in ws)
    return db_text(raw)


def _hexw(w):
    """A 16-bit number as the assembler reads hex: 7000H, 0C000H."""
    t = '%04XH' % w
    return '0' + t if t[0] in 'ABCDEF' else t


def _word(w, res):
    return res.names.get(w) or _hexw(w)


def _lines(res):
    """(addr, raw, text, flag) for every run of the image; flag is ' ' for
    code, 'D' for hinted data, '?' for unknown bytes."""
    for start, n in _runs(res.mem):
        a, end = start, start + n
        while a < end:
            ins = res.insns.get(a)
            if ins is not None and a + ins.length <= end:
                yield a, ins.raw, _named_text(ins, res), ' '
                a += ins.length
                continue
            typ = res.data.get(a, (None,))[0] if a not in res.owner else None
            limit = {'text': 32, 'words': 8}.get(typ, 8)
            b = a + 1
            while (b < end and b - a < limit and b not in res.owner
                   and b not in res.names
                   and res.data.get(b, (None,))[0] == typ):
                if typ == 'text' and _printable(res.mem[b]) != _printable(res.mem[a]):
                    break
                b += 1
            raw = bytes(res.mem[x] for x in range(a, b))
            yield a, raw, _data_text(raw, typ, res), 'D' if typ else '?'
            a = b


def _note(res, a):
    """The comment for the line at A: who refers to it, and hint comments."""
    parts = []
    srcs = [(s, k) for s, k in res.refs.get(a, []) if s is not None]
    if srcs:
        parts.append('from ' + ', '.join('%s %s' % (_hex4(s), k)
                                         for s, k in sorted(set(srcs))))
    parts += res.comments.get(a, [])
    return '; ' + '; '.join(parts) if parts else ''


def _uses(res, a):
    """Does the listing write the name of A?  A var only in (nn)."""
    kinds = {k for _, k in res.refs.get(a, [])}
    return bool(kinds & {'read', 'write'} if a in res.vars else kinds)


def source(res, segments=None):
    """Assembler source for the traced image: assembled, it gives the same
    bytes back.  Labels sit on their lines; a name that cannot (outside
    the bytes, or inside an instruction) is an EQU at the top, if the
    program refers to it."""
    lines = list(_lines(res))
    at_line = {a for a, _, _, _ in lines}
    out = []
    for a in sorted(res.names):
        # an outside name is written only if the program uses it
        if a not in at_line and (a in res.mem or _uses(res, a)):
            c = res.comments.get(a)
            out.append(('%-8s EQU %s %s' % (res.names[a], _hexw(a),
                                            '; ' + '; '.join(c) if c else '')).rstrip())
    prev_end = None
    for a, raw, text, _ in lines:
        if a != prev_end:
            out.append('         ORG %s' % _hexw(a))
        note = _note(res, a)
        out.append(('%-8s %s %s' % (res.names.get(a, ''), text, note)).rstrip())
        prev_end = a + len(raw)
    entry = res.entries[0] if res.entries else None
    out.append('         END' + (' %s' % _word(entry, res)
                                if entry is not None and entry in res.mem else ''))
    return '\n'.join(out) + '\n'


def listing(res):
    """Address, bytes, flag (' ' code, D data, ? unknown), label, text,
    and who refers to the line."""
    out = []
    for a, raw, text, flag in _lines(res):
        hexb = ' '.join('%02X' % b for b in raw)
        if len(hexb) > 23:
            hexb = hexb[:20] + '...'
        line = '%04X  %-23s %s %-8s %s %s' % (a, hexb, flag,
                                             res.names.get(a, ''), text,
                                             _note(res, a))
        out.append(line.rstrip())
    return '\n'.join(out)


def report(res):
    """The summary lines under a listing."""
    out = [res.summary()]
    for c in res.conflicts:
        what = 'the data hinted at' if c.kind == 'data' else 'the instruction at'
        out.append('conflict at %s: inside %s %s%s'
                   % (_hex4(c.addr), what, _hex4(c.inside),
                      ', from %s' % _hex4(c.source) if c.source is not None else ''))
    for a in res.indirect:
        out.append('indirect jump at %s: target unknown' % _hex4(a))
    for a in res.computed:
        out.append('RET after PUSH at %s: possible computed jump' % _hex4(a))
    for t, srcs in sorted(res.external.items()):
        out.append('external %s%s from %s' % (
            _hex4(t), ' (%s)' % res.names[t]
            if t in res.names and t not in res.vars else '',
            ', '.join(_hex4(s) if s is not None else 'entry' for s in srcs)))
    for a in res.truncated:
        out.append('cut off at %s' % _hex4(a))
    for a, kind in res.undoc:
        out.append('undocumented at %s: %s (%s)'
                   % (_hex4(a), kind, 'strong' if UNDOC_STRONG[kind] else 'weak'))
    for o in res.overrides:
        out.append('hint override: ' + o)
    return '\n'.join(out)


def main(argv=None):
    """Trace a Z80 program from its entry points and list what is code.

        python3 -m z80.trace PROG.cmd
        python3 -m z80.trace ROUTINE.bin --base 7F00H --entry 7F40H
        python3 -m z80.trace --hex "C3 04 70 FF C9" --base 7000H --explain
        python3 -m z80.trace PROG.cmd --hints PROG.hints --hints hints/model1.hints

    A /CMD file or a SYSTEM tape (.cas) gives its own load addresses and
    entry point; raw bytes load at --base and start there.  --entry adds
    entry points; --hints reads a hints file (both repeatable).
    Addresses: decimal, 0x.., or ..H.
    """
    import argparse
    from .load import load_file, LoadError
    from . import hints as hintmod
    ap = argparse.ArgumentParser(description=main.__doc__.split('\n\n')[0])
    ap.add_argument('file', nargs='?', help='.cmd, .cas, .asm or raw bytes; omit with --hex')
    ap.add_argument('--hex', help='the bytes as hex digits instead of a file')
    ap.add_argument('--base', default=None, help='load address of raw bytes')
    ap.add_argument('--entry', action='append', default=[], help='an entry point (repeatable)')
    ap.add_argument('--hints', action='append', default=[], help='a hints file (repeatable)')
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
    h = hintmod.Hints()
    for path in a.hints:
        try:
            h.merge(hintmod.load(path))
        except OSError as e:
            ap.error('%s: %s' % (path, e.strerror))
        except (hintmod.HintError, UnicodeDecodeError) as e:
            ap.error(str(e))
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
    res = trace(segments, entries, h)
    # Under --source the notes are comments, so the whole output assembles.
    note = (lambda t: '\n'.join('; ' + x for x in t.split('\n'))) \
        if a.source else (lambda t: t)
    if a.explain:
        print(note('\n'.join(res.steps)))
        print()
    print(source(res) if a.source else listing(res))
    print()
    print(note(report(res)))


def _addr(text):
    t = text.strip()
    return int(t[:-1], 16) if t[-1:] in 'Hh' else int(t, 0)


if __name__ == '__main__':
    main()
