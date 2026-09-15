"""The Z80 execution core -- a pure library.

No I/O, no TRS-80 knowledge, no protocol.  A `Z80` is a register file
plus four callbacks -- `read(addr)`, `write(addr, value)`, `port_in(port)`,
`port_out(port, value)` -- and a `step()` that executes one instruction
and returns its T-state cost.  The caller owns the run loop (seam 3).

DECODE IS A CONSUMER OF THE TABLE (seam 2).  Nothing here re-derives an
encoding: `_build()` walks `z80.table.TABLE` once per instance and turns
every entry into a closure from the entry's mnemonic, operand pattern and
cycle column.  The closures are stored in seven 256-slot pages (main, CB,
ED, DD, FD, DDCB, FDCB) so dispatch is one list index per byte fetched --
the pre-decoded shape measured as the only one fast enough.  Semantics
live here; encodings live in the table.

WHAT IS MODELLED, because the pinned single-step vectors
(tests/test_cpu_vectors.py) check all of it: every documented and
undocumented instruction the table carries, all eight flag bits
including the undocumented X/Y (bits 3 and 5), MEMPTR (`wz`), the
R refresh counter, IFF1/IFF2/IM, the EI one-instruction delay (`ei`), and
the NMOS `Q` state that decides where SCF/CCF take their X/Y bits from
(fitted from the vectors 2026-09-12: X/Y = A | (F if the previous
instruction left the flags alone, else 0)).  Interrupts are not delivered
-- there is nothing to deliver them on this side of the seam -- but the
state they would consult is kept exactly.

HALT sets `halted` and advances PC past the opcode, as the vectors
expect; what a halted CPU means is the caller's decision (the coprocess
raises `ERR halt`).
"""

from .table import TABLE

S, Z, Y, H, X, P, N, C = 0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01
SZP = S | Z | P            # flags preserved by ADD HL,rp and the rotates

SZ53 = [0] * 256
SZ53P = [0] * 256
PARITY = [0] * 256
for _i in range(256):
    _even = bin(_i).count('1') % 2 == 0
    PARITY[_i] = P if _even else 0
    SZ53[_i] = (_i & (S | Y | X)) | (Z if _i == 0 else 0)
    SZ53P[_i] = SZ53[_i] | PARITY[_i]


def _s8(b):
    return b - 256 if b > 127 else b


class Z80:
    __slots__ = ('a', 'f', 'b', 'c', 'd', 'e', 'h', 'l',
                 'a2', 'f2', 'b2', 'c2', 'd2', 'e2', 'h2', 'l2',
                 'ix', 'iy', 'sp', 'pc', 'i', 'r',
                 'iff1', 'iff2', 'im', 'halted', 'wz', 'q', 'pq', 'ei',
                 'read', 'write', 'port_in', 'port_out',
                 '_main', '_cb', '_ed', '_dd', '_fd', '_ddcb', '_fdcb')

    def __init__(self, read, write, port_in=None, port_out=None):
        self.read = read
        self.write = write
        self.port_in = port_in or (lambda port: 0xFF)
        self.port_out = port_out or (lambda port, value: None)
        self.reset()
        _build(self)

    def reset(self):
        self.a = self.f = self.b = self.c = self.d = self.e = self.h = self.l = 0
        self.a2 = self.f2 = self.b2 = self.c2 = 0
        self.d2 = self.e2 = self.h2 = self.l2 = 0
        self.ix = self.iy = self.sp = self.pc = 0
        self.i = self.r = 0
        self.iff1 = self.iff2 = self.im = 0
        self.halted = False
        self.wz = self.q = self.pq = self.ei = 0

    # ---- 16-bit pair views, for callers and tests ----------------------
    @property
    def hl(self):
        return (self.h << 8) | self.l

    @hl.setter
    def hl(self, v):
        self.h = (v >> 8) & 0xFF
        self.l = v & 0xFF

    @property
    def bc(self):
        return (self.b << 8) | self.c

    @bc.setter
    def bc(self, v):
        self.b = (v >> 8) & 0xFF
        self.c = v & 0xFF

    @property
    def de(self):
        return (self.d << 8) | self.e

    @de.setter
    def de(self, v):
        self.d = (v >> 8) & 0xFF
        self.e = v & 0xFF

    @property
    def af(self):
        return (self.a << 8) | self.f

    @af.setter
    def af(self, v):
        self.a = (v >> 8) & 0xFF
        self.f = v & 0xFF

    # ---- the one entry point ------------------------------------------
    def step(self):
        """Execute one instruction; return its T-state cost."""
        s = self
        s.pq = s.q
        s.q = 0
        s.ei = 0
        op = s.read(s.pc)
        s.pc = (s.pc + 1) & 0xFFFF
        s.r = (s.r & 0x80) | ((s.r + 1) & 0x7F)
        return s._main[op]()


# ======================================================================
# The builder: table entry -> closure
# ======================================================================

def _build(s):
    rd = s.read
    wr = s.write

    # ---- register accessors -------------------------------------------
    def get8(name):
        if name == 'A': return lambda: s.a
        if name == 'B': return lambda: s.b
        if name == 'C': return lambda: s.c
        if name == 'D': return lambda: s.d
        if name == 'E': return lambda: s.e
        if name == 'H': return lambda: s.h
        if name == 'L': return lambda: s.l
        if name == 'IXH': return lambda: s.ix >> 8
        if name == 'IXL': return lambda: s.ix & 0xFF
        if name == 'IYH': return lambda: s.iy >> 8
        if name == 'IYL': return lambda: s.iy & 0xFF
        raise ValueError(name)

    def set8(name):
        if name == 'A':
            def f(v): s.a = v
        elif name == 'B':
            def f(v): s.b = v
        elif name == 'C':
            def f(v): s.c = v
        elif name == 'D':
            def f(v): s.d = v
        elif name == 'E':
            def f(v): s.e = v
        elif name == 'H':
            def f(v): s.h = v
        elif name == 'L':
            def f(v): s.l = v
        elif name == 'IXH':
            def f(v): s.ix = (s.ix & 0xFF) | (v << 8)
        elif name == 'IXL':
            def f(v): s.ix = (s.ix & 0xFF00) | v
        elif name == 'IYH':
            def f(v): s.iy = (s.iy & 0xFF) | (v << 8)
        elif name == 'IYL':
            def f(v): s.iy = (s.iy & 0xFF00) | v
        else:
            raise ValueError(name)
        return f

    def get16(name):
        if name == 'HL': return lambda: (s.h << 8) | s.l
        if name == 'BC': return lambda: (s.b << 8) | s.c
        if name == 'DE': return lambda: (s.d << 8) | s.e
        if name == 'AF': return lambda: (s.a << 8) | s.f
        if name == 'SP': return lambda: s.sp
        if name == 'IX': return lambda: s.ix
        if name == 'IY': return lambda: s.iy
        raise ValueError(name)

    def set16(name):
        if name == 'HL':
            def f(v): s.h = v >> 8; s.l = v & 0xFF
        elif name == 'BC':
            def f(v): s.b = v >> 8; s.c = v & 0xFF
        elif name == 'DE':
            def f(v): s.d = v >> 8; s.e = v & 0xFF
        elif name == 'AF':
            def f(v): s.a = v >> 8; s.f = v & 0xFF
        elif name == 'SP':
            def f(v): s.sp = v
        elif name == 'IX':
            def f(v): s.ix = v
        elif name == 'IY':
            def f(v): s.iy = v
        else:
            raise ValueError(name)
        return f

    def cond(name):
        if name == 'NZ': return lambda: not (s.f & Z)
        if name == 'Z': return lambda: s.f & Z
        if name == 'NC': return lambda: not (s.f & C)
        if name == 'C': return lambda: s.f & C
        if name == 'PO': return lambda: not (s.f & P)
        if name == 'PE': return lambda: s.f & P
        if name == 'P': return lambda: not (s.f & S)
        if name == 'M': return lambda: s.f & S
        raise ValueError(name)

    # ---- fetch helpers ------------------------------------------------
    def imm8():
        v = rd(s.pc)
        s.pc = (s.pc + 1) & 0xFFFF
        return v

    def imm16():
        lo = rd(s.pc)
        hi = rd((s.pc + 1) & 0xFFFF)
        s.pc = (s.pc + 2) & 0xFFFF
        return lo | (hi << 8)

    def rd16(a):
        return rd(a) | (rd((a + 1) & 0xFFFF) << 8)

    def wr16(a, v):
        wr(a, v & 0xFF)
        wr((a + 1) & 0xFFFF, v >> 8)

    def push(v):
        s.sp = (s.sp - 2) & 0xFFFF
        wr((s.sp + 1) & 0xFFFF, v >> 8)
        wr(s.sp, v & 0xFF)

    def pop():
        v = rd(s.sp) | (rd((s.sp + 1) & 0xFFFF) << 8)
        s.sp = (s.sp + 2) & 0xFFFF
        return v

    def idx_ea(ireg):
        """Read the displacement byte and resolve (IX+d); sets MEMPTR."""
        base = get16(ireg)

        def ea():
            d = rd(s.pc)
            s.pc = (s.pc + 1) & 0xFFFF
            a = (base() + (d - 256 if d > 127 else d)) & 0xFFFF
            s.wz = a
            return a
        return ea

    # ---- 8-bit ALU, each returns the result and sets F (and Q) --------
    def alu_add(v, cy):
        a = s.a
        r = a + v + cy
        s.q = s.f = (SZ53[r & 0xFF] | ((a ^ v ^ r) & H)
                     | (((a ^ r) & (v ^ r) & 0x80) >> 5) | (r >> 8))
        s.a = r & 0xFF

    def alu_sub(v, cy):
        a = s.a
        r = a - v - cy
        s.q = s.f = (SZ53[r & 0xFF] | N | ((a ^ v ^ r) & H)
                     | (((a ^ v) & (a ^ r) & 0x80) >> 5) | ((r >> 8) & C))
        s.a = r & 0xFF

    def alu_cp(v):
        a = s.a
        r = a - v
        s.q = s.f = ((SZ53[r & 0xFF] & (S | Z)) | (v & (Y | X)) | N
                     | ((a ^ v ^ r) & H)
                     | (((a ^ v) & (a ^ r) & 0x80) >> 5) | ((r >> 8) & C))

    def alu_and(v):
        s.a &= v
        s.q = s.f = SZ53P[s.a] | H

    def alu_xor(v):
        s.a ^= v
        s.q = s.f = SZ53P[s.a]

    def alu_or(v):
        s.a |= v
        s.q = s.f = SZ53P[s.a]

    def inc8(v):
        r = (v + 1) & 0xFF
        s.q = s.f = ((s.f & C) | SZ53[r] | (H if (r & 0x0F) == 0 else 0)
                     | (P if r == 0x80 else 0))
        return r

    def dec8(v):
        r = (v - 1) & 0xFF
        s.q = s.f = ((s.f & C) | N | SZ53[r] | (H if (r & 0x0F) == 0x0F else 0)
                     | (P if r == 0x7F else 0))
        return r

    ALU8 = {
        'ADD': lambda v: alu_add(v, 0),
        'ADC': lambda v: alu_add(v, s.f & C),
        'SUB': lambda v: alu_sub(v, 0),
        'SBC': lambda v: alu_sub(v, s.f & C),
        'AND': alu_and, 'XOR': alu_xor, 'OR': alu_or, 'CP': alu_cp,
    }

    # ---- rotates and shifts (CB page) ----------------------------------
    def rot(mnem):
        if mnem == 'RLC':
            def f(v):
                r = ((v << 1) | (v >> 7)) & 0xFF
                s.q = s.f = SZ53P[r] | (v >> 7)
                return r
        elif mnem == 'RRC':
            def f(v):
                r = (v >> 1) | ((v & 1) << 7)
                s.q = s.f = SZ53P[r] | (v & 1)
                return r
        elif mnem == 'RL':
            def f(v):
                r = ((v << 1) | (s.f & C)) & 0xFF
                s.q = s.f = SZ53P[r] | (v >> 7)
                return r
        elif mnem == 'RR':
            def f(v):
                r = (v >> 1) | ((s.f & C) << 7)
                s.q = s.f = SZ53P[r] | (v & 1)
                return r
        elif mnem == 'SLA':
            def f(v):
                r = (v << 1) & 0xFF
                s.q = s.f = SZ53P[r] | (v >> 7)
                return r
        elif mnem == 'SRA':
            def f(v):
                r = (v >> 1) | (v & 0x80)
                s.q = s.f = SZ53P[r] | (v & 1)
                return r
        elif mnem == 'SLL':
            def f(v):
                r = ((v << 1) | 1) & 0xFF
                s.q = s.f = SZ53P[r] | (v >> 7)
                return r
        elif mnem == 'SRL':
            def f(v):
                r = v >> 1
                s.q = s.f = SZ53P[r] | (v & 1)
                return r
        else:
            raise ValueError(mnem)
        return f

    def bit_flags(bit, v, xy):
        t = v & (1 << bit)
        s.q = s.f = ((s.f & C) | H | (0 if t else (Z | P))
                     | (S if (bit == 7 and t) else 0) | (xy & (Y | X)))

    # ---- 16-bit arithmetic ---------------------------------------------
    def add16(dst_get, dst_set, src_get):
        def f():
            a = dst_get()
            v = src_get()
            r = a + v
            s.wz = (a + 1) & 0xFFFF
            s.q = s.f = ((s.f & SZP) | ((r >> 8) & (Y | X))
                         | (((a ^ v ^ r) >> 8) & H) | ((r >> 16) & C))
            dst_set(r & 0xFFFF)
        return f

    def adc16(src_get):
        def f():
            a = (s.h << 8) | s.l
            v = src_get()
            r = a + v + (s.f & C)
            s.wz = (a + 1) & 0xFFFF
            s.q = s.f = (((r >> 8) & (S | Y | X)) | (Z if (r & 0xFFFF) == 0 else 0)
                         | (((a ^ v ^ r) >> 8) & H)
                         | (((a ^ r) & (v ^ r) & 0x8000) >> 13) | ((r >> 16) & C))
            s.h = (r >> 8) & 0xFF
            s.l = r & 0xFF
        return f

    def sbc16(src_get):
        def f():
            a = (s.h << 8) | s.l
            v = src_get()
            r = a - v - (s.f & C)
            s.wz = (a + 1) & 0xFFFF
            s.q = s.f = (((r >> 8) & (S | Y | X)) | (Z if (r & 0xFFFF) == 0 else 0)
                         | N | (((a ^ v ^ r) >> 8) & H)
                         | (((a ^ v) & (a ^ r) & 0x8000) >> 13) | ((r >> 16) & C))
            s.h = (r >> 8) & 0xFF
            s.l = r & 0xFF
        return f

    # ---- the per-entry builder -------------------------------------------
    def build(op, page):
        """Return the closure for table entry `op`.

        `page` is 'main', 'cb', 'ed' or 'ddcb'; the DD/FD-prefixed main
        and CB pages use the same builders because the table already
        substituted IX/IY into their operands and bumped their costs.
        DDCB closures take the resolved effective address as argument
        (the prefix handler reads the displacement before the opcode).
        """
        m = op.mnemonic
        ops = op.operands
        kinds = tuple(o.kind for o in ops)
        cyc = op.cycles[0]
        cyc2 = op.cycles[1] if len(op.cycles) > 1 else cyc

        # ---------------- DDCB page: (IX+d) with optional register copy
        if page == 'ddcb':
            reg = None
            for o in ops:
                if o.kind == 'reg':
                    reg = set8(o.value)
            if m == 'BIT':
                bit = ops[0].value

                def f(ea):
                    bit_flags(bit, rd(ea), ea >> 8)
                    return cyc
                return f
            if m in ('RES', 'SET'):
                bit = ops[0].value
                mask = 1 << bit
                if m == 'RES':
                    def f(ea):
                        v = rd(ea) & ~mask & 0xFF
                        wr(ea, v)
                        if reg: reg(v)
                        return cyc
                else:
                    def f(ea):
                        v = rd(ea) | mask
                        wr(ea, v)
                        if reg: reg(v)
                        return cyc
                return f
            r = rot(m)

            def f(ea):
                v = r(rd(ea))
                wr(ea, v)
                if reg: reg(v)
                return cyc
            return f

        # ---------------- CB page
        if page == 'cb':
            if m == 'BIT':
                bit = ops[0].value
                if ops[1].kind == 'ireg':
                    def f():
                        bit_flags(bit, rd((s.h << 8) | s.l), s.wz >> 8)
                        return cyc
                else:
                    g = get8(ops[1].value)

                    def f():
                        v = g()
                        bit_flags(bit, v, v)
                        return cyc
                return f
            if m in ('RES', 'SET'):
                bit = ops[0].value
                mask = 1 << bit
                if ops[1].kind == 'ireg':
                    if m == 'RES':
                        def f():
                            a = (s.h << 8) | s.l
                            wr(a, rd(a) & ~mask & 0xFF)
                            return cyc
                    else:
                        def f():
                            a = (s.h << 8) | s.l
                            wr(a, rd(a) | mask)
                            return cyc
                else:
                    g = get8(ops[1].value)
                    st = set8(ops[1].value)
                    if m == 'RES':
                        def f():
                            st(g() & ~mask & 0xFF)
                            return cyc
                    else:
                        def f():
                            st(g() | mask)
                            return cyc
                return f
            r = rot(m)
            if ops[0].kind == 'ireg':
                def f():
                    a = (s.h << 8) | s.l
                    wr(a, r(rd(a)))
                    return cyc
            else:
                g = get8(ops[0].value)
                st = set8(ops[0].value)

                def f():
                    st(r(g()))
                    return cyc
            return f

        # ---------------- ED page
        if page == 'ed':
            if op.kind == 'invalid':
                return lambda: cyc
            if m == 'IN':
                st = None if ops[0].value == 'F' else set8(ops[0].value)

                def f():
                    bc = (s.b << 8) | s.c
                    s.wz = (bc + 1) & 0xFFFF
                    v = s.port_in(bc)
                    s.q = s.f = (s.f & C) | SZ53P[v]
                    if st: st(v)
                    return cyc
                return f
            if m == 'OUT':
                g = (lambda: 0) if ops[1].kind == 'imm_fixed' else get8(ops[1].value)

                def f():
                    bc = (s.b << 8) | s.c
                    s.wz = (bc + 1) & 0xFFFF
                    s.port_out(bc, g())
                    return cyc
                return f
            if m == 'SBC':
                body = sbc16(get16(ops[1].value))
                return lambda: (body(), cyc)[1]
            if m == 'ADC':
                body = adc16(get16(ops[1].value))
                return lambda: (body(), cyc)[1]
            if m == 'LD':
                if ops[0].kind == 'aimm16':
                    g = get16(ops[1].value)

                    def f():
                        a = imm16()
                        wr16(a, g())
                        s.wz = (a + 1) & 0xFFFF
                        return cyc
                    return f
                if ops[1].kind == 'aimm16':
                    st = set16(ops[0].value)

                    def f():
                        a = imm16()
                        st(rd16(a))
                        s.wz = (a + 1) & 0xFFFF
                        return cyc
                    return f
                dst, src = ops[0].value, ops[1].value
                if dst == 'I':
                    def f():
                        s.i = s.a
                        return cyc
                elif dst == 'R':
                    def f():
                        s.r = s.a
                        return cyc
                elif src == 'I':
                    def f():
                        s.a = s.i
                        s.q = s.f = (s.f & C) | SZ53[s.a] | (P if s.iff2 else 0)
                        return cyc
                else:  # LD A,R
                    def f():
                        s.a = s.r
                        s.q = s.f = (s.f & C) | SZ53[s.a] | (P if s.iff2 else 0)
                        return cyc
                return f
            if m == 'NEG':
                def f():
                    v = s.a
                    s.a = 0
                    alu_sub(v, 0)
                    return cyc
                return f
            if m in ('RETN', 'RETI'):
                def f():
                    s.iff1 = s.iff2
                    s.pc = s.wz = pop()
                    return cyc
                return f
            if m == 'IM':
                mode = ops[0].value

                def f():
                    s.im = mode
                    return cyc
                return f
            if m == 'RRD':
                def f():
                    hl = (s.h << 8) | s.l
                    v = rd(hl)
                    wr(hl, ((s.a & 0x0F) << 4) | (v >> 4))
                    s.a = (s.a & 0xF0) | (v & 0x0F)
                    s.q = s.f = (s.f & C) | SZ53P[s.a]
                    s.wz = (hl + 1) & 0xFFFF
                    return cyc
                return f
            if m == 'RLD':
                def f():
                    hl = (s.h << 8) | s.l
                    v = rd(hl)
                    wr(hl, ((v << 4) & 0xF0) | (s.a & 0x0F))
                    s.a = (s.a & 0xF0) | (v >> 4)
                    s.q = s.f = (s.f & C) | SZ53P[s.a]
                    s.wz = (hl + 1) & 0xFFFF
                    return cyc
                return f
            if m == 'NOP':
                return lambda: cyc
            if op.kind == 'block':
                return block(m, cyc, cyc2)
            raise ValueError('unhandled ED entry %s' % (op,))

        # ---------------- main page (and its DD/FD shadows)
        if m == 'NOP':
            return lambda: cyc
        if m == 'HALT':
            def f():
                s.halted = True
                return cyc
            return f
        if m == 'DI':
            def f():
                s.iff1 = s.iff2 = 0
                return cyc
            return f
        if m == 'EI':
            def f():
                s.iff1 = s.iff2 = 1
                s.ei = 1
                return cyc
            return f
        if m == 'EXX':
            def f():
                s.b, s.b2 = s.b2, s.b
                s.c, s.c2 = s.c2, s.c
                s.d, s.d2 = s.d2, s.d
                s.e, s.e2 = s.e2, s.e
                s.h, s.h2 = s.h2, s.h
                s.l, s.l2 = s.l2, s.l
                return cyc
            return f
        if m == 'EX':
            if ops[0].kind == 'ireg':          # EX (SP),HL/IX/IY
                g = get16(ops[1].value)
                st = set16(ops[1].value)

                def f():
                    t = rd16(s.sp)
                    wr16(s.sp, g())
                    st(t)
                    s.wz = t
                    return cyc
                return f
            if ops[0].value == 'AF':
                def f():
                    s.a, s.a2 = s.a2, s.a
                    s.f, s.f2 = s.f2, s.f
                    return cyc
                return f

            def f():                            # EX DE,HL
                s.d, s.h = s.h, s.d
                s.e, s.l = s.l, s.e
                return cyc
            return f
        if m == 'DJNZ':
            def f():
                d = imm8()
                s.b = (s.b - 1) & 0xFF
                if s.b:
                    s.pc = s.wz = (s.pc + _s8(d)) & 0xFFFF
                    return cyc
                return cyc2
            return f
        if m == 'JR':
            if kinds == ('rel',):
                def f():
                    d = imm8()
                    s.pc = s.wz = (s.pc + _s8(d)) & 0xFFFF
                    return cyc
                return f
            cc = cond(ops[0].value)

            def f():
                d = imm8()
                if cc():
                    s.pc = s.wz = (s.pc + _s8(d)) & 0xFFFF
                    return cyc
                return cyc2
            return f
        if m == 'JP':
            if kinds == ('ireg',):
                g = get16(ops[0].value)

                def f():
                    s.pc = g()
                    return cyc
                return f
            if kinds == ('imm16',):
                def f():
                    s.pc = s.wz = imm16()
                    return cyc
                return f
            cc = cond(ops[0].value)

            def f():
                a = imm16()
                s.wz = a
                if cc():
                    s.pc = a
                return cyc
            return f
        if m == 'CALL':
            if kinds == ('imm16',):
                def f():
                    a = imm16()
                    push(s.pc)
                    s.pc = s.wz = a
                    return cyc
                return f
            cc = cond(ops[0].value)

            def f():
                a = imm16()
                s.wz = a
                if cc():
                    push(s.pc)
                    s.pc = a
                    return cyc
                return cyc2
            return f
        if m == 'RET':
            if not ops:
                def f():
                    s.pc = s.wz = pop()
                    return cyc
                return f
            cc = cond(ops[0].value)

            def f():
                if cc():
                    s.pc = s.wz = pop()
                    return cyc
                return cyc2
            return f
        if m == 'RST':
            target = ops[0].value

            def f():
                push(s.pc)
                s.pc = s.wz = target
                return cyc
            return f
        if m == 'PUSH':
            g = get16(ops[0].value)

            def f():
                push(g())
                return cyc
            return f
        if m == 'POP':
            st = set16(ops[0].value)

            def f():
                st(pop())
                return cyc
            return f
        if m == 'IN':                            # IN A,(n)
            def f():
                port = (s.a << 8) | imm8()
                s.wz = (port + 1) & 0xFFFF
                s.a = s.port_in(port)
                return cyc
            return f
        if m == 'OUT':                           # OUT (n),A
            def f():
                n = imm8()
                s.port_out((s.a << 8) | n, s.a)
                s.wz = (s.a << 8) | ((n + 1) & 0xFF)
                return cyc
            return f
        if m == 'RLCA':
            def f():
                a = s.a = ((s.a << 1) | (s.a >> 7)) & 0xFF
                s.q = s.f = (s.f & SZP) | (a & (Y | X)) | (a & C)
                return cyc
            return f
        if m == 'RRCA':
            def f():
                c = s.a & 1
                a = s.a = (s.a >> 1) | (c << 7)
                s.q = s.f = (s.f & SZP) | (a & (Y | X)) | c
                return cyc
            return f
        if m == 'RLA':
            def f():
                c = s.a >> 7
                a = s.a = ((s.a << 1) | (s.f & C)) & 0xFF
                s.q = s.f = (s.f & SZP) | (a & (Y | X)) | c
                return cyc
            return f
        if m == 'RRA':
            def f():
                c = s.a & 1
                a = s.a = (s.a >> 1) | ((s.f & C) << 7)
                s.q = s.f = (s.f & SZP) | (a & (Y | X)) | c
                return cyc
            return f
        if m == 'DAA':
            def f():
                a = s.a
                fl = s.f
                lo = a & 0x0F
                adj = 0x06 if (fl & H or lo > 9) else 0
                cy = fl & C
                if cy or a > 0x99:
                    adj |= 0x60
                    cy = C
                if fl & N:
                    r = (a - adj) & 0xFF
                    hf = H if (fl & H and lo < 6) else 0
                else:
                    r = (a + adj) & 0xFF
                    hf = H if lo > 9 else 0
                s.a = r
                s.q = s.f = SZ53P[r] | cy | (fl & N) | hf
                return cyc
            return f
        if m == 'CPL':
            def f():
                s.a ^= 0xFF
                s.q = s.f = (s.f & (SZP | C)) | H | N | (s.a & (Y | X))
                return cyc
            return f
        if m == 'SCF':
            def f():
                fl = s.f
                s.q = s.f = (fl & SZP) | ((s.a | (0 if s.pq else fl)) & (Y | X)) | C
                return cyc
            return f
        if m == 'CCF':
            def f():
                fl = s.f
                s.q = s.f = ((fl & SZP) | ((fl & C) << 4)
                             | ((s.a | (0 if s.pq else fl)) & (Y | X)) | ((fl & C) ^ C))
                return cyc
            return f
        if m == 'INC' or m == 'DEC':
            o = ops[0]
            if o.kind == 'reg' and len(o.value) == 2:       # 16-bit
                g = get16(o.value)
                st = set16(o.value)
                delta = 1 if m == 'INC' else -1

                def f():
                    st((g() + delta) & 0xFFFF)
                    return cyc
                return f
            fn = inc8 if m == 'INC' else dec8
            if o.kind == 'ireg':
                def f():
                    a = (s.h << 8) | s.l
                    wr(a, fn(rd(a)))
                    return cyc
                return f
            if o.kind == 'idx':
                ea = idx_ea(o.value)

                def f():
                    a = ea()
                    wr(a, fn(rd(a)))
                    return cyc
                return f
            g = get8(o.value)
            st = set8(o.value)

            def f():
                st(fn(g()))
                return cyc
            return f
        if m in ALU8:
            # ADD/ADC/SBC carry an explicit A destination; the others do not
            src = ops[-1]
            if m == 'ADD' and ops[0].kind == 'reg' and len(ops[0].value) == 2:
                body = add16(get16(ops[0].value), set16(ops[0].value),
                             get16(ops[1].value))
                return lambda: (body(), cyc)[1]
            fn = ALU8[m]
            if src.kind == 'imm8':
                def f():
                    fn(imm8())
                    return cyc
                return f
            if src.kind == 'ireg':
                def f():
                    fn(rd((s.h << 8) | s.l))
                    return cyc
                return f
            if src.kind == 'idx':
                ea = idx_ea(src.value)

                def f():
                    fn(rd(ea()))
                    return cyc
                return f
            g = get8(src.value)

            def f():
                fn(g())
                return cyc
            return f
        if m == 'LD':
            dst, src = ops
            # 16-bit forms
            if dst.kind == 'reg' and len(dst.value) == 2:
                st = set16(dst.value)
                if src.kind == 'imm16':
                    def f():
                        st(imm16())
                        return cyc
                    return f
                if src.kind == 'aimm16':
                    def f():
                        a = imm16()
                        st(rd16(a))
                        s.wz = (a + 1) & 0xFFFF
                        return cyc
                    return f
                g = get16(src.value)                    # LD SP,HL

                def f():
                    st(g())
                    return cyc
                return f
            if dst.kind == 'aimm16':
                if dst.width == 2:
                    g = get16(src.value)

                    def f():
                        a = imm16()
                        wr16(a, g())
                        s.wz = (a + 1) & 0xFFFF
                        return cyc
                    return f

                def f():                                # LD (nn),A
                    a = imm16()
                    wr(a, s.a)
                    s.wz = (s.a << 8) | ((a + 1) & 0xFF)
                    return cyc
                return f
            if src.kind == 'aimm16':                    # LD A,(nn)
                def f():
                    a = imm16()
                    s.a = rd(a)
                    s.wz = (a + 1) & 0xFFFF
                    return cyc
                return f
            if dst.kind == 'ireg':
                if dst.value == 'HL':
                    if src.kind == 'imm8':
                        def f():
                            wr((s.h << 8) | s.l, imm8())
                            return cyc
                        return f
                    g = get8(src.value)

                    def f():
                        wr((s.h << 8) | s.l, g())
                        return cyc
                    return f
                g16 = get16(dst.value)                  # LD (BC),A / LD (DE),A

                def f():
                    a = g16()
                    wr(a, s.a)
                    s.wz = (s.a << 8) | ((a + 1) & 0xFF)
                    return cyc
                return f
            if src.kind == 'ireg':
                if src.value == 'HL':
                    st = set8(dst.value)

                    def f():
                        st(rd((s.h << 8) | s.l))
                        return cyc
                    return f
                g16 = get16(src.value)                  # LD A,(BC) / LD A,(DE)

                def f():
                    a = g16()
                    s.a = rd(a)
                    s.wz = (a + 1) & 0xFFFF
                    return cyc
                return f
            if dst.kind == 'idx':
                ea = idx_ea(dst.value)
                if src.kind == 'imm8':
                    def f():
                        a = ea()
                        wr(a, imm8())
                        return cyc
                    return f
                g = get8(src.value)

                def f():
                    wr(ea(), g())
                    return cyc
                return f
            if src.kind == 'idx':
                ea = idx_ea(src.value)
                st = set8(dst.value)

                def f():
                    st(rd(ea()))
                    return cyc
                return f
            st = set8(dst.value)
            if src.kind == 'imm8':
                def f():
                    st(imm8())
                    return cyc
                return f
            g = get8(src.value)

            def f():
                st(g())
                return cyc
            return f
        raise ValueError('unhandled entry %s' % (op,))

    # ---- block instructions --------------------------------------------
    def block(m, cyc, cyc2):
        base = m[:3] if m.endswith('R') and m not in ('LDD', 'CPD') else m
        if m in ('LDIR', 'LDDR', 'CPIR', 'CPDR', 'INIR', 'INDR', 'OTIR', 'OTDR'):
            base = {'LDIR': 'LDI', 'LDDR': 'LDD', 'CPIR': 'CPI', 'CPDR': 'CPD',
                    'INIR': 'INI', 'INDR': 'IND', 'OTIR': 'OUTI', 'OTDR': 'OUTD'}[m]
            repeat = True
        else:
            repeat = False
        step = -1 if base in ('LDD', 'CPD', 'IND', 'OUTD') else 1

        if base in ('LDI', 'LDD'):
            def one():
                hl = (s.h << 8) | s.l
                de = (s.d << 8) | s.e
                v = rd(hl)
                wr(de, v)
                s.h, s.l = ((hl + step) >> 8) & 0xFF, (hl + step) & 0xFF
                s.d, s.e = ((de + step) >> 8) & 0xFF, (de + step) & 0xFF
                bc = ((s.b << 8) | s.c) - 1 & 0xFFFF
                s.b, s.c = bc >> 8, bc & 0xFF
                n = v + s.a
                s.q = s.f = ((s.f & (S | Z | C)) | (P if bc else 0)
                             | (n & X) | ((n & 0x02) << 4))
                return bc != 0
        elif base in ('CPI', 'CPD'):
            def one():
                hl = (s.h << 8) | s.l
                v = rd(hl)
                a = s.a
                r = (a - v) & 0xFF
                hf = (a ^ v ^ r) & H
                n = r - (1 if hf else 0)
                s.h, s.l = ((hl + step) >> 8) & 0xFF, (hl + step) & 0xFF
                bc = ((s.b << 8) | s.c) - 1 & 0xFFFF
                s.b, s.c = bc >> 8, bc & 0xFF
                s.wz = (s.wz + step) & 0xFFFF
                s.q = s.f = ((s.f & C) | N | (SZ53[r] & (S | Z)) | hf
                             | (P if bc else 0) | (n & X) | ((n & 0x02) << 4))
                return bc != 0 and not (s.f & Z)
        elif base in ('INI', 'IND'):
            def one():
                bc = (s.b << 8) | s.c
                s.wz = (bc + step) & 0xFFFF
                v = s.port_in(bc)
                hl = (s.h << 8) | s.l
                wr(hl, v)
                s.h, s.l = ((hl + step) >> 8) & 0xFF, (hl + step) & 0xFF
                b = s.b = (s.b - 1) & 0xFF
                k = v + ((s.c + step) & 0xFF)
                s.q = s.f = (SZ53[b] | (N if v & 0x80 else 0)
                             | ((H | C) if k > 0xFF else 0)
                             | PARITY[(k & 7) ^ b])
                return b != 0
        else:  # OUTI / OUTD
            def one():
                hl = (s.h << 8) | s.l
                v = rd(hl)
                b = s.b = (s.b - 1) & 0xFF
                bc = (b << 8) | s.c
                s.port_out(bc, v)
                s.h, s.l = ((hl + step) >> 8) & 0xFF, (hl + step) & 0xFF
                s.wz = (bc + step) & 0xFFFF
                k = v + s.l
                s.q = s.f = (SZ53[b] | (N if v & 0x80 else 0)
                             | ((H | C) if k > 0xFF else 0)
                             | PARITY[(k & 7) ^ b])
                return b != 0

        if not repeat:
            def f():
                one()
                return cyc
            return f

        io = base in ('INI', 'IND', 'OUTI', 'OUTD')

        def f():
            if one():
                s.pc = (s.pc - 2) & 0xFFFF
                s.wz = (s.pc + 1) & 0xFFFF
                fl = s.f
                fl = (fl & ~(Y | X)) | ((s.pc >> 8) & (Y | X))
                if io:
                    # the repeat's extra M-cycle disturbs H and P/V (NMOS,
                    # as the pinned vectors record it)
                    b = s.b
                    if fl & C:
                        if fl & N:
                            fl ^= PARITY[(b - 1) & 7] ^ P
                            fl = (fl & ~H) | (H if (b & 0x0F) == 0 else 0)
                        else:
                            fl ^= PARITY[(b + 1) & 7] ^ P
                            fl = (fl & ~H) | (H if (b & 0x0F) == 0x0F else 0)
                    else:
                        fl ^= PARITY[b & 7] ^ P
                s.q = s.f = fl
                return cyc
            return cyc2
        return f

    # ---- assemble the seven pages ------------------------------------------
    main = [None] * 256
    cb = [None] * 256
    ed = [None] * 256
    dd = [None] * 256
    fd = [None] * 256
    ddcb = [None] * 256
    fdcb = [None] * 256
    for enc, op in TABLE.items():
        if len(enc) == 1:
            main[enc[0]] = build(op, 'main')
        elif enc[0] == 0xCB:
            cb[enc[1]] = build(op, 'cb')
        elif enc[0] == 0xED:
            ed[enc[1]] = build(op, 'ed')
        elif len(enc) == 3:
            (ddcb if enc[0] == 0xDD else fdcb)[enc[2]] = build(op, 'ddcb')
        else:
            (dd if enc[0] == 0xDD else fd)[enc[1]] = build(op, 'main')

    # prefix handlers: the second opcode byte is an M1 fetch (R += 1)
    def fetch2(page, clears_q):
        # A DD/FD prefix is an instruction of its own to the flag logic:
        # it leaves Q clear, so a prefixed SCF/CCF always takes X/Y from
        # A | F (the vectors' 'dd 37'/'fd 3f' cases pin this).
        if clears_q:
            def f():
                op = rd(s.pc)
                s.pc = (s.pc + 1) & 0xFFFF
                s.r = (s.r & 0x80) | ((s.r + 1) & 0x7F)
                s.pq = 0
                return page[op]()
        else:
            def f():
                op = rd(s.pc)
                s.pc = (s.pc + 1) & 0xFFFF
                s.r = (s.r & 0x80) | ((s.r + 1) & 0x7F)
                return page[op]()
        return f
    main[0xCB] = fetch2(cb, False)
    main[0xED] = fetch2(ed, False)
    main[0xDD] = fetch2(dd, True)
    main[0xFD] = fetch2(fd, True)

    def idx_cb(page, base):
        # DD CB d op: displacement then opcode, neither an M1 fetch
        def f():
            d = rd(s.pc)
            op = rd((s.pc + 1) & 0xFFFF)
            s.pc = (s.pc + 2) & 0xFFFF
            ea = s.wz = (base() + (d - 256 if d > 127 else d)) & 0xFFFF
            return page[op](ea)
        return f
    dd[0xCB] = idx_cb(ddcb, get16('IX'))
    fd[0xCB] = idx_cb(fdcb, get16('IY'))

    def reprefix():
        # DD DD / DD FD / DD ED / FD ...: the first prefix is a 4-T no-op
        # and the byte after it starts the next instruction.
        s.pc = (s.pc - 1) & 0xFFFF
        s.r = (s.r & 0x80) | ((s.r - 1) & 0x7F)
        return 4
    for page in (dd, fd):
        page[0xDD] = page[0xFD] = page[0xED] = reprefix

    for name, page in (('main', main), ('cb', cb), ('ed', ed), ('dd', dd),
                       ('fd', fd), ('ddcb', ddcb), ('fdcb', fdcb)):
        missing = [i for i, x in enumerate(page) if x is None]
        if missing:
            raise RuntimeError('page %s has no closure for %s'
                               % (name, ['%02X' % i for i in missing]))

    s._main, s._cb, s._ed, s._dd, s._fd, s._ddcb, s._fdcb = (
        main, cb, ed, dd, fd, ddcb, fdcb)
