"""Z80 flow tracer -- recursive descent over z80.disasm.decode().

The linear sweep in z80/disasm.py decodes every byte as if it were code,
so data mixed into a program comes out as nonsense instructions.  This
tracer decodes only what control flow can reach: it starts at the entry
points and follows each instruction's successors.

    a fall-through                  most instructions
    a target, no fall-through       JP nn, JR e; an unconditional CALL
                                    or RST to a `noreturn` hint
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

With `tables` (--guess-tables) the tracer also follows the jump tables an
address constant in traced code names (`_guess_tables`): two or more words
in a row, or records of a key byte and a word ended by a zero key, each
word the address of bytes in the image.  Each table is traced on a copy
first and dropped if it adds a conflict or runs into a strong undocumented
opcode; everything a kept table reaches is code marked GUESSED, never
proven.

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


@dataclass(frozen=True)
class Table:
    """A jump table `tables=True` guessed and kept."""
    addr: int                   # its first byte
    count: int                  # words, or keyed records
    keyed: bool                 # DB key, DW address records, a zero key ends
    #                             them; every key C3H: a vector of JP nn
    #                             instructions, traced as code (`vector`)
    source: int                 # the instruction whose constant names it
    grade: str = 'strong'       # 'weak': an undocumented opcode of the weak
    #                             kind on the path it opened (D6)


@dataclass
class Result:
    entries: list
    mem: dict                                   # addr -> byte, the loaded image
    insns: dict = field(default_factory=dict)   # head addr -> Insn
    owner: dict = field(default_factory=dict)   # byte addr -> head addr
    data: dict = field(default_factory=dict)    # byte addr -> (type, range start)
    guess: dict = field(default_factory=dict)   # byte addr -> (type, run start):
    #                                             S3's guesses for unknown bytes
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
    why: dict = field(default_factory=dict)         # addr -> why it is what
    #   it is: for an instruction's head, how the path reached it; for the
    #   first byte of a data, guess or inline run, what made it data
    guessed: set = field(default_factory=set)       # heads of instructions a
    #                                                 guessed table led to
    tables: list = field(default_factory=list)      # [Table] kept
    dropped: list = field(default_factory=list)     # (addr, count, keyed, why)
    steps: list = field(default_factory=list)

    def map(self, start, length):
        """'C' per code byte ('c' if a guessed table led there), 'D' per
        byte a hint makes data, a guess's letter (t text, w words, k the
        keys of a keyed table, f fill) per guessed byte, '.' per unknown,
        over [start, start+length)."""
        out = []
        for i in range(length):
            a = (start + i) & 0xFFFF
            out.append(('c' if self.owner[a] in self.guessed else 'C')
                       if a in self.owner else 'D' if a in self.data
                       else GUESS_FLAG[self.guess[a][0]] if a in self.guess
                       else '.')
        return ''.join(out)

    def summary(self):
        code = len(self.owner)
        gcode = sum(1 for h in self.owner.values() if h in self.guessed)
        data = sum(1 for a in self.data if a in self.mem and a not in self.owner)
        kinds = {}
        for t, _ in self.guess.values():
            kinds[t] = kinds.get(t, 0) + 1
        guessed = sum(kinds.values())
        total = len(self.mem)
        return '%d of %d bytes code%s, %s%s%d unknown' % (
            code, total, ' (%d guessed)' % gcode if gcode else '',
            '%d data, ' % data if data else '',
            '%d guessed data (%s), ' % (guessed, ', '.join(
                '%d %s' % (kinds[t], t) for t in GUESS_TYPES if t in kinds))
            if guessed else '', total - code - data - guessed)


# The kinds of reference, as the listing names them.  `addr` is a 16-bit
# constant that falls inside the loaded bytes (LD HL,nn): perhaps an
# address, perhaps a number; it is labelled, and marked as a guess.
# `word` is a word of a table S3 guessed: a guess too.
REF_KINDS = ('entry', 'jump', 'call', 'table', 'read', 'write', 'addr', 'word')

# S3: what unknown bytes are guessed to be, and the listing's flag for each.
GUESS_TYPES = ('words', 'keys', 'text', 'fill')
GUESS_FLAG = {'words': 'w', 'keys': 'k', 'text': 't', 'fill': 'f'}
MIN_WORDS = 2       # words in a row, each the address of a traced instruction
#                     (S3), or of bytes in the image (a guessed table's)
MIN_TEXT = 5        # printable bytes in a row, one of them a letter
MIN_FILL = 4        # identical bytes in a row
TEXT_ENDS = (0x00, 0x0D, 0x03)  # a terminator a text run takes with it


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


def _until(mem, start, end):
    """How many bytes from START up to and including the first that ends
    inline data (END a byte, or 'bit7'); None if the loaded bytes run out
    first."""
    n, a = 0, start
    while a in mem and n < 0x10000:
        b = mem[a]
        n += 1
        if (b & 0x80) if end == 'bit7' else b == end:
            return n
        a = (a + 1) & 0xFFFF
    return None


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


def trace(segments, entries, hints=None, guess=True, tables=False):
    """Trace SEGMENTS ([(org, bytes)], as z80.load returns) from ENTRIES,
    with HINTS (a z80.hints.Hints) if given; with TABLES, follow the jump
    tables the code's constants name, marked guessed (D5, `_guess_tables`);
    then, unless GUESS is false, guess what the bytes nothing reached are
    (S3, `_guess`)."""
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
        res.why[lo] = 'data hint'
    # the worklist holds (address, the instruction that led there or None,
    # how it led there); `how` becomes the instruction's `why`
    starts = [(e & 0xFFFF, None, 'entry') for e in entries]
    starts += [(e & 0xFFFF, None, 'entry hint') for e in h.entries]
    starts += [(lo, None, 'code hint') for lo, _ in h.code]
    for t, n in h.tables:
        for a in range(t, t + 2 * n):
            res.data[a & 0xFFFF] = ('words', t)
        res.why[t] = 'table hint'
        for i in range(n):
            lo, hi = mem.get((t + 2 * i) & 0xFFFF), mem.get((t + 2 * i + 1) & 0xFFFF)
            if lo is not None and hi is not None:
                starts.append((lo | hi << 8, (t + 2 * i) & 0xFFFF, 'table'))
    uniq = []
    for a, src, how in starts:
        if all(u[:2] != (a, src) for u in uniq):
            uniq.append((a, src, how))
            if a not in res.entries:
                res.entries.append(a)
            ref(a, src, 'table' if src is not None else 'entry')
    say('entry ' + ', '.join(_hex4(e) for e in res.entries))
    st = {'fell_from': {},           # addr -> the instruction falling into it
          'forced': [a for lo, hi in h.code for a in range(lo, hi + 1)],
          'popped': set()}           # every address a path has tried
    _run(res, h, list(reversed(uniq)), st)
    if tables:
        res = _guess_tables(res, h, st)
    say = res.steps.append
    if guess:
        _guess(res, say)
    res.conflicts.sort(key=lambda c: c.addr)
    res.indirect.sort()
    res.computed.sort()
    res.truncated.sort()
    res.undoc.sort()
    _name(res, h)
    say('done: ' + res.summary())
    return res


def _run(res, h, work, st):
    """Run the worklist WORK ([(addr, the instruction that led there or
    None, how)]) to exhaustion over RES, with the hints H; ST carries
    the loop's state between runs (`fell_from`, `forced`, `popped`)."""
    mem, say = res.mem, res.steps.append
    fell_from, forced, popped = st['fell_from'], st['forced'], st['popped']

    def ref(target, src, kind):
        res.refs.setdefault(target & 0xFFFF, []).append((src, kind))

    while True:
        if not work:
            # a `code` hint: its first byte nothing has reached yet starts
            # a new path, until the range is code or will not decode
            nxt = next((a for a in forced if a in mem and a not in res.owner
                        and a not in res.data and a not in popped), None)
            if nxt is None:
                break
            say('code hint: %s not reached yet' % _hex4(nxt))
            work.append((nxt, None, 'code hint'))
            continue
        addr, src, how = work.pop()
        popped.add(addr)
        guessed = how in ('guessed table', 'guessed vector') or src in res.guessed
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
        clash = next((a for a in span if a in res.data or a in res.guess), None)
        if clash is not None:
            hinted = clash in res.data
            start = (res.data if hinted else res.guess)[clash][1]
            res.conflicts.append(Conflict(addr, start, src, 'data'))
            say('pop %s: %s CONFLICT, runs into the %s at %s'
                % (_hex4(addr), ins.text,
                   'data hinted' if hinted else 'table guessed', _hex4(start)))
            continue
        res.insns[addr] = ins
        for a in span:
            res.owner[a] = addr
        if guessed:
            res.guessed.add(addr)
        res.why[addr] = _why(how, src)
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
        call = falls and ins.op is not None and ins.op.kind == 'call'
        skipped = 0
        if call and ins.target in h.noreturn and not any(
                o.kind == 'cond' for o in ins.op.operands) and (
                h.noreturn[ins.target] == 'call' or ins.op.mnemonic == 'RST'):
            falls = False
            note += ' [never returns]'
        elif call and ins.target in h.inline:
            spec = h.inline[ins.target]
            n = spec if isinstance(spec, int) else _until(mem, nxt, spec[1])
            if n is None:
                # no terminator before the bytes end: the path stops
                res.truncated.append(addr)
                falls = False
                note += ' [inline: no terminator before the end of the bytes]'
            else:
                typ = 'bytes' if isinstance(spec, int) else 'text'
                for i in range(n):
                    b = (nxt + i) & 0xFFFF
                    if b in res.owner:
                        res.conflicts.append(Conflict(b, res.owner[b], addr, 'data'))
                    else:
                        res.data.setdefault(b, (typ, nxt))
                if nxt in res.data and res.data[nxt] == (typ, nxt):
                    res.why.setdefault(nxt, 'inline data for the %s at %s'
                                       % (ins.op.mnemonic, _hex4(addr)))
                note += ' [inline: %d data byte%s]' % (n, 's' if n > 1 else '')
                nxt = (nxt + n) & 0xFFFF
                skipped = n
        queue = [(t, ins.op.kind) for t in targets]
        if falls:
            fell_from[nxt] = addr
            queue.append((nxt, ('skip', skipped) if skipped else 'fall'))
        for t, k in queue:
            work.append((t, addr, k))
        queue = [t for t, _ in queue]
        if queue:
            say('pop %s: %s%s -> queue %s' % (_hex4(addr), text, note,
                                              ', '.join(_hex4(t) for t in queue)))
        else:
            say('pop %s: %s%s -> end of path' % (_hex4(addr), text, note))


def _why(how, src):
    """The reason an instruction is code: HOW its path reached it, from
    the instruction at SRC."""
    if isinstance(how, tuple):          # ('skip', n): the fall-through past
        n = how[1]                      # a call's inline data
        return 'continues from %s past %d inline byte%s' % (
            _hex4(src), n, 's' if n > 1 else '')
    if how in ('entry', 'entry hint', 'code hint'):
        return how
    if how == 'table':
        return 'table at %s' % _hex4(src)
    if how == 'guessed table':
        return 'guessed table at %s' % _hex4(src)
    if how == 'guessed vector':
        return 'guessed jump vector, named at %s' % _hex4(src)
    return {'jump': 'jump from %s', 'call': 'call from %s',
            'fall': 'falls from %s'}[how] % _hex4(src)


def _guess_tables(res, h, st):
    """D5: follow the jump tables the traced code's constants name.

    A candidate is a 16-bit constant in a traced instruction (LD HL,TAB:
    an `addr` ref) pointing at bytes nothing reached, where MIN_WORDS or
    more words in a row each point at a byte inside the loaded image and
    not into hinted data or another table (`_table_at`); first as plain
    words, then as records of a key byte and a word that a zero key ends
    (LD DE,TAB / DB key, DW routine ...); keyed records whose every key
    is C3H are a vector of JP nn instructions, so the records are traced
    as code themselves (a CP/M BIOS's jump vector).  Each candidate is traced on a
    copy of the result and kept only if that adds no conflict and runs
    into no undocumented opcode of the STRONG kind (D6); a WEAK one is
    kept with the table's grade lowered.  Every instruction a kept table
    leads to is marked guessed, never proven.  New constants in guessed
    code can name more tables, so this repeats until none is new.

    On the 86 identical period pairs with an entry in their own bytes
    (2026-10-21) the plain pattern alone found nothing (their tables'
    words point at ROM entries or 0 before the second word); the keyed
    one found 2,033 code bytes for 9 data bytes called code, in 5 pairs.
    Returns the result to go on with (the copy, where a table was kept)."""
    say = lambda s: res.steps.append(s)       # noqa: E731 (res is rebound)
    tried = set()
    while True:
        cands = [(t, n, keyed, src) for t, n, keyed, src in _table_candidates(res)
                 if t not in tried]
        if not cands:
            return res
        for t, n, keyed, src in cands:
            tried.add(t)
            say('guess table at %s: %d %s, from %s: trace it'
                % (_hex4(t), n, 'keyed records' if keyed else 'words', _hex4(src)))
            trial, tst = _fork(res), {'fell_from': dict(st['fell_from']),
                                       'forced': [], 'popped': set(st['popped'])}
            work = _mark_table(trial, t, n, keyed, src)
            _run(trial, h, work, tst)
            new = trial.conflicts[len(res.conflicts):]
            undoc = [(a, k) for a, k in trial.undoc[len(res.undoc):] if a in trial.guessed]
            strong = [(a, k) for a, k in undoc if UNDOC_STRONG[k]]
            if new or strong:
                why = ('a conflict at %s' % _hex4(new[0].addr) if new
                       else 'an undocumented %s at %s' % (strong[0][1], _hex4(strong[0][0])))
                res.dropped.append((t, n, keyed, why))
                res.steps = trial.steps
                say('drop the table at %s: %s' % (_hex4(t), why))
                continue
            trial.tables.append(Table(t, n, keyed, src, 'weak' if undoc else 'strong'))
            if undoc:
                say('keep the table at %s, graded weak: undocumented %s at %s'
                    % (_hex4(t), undoc[0][1], _hex4(undoc[0][0])))
            else:
                say('keep the table at %s' % _hex4(t))
            res, st = trial, tst


def _table_candidates(res):
    """[(addr, count, keyed, source)]: every `addr` constant in traced
    code that starts a table by the rule in `_guess_tables`."""
    out = []
    for t, lst in sorted(res.refs.items()):
        srcs = [s for s, k in lst if k == 'addr' and s is not None]
        if not srcs or t not in res.mem or t in res.owner or t in res.data \
                or t in res.guess:
            continue
        for keyed in (False, True):
            n = _table_at(res, t, keyed)
            if n >= MIN_WORDS:
                out.append((t, n, keyed, min(srcs)))
                break
    return out


def _table_at(res, t, keyed):
    """How many records (a word, or a key byte and a word) in a row from
    T each hold the address of a byte in the image, over bytes nothing
    has claimed; a keyed table ends at a zero key."""
    mem = res.mem

    def free(a):
        a &= 0xFFFF
        return a in mem and a not in res.owner and a not in res.data \
            and a not in res.guess

    n, a = 0, t
    while n < 0x8000:
        if keyed and (not free(a) or mem[a & 0xFFFF] == 0):
            break
        slot = a + (1 if keyed else 0)
        if not (free(slot) and free(slot + 1)):
            break
        w = mem[slot & 0xFFFF] | mem[(slot + 1) & 0xFFFF] << 8
        if w not in mem or w in res.data or w in res.guess:
            break
        n += 1
        a += 3 if keyed else 2
    return n


def _mark_table(res, t, n, keyed, src):
    """Mark the table at T as guessed data in RES and return the worklist
    of its words' targets; a vector of JP nn instructions is not marked
    (its records are traced as code) and the worklist is the records."""
    stride = 3 if keyed else 2
    if keyed and _vector(res, t, n):        # each JP's `why` says it
        return [((t + 3 * i) & 0xFFFF, src, 'guessed vector') for i in reversed(range(n))]
    work = []
    for i in range(n):
        a = (t + stride * i) & 0xFFFF
        if keyed:
            res.guess[a] = ('keys', t)
        slot = (a + stride - 2) & 0xFFFF
        res.guess[slot] = res.guess[(slot + 1) & 0xFFFF] = ('words', t)
        w = res.mem[slot] | res.mem[(slot + 1) & 0xFFFF] << 8
        res.refs.setdefault(w, []).append((slot, 'table'))
        work.append((w, slot, 'guessed table'))
    res.why[t] = ('guessed keyed table: %d records of a key byte and an address '
                  'in the image, ended by a zero key, from %s' if keyed else
                  'guessed table: %d words, each an address in the image, from %s'
                  ) % (n, _hex4(src))
    return list(reversed(work))


def _vector(res, t, n):
    """Is the keyed table at T a run of N `JP nn` instructions?"""
    return all(res.mem[(t + 3 * i) & 0xFFFF] == 0xC3 for i in range(n))


def _fork(res):
    """A copy of RES to trace a guess on: its image is shared, everything
    a trace writes is copied."""
    out = Result(list(res.entries), res.mem)
    for name in ('insns', 'owner', 'data', 'guess', 'external', 'refs', 'names',
                 'comments', 'why'):
        v = getattr(res, name)
        setattr(out, name, {k: list(x) if isinstance(x, list) else x
                            for k, x in v.items()})
    for name in ('conflicts', 'indirect', 'computed', 'truncated', 'undoc',
                 'overrides', 'tables', 'dropped', 'steps'):
        setattr(out, name, list(getattr(res, name)))
    out.vars, out.guessed = set(res.vars), set(res.guessed)
    return out


def _guess(res, say):
    """S3: classify the bytes that are neither code nor hinted data, by
    conservative rules, in this order; every one is a guess, kept apart
    from proven code and from hints, and nothing is traced from it.

      words   MIN_WORDS or more words in a row, each the address of an
              instruction the trace decoded: a table of routines
      text    MIN_TEXT or more printable ASCII bytes (20H-7EH), one of
              them a letter and not all the same, with one terminator
              after them if there is one: 00H, 0DH or 03H, or a last
              character with bit 7 set (not counted: an opcode such as
              C9H or CDH after four printable bytes of code passes for
              one)

    The thresholds were set against the 86 period pairs whose objects
    have an entry: four bytes, or the bit-7 character counted, called
    two to five times as much missed code text.
      fill    MIN_FILL or more identical bytes

    Anything else stays unknown (DB in the listing)."""
    free = {a for a in res.mem if a not in res.owner and a not in res.data
            and a not in res.guess}             # a guessed table's bytes are taken

    def mark(lo, n, typ, why):
        for i in range(n):
            res.guess[(lo + i) & 0xFFFF] = (typ, lo)
            free.discard((lo + i) & 0xFFFF)
        res.why[lo] = 'guessed %s: %s' % (typ, why)
        say('guess %s-%s: %s' % (_hex4(lo), _hex4((lo + n - 1) & 0xFFFF), typ))

    def word(a):
        if not all((a + i) & 0xFFFF in free for i in (0, 1)):
            return None
        return res.mem[a] | res.mem[(a + 1) & 0xFFFF] << 8

    for start, length in _runs(res.mem):
        a, end = start, start + length
        while a < end - 1:
            n = 0
            while a + 2 * n + 1 < end and word(a + 2 * n) in res.insns:
                n += 1
            if n >= MIN_WORDS:
                for i in range(n):
                    res.refs.setdefault(word(a + 2 * i), []).append((a + 2 * i, 'word'))
                mark(a, 2 * n, 'words', '%d, each the address of code' % n)
                a += 2 * n
            else:
                a += 1
    for start, length in _runs(res.mem):
        a, end = start, start + length
        while a < end:
            b = a
            while b < end and b in free and _printable(res.mem[b]):
                b += 1
            run = [res.mem[x] for x in range(a, b)]
            last = res.mem[b] if b < end and b in free else None
            bit7 = last is not None and last & 0x80 and _printable(last & 0x7F)
            if (len(run) >= MIN_TEXT and len(set(run)) > 1
                    and any(chr(x).isalpha() for x in run)):
                why = '%d printable' % len(run)
                if bit7:
                    why += ', then a character with bit 7 set'
                elif last in TEXT_ENDS:
                    why += ', then %02XH' % last
                if bit7 or last in TEXT_ENDS:
                    b += 1
                mark(a, b - a, 'text', why)
            a = max(b, a + 1)
    for start, length in _runs(res.mem):
        a, end = start, start + length
        while a < end:
            b = a
            while b < end and b in free and res.mem[b] == res.mem[a]:
                b += 1
            if b - a >= MIN_FILL:
                mark(a, b - a, 'fill', '%d x %02XH' % (b - a, res.mem[a]))
            a = max(b, a + 1)


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
    code, 'g' for code a guessed table led to, 'D' for hinted data,
    t/w/k/f for guessed data (text, words, a keyed table's keys, fill),
    '?' for unknown bytes."""
    for start, n in _runs(res.mem):
        a, end = start, start + n
        while a < end:
            ins = res.insns.get(a)
            if ins is not None and a + ins.length <= end:
                yield a, ins.raw, _named_text(ins, res), 'g' if a in res.guessed else ' '
                a += ins.length
                continue
            kind = _kind(res, a)
            typ = kind[0] if kind else None
            limit = {'text': 32, 'words': 8}.get(typ, 8)
            b = a + 1
            while (b < end and b - a < limit and b not in res.owner
                   and b not in res.names and _kind(res, b) == kind):
                if typ == 'text' and _printable(res.mem[b]) != _printable(res.mem[a]):
                    break
                b += 1
            raw = bytes(res.mem[x] for x in range(a, b))
            flag = '?' if kind is None else 'D' if kind[2] else GUESS_FLAG[typ]
            yield a, raw, _data_text(raw, typ, res), flag
            a = b


def _kind(res, a):
    """(type, run start, hinted) for a data byte, or None: a hint's
    data first, then S3's guess."""
    if a in res.owner:
        return None
    if a in res.data:
        return res.data[a] + (True,)
    if a in res.guess:
        return res.guess[a] + (False,)
    return None


def _reason(res, a):
    """The listing's reason for the line at A, or '' where the line says
    it already: a jump, call or table xref is printed as 'from', and a
    fall-through from the instruction before needs no words.  Data,
    guesses and unknown bytes get theirs on the first line of the run."""
    if a in res.insns:
        w = res.why.get(a, '')
        return w if w in ('entry', 'entry hint', 'code hint') \
            or w.startswith(('continues', 'guessed')) else ''
    if a in res.data:
        return res.why.get(a, '') if res.data[a][1] == a else ''
    if a in res.guess:
        return res.why.get(a, '') if res.guess[a][1] == a else ''
    prev = (a - 1) & 0xFFFF
    if prev not in res.mem or prev in res.owner or prev in res.data \
            or prev in res.guess:
        return 'nothing reaches it'
    return ''


def _note(res, a):
    """The comment for the line at A: why it is what it is, who refers
    to it, and hint comments."""
    why = _reason(res, a)
    parts = [why] if why else []
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
    """Address, bytes, flag (' ' code, g guessed code, D hinted data,
    t/w/k/f guessed text/words/keys/fill, ? unknown), label, text, and the reason: why the
    line is what it is (S4 (b)), who refers to it, and hint comments."""
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
    for t in res.tables:
        weak = ''
        if t.grade == 'weak':
            u = next((a, k) for a, k in res.undoc if a in res.guessed and not UNDOC_STRONG[k])
            weak = ' (weak: undocumented %s at %s)' % (u[1], _hex4(u[0]))
        vec = t.keyed and _vector(res, t.addr, t.count)
        out.append('guessed %s at %s: %d %s, from %s%s' % (
            'jump vector' if vec else 'keyed table' if t.keyed else 'table',
            _hex4(t.addr), t.count,
            'JP instructions' if vec else 'records' if t.keyed else 'words',
            _hex4(t.source), weak))
    for t, n, keyed, why in res.dropped:
        out.append('table guess at %s dropped: %s' % (_hex4(t), why))
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


def blocks(res):
    """The image as maximal runs of one kind: (start, end, kind, type,
    guessed, why).  kind is 'code' (type None), 'data' (a hint's type),
    'guess' (S3's type) or 'unknown'; guessed is True for code a guessed
    table led to; why is res.why for the run's first byte, or None."""
    out = []
    for start, n in _runs(res.mem):
        a, end = start, start + n
        while a < end:
            if a in res.owner:
                kind, typ, g = 'code', None, res.owner[a] in res.guessed
                b = a
                while b < end and b in res.owner \
                        and (res.owner[b] in res.guessed) == g:
                    b += 1
            elif a in res.data:
                kind, typ, g = 'data', res.data[a][0], False
                b = a
                while b < end and b in res.data and b not in res.owner \
                        and res.data[b][0] == typ:
                    b += 1
            elif a in res.guess:
                kind, typ, g = 'guess', res.guess[a][0], False
                b = a
                while b < end and b in res.guess and res.guess[b][0] == typ:
                    b += 1
            else:
                kind, typ, g = 'unknown', None, False
                b = a
                while b < end and b not in res.owner and b not in res.data \
                        and b not in res.guess:
                    b += 1
            out.append((a, b, kind, typ, g, res.why.get(a)))
            a = b
    return out


def to_json(res):
    """S4 (c): the result for tools, as a JSON text.  Every address is a
    number.  blocks tile the loaded bytes; labels map address (as a
    decimal string: JSON keys are strings) to name; xrefs are
    {from, to, kind} with from null for an entry; the rest are the
    report's lists (conflicts, indirect, computed, external, truncated,
    undoc, tables, dropped, overrides) and the summary's counts."""
    import json
    code = len(res.owner)
    gcode = sum(1 for h in res.owner.values() if h in res.guessed)
    data = sum(1 for a in res.data if a in res.mem and a not in res.owner)
    kinds = {}
    for t, _ in res.guess.values():
        kinds[t] = kinds.get(t, 0) + 1
    total = len(res.mem)
    doc = {
        'entries': list(res.entries),
        'summary': {'total': total, 'code': code, 'guessed_code': gcode,
                    'data': data,
                    'guessed_data': {t: kinds[t] for t in GUESS_TYPES if t in kinds},
                    'unknown': total - code - data - sum(kinds.values())},
        'blocks': [{'start': a, 'end': b, 'kind': k, 'type': t,
                    'guessed': g, 'why': w}
                   for a, b, k, t, g, w in blocks(res)],
        'labels': {str(a): res.names[a] for a in sorted(res.names)},
        'vars': sorted(res.vars),
        'xrefs': [{'from': s, 'to': t, 'kind': k}
                  for t in sorted(res.refs) for s, k in res.refs[t]],
        'conflicts': [{'addr': c.addr, 'inside': c.inside, 'source': c.source,
                       'kind': c.kind} for c in res.conflicts],
        'indirect': list(res.indirect),
        'computed': list(res.computed),
        'external': [{'addr': t, 'from': srcs}
                     for t, srcs in sorted(res.external.items())],
        'truncated': list(res.truncated),
        'undoc': [{'addr': a, 'kind': k, 'strong': UNDOC_STRONG[k]}
                  for a, k in res.undoc],
        'tables': [{'addr': t.addr, 'count': t.count, 'keyed': t.keyed,
                    'vector': bool(t.keyed and _vector(res, t.addr, t.count)),
                    'source': t.source, 'grade': t.grade} for t in res.tables],
        'dropped': [{'addr': t, 'count': n, 'keyed': keyed, 'why': why}
                    for t, n, keyed, why in res.dropped],
        'overrides': list(res.overrides),
        'comments': {str(a): c for a, c in sorted(res.comments.items())},
    }
    return json.dumps(doc, indent=1)


def main(argv=None):
    """Trace a Z80 program from its entry points and list what is code.

        python3 -m z80.trace PROG.cmd
        python3 -m z80.trace ROUTINE.bin --base 7F00H --entry 7F40H
        python3 -m z80.trace --hex "C3 04 70 FF C9" --base 7000H --explain
        python3 -m z80.trace PROG.cmd --hints PROG.hints --hints hints/model1.hints

    A /CMD file or a SYSTEM tape (.cas) gives its own load addresses and
    entry point; raw bytes load at --base and start there.  --entry adds
    entry points; --hints reads a hints file (both repeatable).  The bytes
    nothing reaches are guessed at (text, word tables, fill; flagged t, w,
    f) unless --no-guess; --guess-tables also follows the jump tables the
    code's constants name, what they reach flagged g.
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
    ap.add_argument('--json', action='store_true',
                    help='print the result as JSON for tools (blocks, labels, '
                         'xrefs, conflicts, the report) and nothing else')
    ap.add_argument('--no-guess', action='store_true',
                    help='leave the bytes nothing reached unknown: no text, word '
                         'table or fill guesses')
    ap.add_argument('--guess-tables', action='store_true',
                    help='follow the jump tables an address constant in the code '
                         'names (2+ words, or key byte + word records ended by a '
                         'zero key, each word an address in the image); what they '
                         'reach is code marked g, never proven; a conflict drops '
                         'the table')
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
    res = trace(segments, entries, h, guess=not a.no_guess, tables=a.guess_tables)
    if a.json:
        print(to_json(res))
        return
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
