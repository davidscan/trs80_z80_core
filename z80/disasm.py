"""Z80 disassembler -- a pure consumer of z80.table.TABLE.

No opcode knowledge lives here. This module only walks bytes, looks up
encodings, and resolves the operand values the encoding says are
present. If a mnemonic is wrong the table is wrong, which is exactly
the property ANCHOR 1 tests.

Linear sweep. Data bytes interleaved with code will mis-decode; the
returned Insn stream carries quality signals (invalid, truncated) so
callers can report confidence instead of pretending certainty.
"""

from dataclasses import dataclass
from typing import Optional

from .table import TABLE


def s8(b):
    return b - 256 if b > 127 else b


@dataclass
class Insn:
    addr: int                 # load address of this instruction
    offset: int               # offset within the supplied block
    length: int
    raw: bytes
    op: object                # z80.table.Op, or None when undecodable
    disp: Optional[int] = None       # (IX+d) displacement, signed
    imm: Optional[int] = None        # immediate / absolute address / port
    target: Optional[int] = None     # resolved branch or call target
    text: str = ''
    truncated: bool = False
    ignored_prefixes: int = 0

    @property
    def mnemonic(self):
        return self.op.mnemonic if self.op else 'DB'

    @property
    def invalid(self):
        return self.op is None or self.op.kind == 'invalid'

    def abs_addresses(self):
        """Absolute memory addresses this instruction touches via (nn),
        as (mode, addr, width). Empty for register-indirect access."""
        if not self.op or self.imm is None:
            return []
        out = []
        for mode, src in self.op.access:
            if src == 'aimm16':
                width = 1
                for o in self.op.operands:
                    if o.kind == 'aimm16':
                        width = o.width
                out.append((mode, self.imm & 0xFFFF, width))
        return out

    def port(self):
        """(mode, port_number_or_None). None number = port from C."""
        if not self.op:
            return None
        for mode, src in self.op.io:
            return (mode, self.imm if src == 'imm8' else None)
        return None


def decode(data, pos, base=0):
    """Decode one instruction at data[pos]. Returns an Insn."""
    start = pos
    n = len(data)
    idx_prefix = None
    ignored = 0

    # Index prefixes. A DD/FD immediately followed by another DD/FD or
    # by ED is discarded by the CPU; the last one standing takes effect.
    while pos < n and data[pos] in (0xDD, 0xFD):
        nxt = data[pos + 1] if pos + 1 < n else None
        if nxt in (0xDD, 0xFD, 0xED):
            pos += 1
            ignored += 1
            continue
        idx_prefix = data[pos]
        pos += 1
        break

    if pos >= n:
        return Insn(base + start, start, n - start, bytes(data[start:n]),
                    None, text='DB (truncated prefix)', truncated=True,
                    ignored_prefixes=ignored)

    b = data[pos]
    disp = None
    imm = None

    if b == 0xCB and idx_prefix is not None:
        # DDCB/FDCB: the displacement sits BETWEEN the CB and the opcode.
        if pos + 2 >= n:
            return _trunc(data, start, n, base, ignored)
        disp = s8(data[pos + 1])
        enc = (idx_prefix, 0xCB, data[pos + 2])
        return _finish(data, start, pos + 3, base, TABLE.get(enc),
                       disp, None, ignored)

    if b in (0xCB, 0xED):
        if pos + 1 >= n:
            return _trunc(data, start, n, base, ignored)
        enc = (b, data[pos + 1])
        cur = pos + 2
    else:
        enc = ((idx_prefix,) if idx_prefix is not None else ()) + (b,)
        cur = pos + 1

    op = TABLE.get(enc)
    if op is None:
        return Insn(base + start, start, 1, bytes(data[start:start + 1]),
                    None, text='DB %02XH' % b, ignored_prefixes=ignored)

    if any(o.kind == 'idx' for o in op.operands):
        if cur >= n:
            return _trunc(data, start, n, base, ignored)
        disp = s8(data[cur])
        cur += 1

    imm_kind = None
    for o in op.operands:
        if o.kind in ('imm8', 'port_imm', 'imm16', 'aimm16', 'rel'):
            imm_kind = o.kind
            break
    if imm_kind in ('imm8', 'port_imm', 'rel'):
        if cur >= n:
            return _trunc(data, start, n, base, ignored)
        imm = data[cur]
        cur += 1
    elif imm_kind in ('imm16', 'aimm16'):
        if cur + 1 >= n:
            return _trunc(data, start, n, base, ignored)
        imm = data[cur] | (data[cur + 1] << 8)
        cur += 2

    return _finish(data, start, cur, base, op, disp, imm, ignored,
                   imm_kind == 'rel')


def _trunc(data, start, n, base, ignored):
    return Insn(base + start, start, n - start, bytes(data[start:n]),
                None, text='DB (truncated)', truncated=True,
                ignored_prefixes=ignored)


def _finish(data, start, end, base, op, disp, imm, ignored, is_rel=False):
    raw = bytes(data[start:end])
    if op is None:
        return Insn(base + start, start, len(raw), raw, None,
                    text='DB ' + ' '.join('%02XH' % x for x in raw),
                    ignored_prefixes=ignored)
    target = None
    if is_rel and imm is not None:
        target = (base + end + s8(imm)) & 0xFFFF
    elif op.kind in ('jump', 'call'):
        for o in op.operands:
            if o.kind == 'imm16':
                target = imm
            elif o.kind == 'rst':
                target = o.value
    ins = Insn(base + start, start, len(raw), raw, op, disp, imm, target,
               '', False, ignored)
    ins.text = render(ins)
    return ins


def render(ins):
    op = ins.op
    if op is None:
        return ins.text
    parts = []
    for o in op.operands:
        parts.append(o.text(imm=ins.imm, disp=ins.disp, addr=ins.target))
    return op.mnemonic + (' ' + ','.join(parts) if parts else '')


def disassemble(data, base=0, limit=None):
    """Linear sweep over `data` loaded at `base`."""
    out = []
    pos = 0
    n = len(data)
    while pos < n:
        ins = decode(data, pos, base)
        out.append(ins)
        if ins.length <= 0:
            break
        pos += ins.length
        if limit and len(out) >= limit:
            break
    return out


def listing(data, base=0):
    """Human-readable listing -- used by the anchor validation."""
    lines = []
    for ins in disassemble(data, base):
        hexb = ' '.join('%02X' % b for b in ins.raw)
        lines.append('%04X  %-12s  %s' % (ins.addr, hexb, ins.text))
    return '\n'.join(lines)
