"""Hints for the flow tracer (z80/trace.py): what the reader knows that
control flow cannot show.

A hints file is text, one hint per line, `;` starting a comment:

    entry   8120            a routine reached only through JP (HL)
    label   0033  DSP       a name for an address, in the image or not
    data    7F40-7F7F text  bytes that are data: text, words or bytes
    code    8200-8240       bytes that are code, traced from 8200 on
    inline  0028  1         a CALL or RST to 0028 is followed by 1 data byte
    table   8000  8         8 words at 8000, each the address of code
    comment 7F12  wait for vertical blank

Addresses are hex: 7F40, 7F40H or 0x7F40.  Counts (inline, table) are
decimal.  A range A-B includes both ends.  Free text after an entry's
address is a comment on it.  Anything the parser does not understand is
an error naming the line: a typo is never skipped.
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
    data: list = field(default_factory=list)        # (start, end, type)
    code: list = field(default_factory=list)        # (start, end)
    inline: dict = field(default_factory=dict)      # call target -> bytes
    tables: list = field(default_factory=list)      # (addr, count)
    comments: dict = field(default_factory=dict)    # addr -> [text]

    def merge(self, other):
        """Add OTHER's hints to these; a name given twice must agree."""
        for a, n in other.labels.items():
            if self.labels.get(a, n) != n:
                raise HintError('%04X is named both %s and %s'
                                % (a, self.labels[a], n))
        _unique(other.labels, self.labels)
        self.entries += other.entries
        self.labels.update(other.labels)
        self.data += other.data
        self.code += other.code
        self.inline.update(other.inline)
        self.tables += other.tables
        for a, t in other.comments.items():
            self.comments.setdefault(a, []).extend(t)
        return self


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


def _name(text):
    from .asm import assemble
    if not _NAME.match(text) or assemble(
            ' ORG 0\n%s EQU 0\n' % text).errors:
        raise ValueError('%s is not a label the assembler takes' % text)
    return text


def parse(text, source='hints'):
    """Read hints from TEXT; errors name SOURCE and the line."""
    h = Hints()
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
            elif kw == 'label' and len(args) == 2:
                a, n = addr(args[0]), _name(args[1])
                if h.labels.get(a, n) != n:
                    raise ValueError('%04X is already named %s'
                                     % (a, h.labels[a]))
                _unique({a: n}, h.labels)
                h.labels[a] = n
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
