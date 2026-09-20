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

from .table import TABLE, _hex


def db_text(raw):
    """The bytes as a DB statement the assembler takes back: DB 0EDH,00H."""
    return 'DB ' + ','.join(_hex(b, 2) for b in raw)


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
        return _trunc(data, start, n, base, ignored)

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
                    None, text=db_text(data[start:start + 1]),
                    ignored_prefixes=ignored)

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
                None, text=db_text(data[start:n]), truncated=True,
                ignored_prefixes=ignored)


def _finish(data, start, end, base, op, disp, imm, ignored, is_rel=False):
    raw = bytes(data[start:end])
    if op is None:
        return Insn(base + start, start, len(raw), raw, None,
                    text=db_text(raw), ignored_prefixes=ignored)
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
    if op.kind == 'invalid':
        return db_text(ins.raw)         # an undefined ED opcode: its two bytes
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


_SOURCE = {}


def source_text(ins):
    """Text that assembles back to exactly ins.raw at ins.addr.

    Usually that is ins.text.  It is not when the bytes are one of several
    encodings of an instruction and not the one the assembler picks
    (ED 77 is a NOP of two bytes, ED 4C a second NEG), or carry a DD/FD
    prefix that changes nothing (DD 00, DD DD 21 ..): assembled from the
    mnemonic the line would come back shorter and every address after it
    would move.  Those are written as DB with the mnemonic as the comment.
    Asked of the assembler itself, so the two cannot drift apart.
    """
    if ins.op is None or ins.invalid:
        return ins.text + (' ;truncated' if ins.truncated else '')
    rel = any(o.kind == 'rel' for o in ins.op.operands)
    key = (ins.raw, ins.addr if rel else None)
    if key not in _SOURCE:
        from .asm import assemble
        r = assemble(' ORG %d\n %s\n' % (ins.addr & 0xFFFF, ins.text))
        _SOURCE[key] = (not r.errors and len(r.segments) == 1
                        and r.segments[0][1] == ins.raw)
    return ins.text if _SOURCE[key] else '%s ;%s' % (db_text(ins.raw), ins.text)


def listing(data, base=0):
    """Human-readable listing -- used by the anchor validation.  The text
    column is source: assembled at `base` it gives `data` back."""
    lines = []
    for ins in disassemble(data, base):
        hexb = ' '.join('%02X' % b for b in ins.raw)
        lines.append('%04X  %-12s  %s' % (ins.addr, hexb, source_text(ins)))
    return '\n'.join(lines)


def main(argv=None):
    """Disassemble a file of raw Z80 bytes (goal (4) from a shell):

        python3 -m z80.disasm ROUTINE.bin --base 0x7F00
        python3 -m z80.disasm --hex "CD 7F 0A 29 C3 9A 0A" --base 32000

    `--base` is the address the bytes live at (decimal, or 0x/H hex);
    `--skip` and `--length` pick a slice of the file.  Output is the same
    listing the anchor validation reads: address, bytes, mnemonic.
    """
    import argparse
    ap = argparse.ArgumentParser(description=main.__doc__.split('\n\n')[0])
    ap.add_argument('file', nargs='?', help='raw bytes; omit with --hex')
    ap.add_argument('--hex', help='the bytes as hex digits instead of a file')
    ap.add_argument('--base', default='0', help='load address (decimal, 0x.., or ..H)')
    ap.add_argument('--skip', type=int, default=0, help='bytes of the file to skip first')
    ap.add_argument('--length', type=int, default=None, help='bytes to disassemble')
    a = ap.parse_args(argv)
    b = a.base.strip()
    base = int(b[:-1], 16) if b[-1:] in 'Hh' else int(b, 0)
    if a.hex is not None:
        data = bytes.fromhex(a.hex.replace(' ', ''))
    elif a.file:
        data = open(a.file, 'rb').read()
    else:
        ap.error('a file or --hex is required')
    data = data[a.skip:]
    if a.length is not None:
        data = data[:a.length]
    print(listing(data, base))


if __name__ == '__main__':
    main()
