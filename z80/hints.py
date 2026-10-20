"""Hints for the flow tracer (z80/trace.py): what the reader knows that
control flow cannot show.

A hints file is text, one hint per line, `;` starting a comment:

    entry   8120            a routine reached only through JP (HL)
    label   0033  DSP       a name for an address, in the image or not
    var     409C  DEVFLG    a name for a RAM location outside the program:
                            it names (nn) operands only, never the
                            program's own bytes
    data    7F40-7F7F text  bytes that are data: text, words or bytes
    code    8200-8240       bytes that are code, traced from 8200 on
    inline  0028  1         a CALL or RST to 0028 is followed by 1 data byte
    inline  5300  until 00  ... by data bytes up to and including a 00
    inline  5300  until bit7    ... up to and including a byte with bit 7 set
    noreturn 0000           a CALL or RST to 0000 never comes back: an
                            unconditional one has no fall-through
    noreturn 0000 rst       ... only an RST to it (CALL 0000H is often a
                            placeholder a program patches)
    table   8000  8         8 words at 8000, each the address of code
    comment 7F12  wait for vertical blank

Addresses are hex: 7F40, 7F40H or 0x7F40, and so is a terminator byte.
Counts (inline, table) are decimal.  A range A-B includes both ends.  Free text after an entry's
address is a comment on it.  Anything the parser does not understand is
an error naming the line: a typo is never skipped.

Within one file a name names one address and an address has one name.
Across files (Hints.merge) the later file wins, and every name it takes
over is recorded in `overrides` for the report.
"""

import re
from dataclasses import dataclass, field

TYPES = ('text', 'words', 'bytes')

_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]*$')


class HintError(Exception):
    pass


@dataclass
class Hints:
    entries: list = field(default_factory=list)
    labels: dict = field(default_factory=dict)      # addr -> name
    vars: dict = field(default_factory=dict)        # addr -> name, RAM
    data: list = field(default_factory=list)        # (start, end, type)
    code: list = field(default_factory=list)        # (start, end)
    inline: dict = field(default_factory=dict)      # call target -> bytes,
    #                       or ('until', byte) / ('until', 'bit7')
    noreturn: dict = field(default_factory=dict)    # call target -> 'call'
    #                       (any CALL or RST) or 'rst' (an RST only)
    tables: list = field(default_factory=list)      # (addr, count)
    comments: dict = field(default_factory=dict)    # addr -> [text]
    overrides: list = field(default_factory=list)   # what a later file renamed
    source: str = ''

    def names(self):
        """Every name, label or var: addr -> name."""
        return {**self.labels, **self.vars}

    def merge(self, other):
        """Add OTHER's hints to these.  Where the two name things
        differently OTHER wins: an address it names loses its old name,
        and a name it uses leaves the address that had it."""
        by_name = {n.upper(): a for a, n in self.names().items()}
        for a, n in other.names().items():
            old = self.labels.get(a) or self.vars.get(a)
            if old is not None and old != n:
                self._drop(a)
                self.overrides.append('%04X: %s replaces %s (%s)'
                                      % (a, n, old, other.source or 'hints'))
            b = by_name.get(n.upper())
            if b is not None and b != a and (self.labels.get(b) or
                                             self.vars.get(b)):
                self._drop(b)
                self.overrides.append('%s: names %04X, no longer %04X (%s)'
                                      % (n, a, b, other.source or 'hints'))
        for a in other.labels:
            self.vars.pop(a, None)
        for a in other.vars:
            self.labels.pop(a, None)
        self.labels.update(other.labels)
        self.vars.update(other.vars)
        self.overrides += other.overrides
        self.entries += other.entries
        self.data += other.data
        self.code += other.code
        self.inline.update(other.inline)
        self.noreturn.update(other.noreturn)
        self.tables += other.tables
        for a, t in other.comments.items():
            self.comments.setdefault(a, []).extend(t)
        return self

    def _drop(self, a):
        self.labels.pop(a, None)
        self.vars.pop(a, None)


def _unique(new, old):
    """One name, one address."""
    seen = {n.upper(): a for a, n in old.items()}
    for a, n in new.items():
        if seen.get(n.upper(), a) != a:
            raise HintError('%s names both %04X and %04X'
                            % (n, seen[n.upper()], a))
        seen[n.upper()] = a


def addr(text):
    """7F40, 7F40H or 0x7F40 -> int; ValueError otherwise."""
    t = text.strip()
    if t[:2].lower() == '0x':
        v = int(t[2:], 16)
    elif t[-1:] in 'Hh':
        v = int(t[:-1], 16)
    else:
        v = int(t, 16)
    if not 0 <= v <= 0xFFFF:
        raise ValueError('%s is outside 0000-FFFF' % text)
    return v


def _range(text):
    a, sep, b = text.partition('-')
    lo = addr(a)
    hi = addr(b) if sep else lo
    if hi < lo:
        raise ValueError('%s ends before it starts' % text)
    return lo, hi


def _count(text):
    n = int(text, 10)
    if n < 1:
        raise ValueError('a count must be 1 or more, not %s' % text)
    return n


def _terminator(text):
    """`bit7`, or one byte in hex: the byte that ends inline data."""
    if text.lower() == 'bit7':
        return 'bit7'
    v = addr(text)
    if v > 0xFF:
        raise ValueError('a terminator is one byte or bit7, not %s' % text)
    return v


def _name(text):
    from .asm import assemble
    if not _NAME.match(text) or assemble(
            ' ORG 0\n%s EQU 0\n' % text).errors:
        raise ValueError('%s is not a label the assembler takes' % text)
    return text


def parse(text, source='hints'):
    """Read hints from TEXT; errors name SOURCE and the line."""
    h = Hints(source=source)
    for no, line in enumerate(text.splitlines(), 1):
        body = line.split(';', 1)[0].split()
        if not body:
            continue
        kw, args = body[0].lower(), body[1:]
        try:
            if kw == 'entry' and args:
                a = addr(args[0])
                h.entries.append(a)
                if args[1:]:
                    h.comments.setdefault(a, []).append(' '.join(args[1:]))
            elif kw in ('label', 'var') and len(args) == 2:
                a, n = addr(args[0]), _name(args[1])
                have = h.names()
                if have.get(a, n) != n or (a in have and (
                        a in h.vars) != (kw == 'var')):
                    raise ValueError('%04X is already named %s'
                                     % (a, have[a]))
                _unique({a: n}, have)
                (h.vars if kw == 'var' else h.labels)[a] = n
            elif kw == 'data' and len(args) == 2:
                if args[1].lower() not in TYPES:
                    raise ValueError('data type %s: use %s'
                                     % (args[1], ', '.join(TYPES)))
                lo, hi = _range(args[0])
                if args[1].lower() == 'words' and (hi - lo) % 2 == 0:
                    raise ValueError('words need an even number of bytes')
                h.data.append((lo, hi, args[1].lower()))
            elif kw == 'code' and len(args) == 1:
                h.code.append(_range(args[0]))
            elif kw == 'inline' and len(args) == 2:
                h.inline[addr(args[0])] = _count(args[1])
            elif kw == 'inline' and len(args) == 3 and args[1].lower() == 'until':
                h.inline[addr(args[0])] = ('until', _terminator(args[2]))
            elif kw == 'noreturn' and (len(args) == 1 or (
                    len(args) == 2 and args[1].lower() == 'rst')):
                h.noreturn[addr(args[0])] = 'rst' if len(args) == 2 else 'call'
            elif kw == 'table' and len(args) == 2:
                h.tables.append((addr(args[0]), _count(args[1])))
            elif kw == 'comment' and len(args) >= 2:
                h.comments.setdefault(addr(args[0]), []).append(
                    ' '.join(args[1:]))
            else:
                raise ValueError('cannot read %r' % line.strip())
        except (ValueError, HintError) as e:
            raise HintError('%s:%d: %s' % (source, no, e))
    return h


def load(path):
    with open(path, encoding='ascii', errors='strict') as f:
        return parse(f.read(), path)
