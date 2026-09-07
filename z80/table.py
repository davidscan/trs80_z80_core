"""THE declarative Z80 opcode table -- single source of truth.

Three consumers, per DESIGN.md "Architecture: the reusable seams":
  1. the Phase A disassembler/classifier   (encoding -> mnemonic)
  2. the future core's decoder             (encoding -> execution)
  3. a future assembler                    (mnemonic -> encoding)

The table is DATA, not per-opcode decode logic. Its source form is the
documented regular structure of the Z80 instruction space -- the index
tables R/RP/RP2/CC/ALU/ROT/BLI addressed by the standard x/y/z/p/q
decomposition of the opcode byte -- plus explicit rows for the
irregulars. `build_table()` expands that TOTALLY at import into a flat
dict keyed by encoding, so consumers see one uniform table and never
re-derive an encoding by hand.

Every entry carries: mnemonic, operand pattern, encoding, length,
cycle cost, flag effects, and the memory/port access it performs.

CYCLE COSTS ARE CARRIED BUT LARGELY UNVALIDATED. Nothing in the Phase
A gate measurement depends on them; they exist because the ruling
requires the column and because omitting them would design out the
offline sound-synthesis option (DESIGN.md non-goals). They are
validated when the core is built against the single-step vectors.
ONE PARTIAL EXTERNAL CHECK EXISTS (2026-09-07, Z80_FINDINGS FINDING
21): the Nano Systems reference card states that every index-half
instruction costs its H/L-operand equivalent plus 4 T-states, and all
92 of them satisfy that (tests/test_table.py). That is a rule holding
over 92 entries, not a per-opcode table; the other 1688 are still
unchecked against anything outside this file.

The `undoc` flag means "not in Zilog's published instruction set", and
it is load-bearing: the inverse (assembler) index prefers a documented
encoding over an undocumented one carrying the same signature.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional


# --------------------------------------------------------------------
# Operand model
# --------------------------------------------------------------------
# kind:
#   'reg'       8- or 16-bit register by name           value=name
#   'ireg'      register-indirect memory  (HL) (BC) (DE) value=regname
#   'idx'       indexed memory (IX+d) / (IY+d)          value='IX'|'IY'
#   'imm8'      immediate byte n                        value=None
#   'imm16'     immediate word nn                       value=None
#   'aimm16'    ABSOLUTE memory at (nn)                 value=None
#   'port_imm'  port (n)                                value=None
#   'port_c'    port (C)                                value=None
#   'rel'       relative displacement d (PC-relative)   value=None
#   'cond'      branch condition                        value='NZ'...
#   'bit'       bit number 0-7                          value=int
#   'rst'       RST target address                      value=int
#   'imm_fixed' literal operand baked into the opcode   value=int/str
#               (IM 0/1/2, OUT (C),0, RST n handled by 'rst')

@dataclass(frozen=True)
class Operand:
    kind: str
    value: object = None
    # bytes touched when this operand names memory (1 or 2), else 0
    width: int = 0

    def text(self, imm=None, disp=None, addr=None):
        """Render this operand. imm/disp/addr supplied by the decoder."""
        k = self.kind
        if k == 'reg':
            return self.value
        if k == 'ireg':
            return '(%s)' % self.value
        if k == 'idx':
            d = 0 if disp is None else disp
            sign = '+' if d >= 0 else '-'
            return '(%s%s%02XH)' % (self.value, sign, abs(d))
        if k == 'imm8':
            return '%02XH' % (imm & 0xFF) if imm is not None else 'n'
        if k == 'imm16':
            return '%04XH' % (imm & 0xFFFF) if imm is not None else 'nn'
        if k == 'aimm16':
            return '(%04XH)' % (imm & 0xFFFF) if imm is not None else '(nn)'
        if k == 'port_imm':
            return '(%02XH)' % (imm & 0xFF) if imm is not None else '(n)'
        if k == 'port_c':
            return '(C)'
        if k == 'rel':
            return '%04XH' % (addr & 0xFFFF) if addr is not None else 'd'
        if k == 'cond':
            return self.value
        if k == 'bit':
            return str(self.value)
        if k == 'rst':
            return '%02XH' % self.value
        if k == 'imm_fixed':
            return str(self.value)
        raise AssertionError('bad operand kind %r' % k)


# Shorthand constructors
def REG(n):    return Operand('reg', n)
def IREG(n, w=1): return Operand('ireg', n, w)
def IDX(n, w=1):  return Operand('idx', n, w)
IMM8   = Operand('imm8')
IMM16  = Operand('imm16')
def AIMM16(w=1):  return Operand('aimm16', None, w)
PORTN  = Operand('port_imm')
PORTC  = Operand('port_c')
REL    = Operand('rel')
def COND(c):  return Operand('cond', c)
def BIT(b):   return Operand('bit', b)
def RST(a):   return Operand('rst', a)
def FIXED(v): return Operand('imm_fixed', v)


# --------------------------------------------------------------------
# Instruction entry
# --------------------------------------------------------------------
# flags: 6 chars, in order S Z H P/V N C
#   '-' unaffected   '*' set from result   '0' reset   '1' set
#   '?' undefined
#
# access: tuple of (mode, source) pairs describing memory touched.
#   mode   'r' | 'w'
#   source 'aimm16' | 'hl' | 'bc' | 'de' | 'sp' | 'idx' | 'pc'
#
# io: tuple of (mode, source) for port access. mode 'in'|'out',
#   source 'imm8' | 'c'

@dataclass(frozen=True)
class Op:
    prefix: tuple
    opcode: int
    mnemonic: str
    operands: tuple = ()
    length: int = 1
    cycles: tuple = (4,)
    flags: str = '------'
    kind: str = 'misc'
    access: tuple = ()
    io: tuple = ()
    undoc: bool = False

    @property
    def encoding(self):
        return self.prefix + (self.opcode,)

    def signature(self):
        """Assembler-facing key: mnemonic + operand pattern."""
        parts = []
        for o in self.operands:
            if o.kind in ('reg', 'cond'):
                parts.append(o.value)
            elif o.kind == 'ireg':
                parts.append('(%s)' % o.value)
            elif o.kind == 'idx':
                parts.append('(%s+d)' % o.value)
            elif o.kind == 'bit':
                parts.append(str(o.value))
            elif o.kind == 'rst':
                parts.append('%02XH' % o.value)
            elif o.kind == 'imm_fixed':
                parts.append(str(o.value))
            elif o.kind == 'imm8':
                parts.append('n')
            elif o.kind == 'imm16':
                parts.append('nn')
            elif o.kind == 'aimm16':
                parts.append('(nn)')
            elif o.kind == 'port_imm':
                parts.append('(n)')
            elif o.kind == 'port_c':
                parts.append('(C)')
            elif o.kind == 'rel':
                parts.append('d')
        return (self.mnemonic, tuple(parts))


# --------------------------------------------------------------------
# The declarative index tables (the documented ISA structure)
# --------------------------------------------------------------------

R    = ['B', 'C', 'D', 'E', 'H', 'L', '(HL)', 'A']
RP   = ['BC', 'DE', 'HL', 'SP']
RP2  = ['BC', 'DE', 'HL', 'AF']
CC   = ['NZ', 'Z', 'NC', 'C', 'PO', 'PE', 'P', 'M']
ALU  = ['ADD', 'ADC', 'SUB', 'SBC', 'AND', 'XOR', 'OR', 'CP']
# ALU ops that take an explicit A destination operand
ALU_TAKES_A = {'ADD', 'ADC', 'SBC'}
ROT  = ['RLC', 'RRC', 'RL', 'RR', 'SLA', 'SRA', 'SLL', 'SRL']
IM_T = [0, 0, 1, 2, 0, 0, 1, 2]
BLI  = [['LDI', 'CPI', 'INI', 'OUTI'],
        ['LDD', 'CPD', 'IND', 'OUTD'],
        ['LDIR', 'CPIR', 'INIR', 'OTIR'],
        ['LDDR', 'CPDR', 'INDR', 'OTDR']]

# Flag effects for the ALU group, indexed as ALU
ALU_FLAGS = {
    'ADD': '***V0*', 'ADC': '***V0*', 'SUB': '***V1*', 'SBC': '***V1*',
    'AND': '**1P00', 'XOR': '**0P00', 'OR': '**0P00', 'CP': '***V1*',
}
# Accumulator-rotate / misc group (x=0, z=7)
X0Z7 = [
    ('RLCA', '--0-0*'), ('RRCA', '--0-0*'),
    ('RLA',  '--0-0*'), ('RRA',  '--0-0*'),
    ('DAA',  '**-P-*'), ('CPL',  '--1-1-'),
    ('SCF',  '--0-01'), ('CCF',  '--?-0*'),
]


def _reg_operand(name, idx_reg=None, disp_used=None):
    """Map an R[] entry to an Operand, honoring DD/FD substitution."""
    if name == '(HL)':
        if idx_reg:
            return IDX(idx_reg), True
        return IREG('HL'), False
    if idx_reg and name in ('H', 'L'):
        return REG(idx_reg + name), False
    return REG(name), False


def _rp_sub(name, idx_reg):
    return idx_reg if (idx_reg and name == 'HL') else name


# --------------------------------------------------------------------
# Page builders
# --------------------------------------------------------------------

def _build_main(prefix=(), idx_reg=None):
    """Main page (and its DD/FD-shadowed variants)."""
    ops = {}
    pfx_extra = 1 if idx_reg else 0        # extra prefix byte in length
    bump = 4 if idx_reg else 0             # DD/FD prefix cycle surcharge

    def add(op, mnem, operands, length, cycles, flags='------',
            kind='misc', access=(), io=(), undoc=False):
        ops[prefix + (op,)] = Op(prefix, op, mnem, tuple(operands),
                                 length + pfx_extra, tuple(cycles), flags,
                                 kind, tuple(access), tuple(io), undoc)

    for op in range(256):
        x, y, z = op >> 6, (op >> 3) & 7, op & 7
        p, q = y >> 1, y & 1

        if x == 0:
            if z == 0:
                if y == 0:
                    add(op, 'NOP', [], 1, [4 + bump], kind='nop')
                elif y == 1:
                    add(op, 'EX', [REG('AF'), REG("AF'")], 1, [4 + bump],
                        kind='ex')
                elif y == 2:
                    add(op, 'DJNZ', [REL], 2, [13 + bump, 8 + bump],
                        kind='jump')
                elif y == 3:
                    add(op, 'JR', [REL], 2, [12 + bump], kind='jump')
                else:
                    add(op, 'JR', [COND(CC[y - 4]), REL], 2,
                        [12 + bump, 7 + bump], kind='jump')
            elif z == 1:
                rp = _rp_sub(RP[p], idx_reg)
                if q == 0:
                    add(op, 'LD', [REG(rp), IMM16], 3,
                        [14 if idx_reg else 10], kind='ld')
                else:
                    dst = idx_reg or 'HL'
                    src = _rp_sub(RP[p], idx_reg)
                    add(op, 'ADD', [REG(dst), REG(src)], 1,
                        [15 if idx_reg else 11], '--*-0*', kind='alu')
            elif z == 2:
                if q == 0:
                    if p == 0:
                        add(op, 'LD', [IREG('BC'), REG('A')], 1, [7 + bump],
                            kind='ld', access=[('w', 'bc')])
                    elif p == 1:
                        add(op, 'LD', [IREG('DE'), REG('A')], 1, [7 + bump],
                            kind='ld', access=[('w', 'de')])
                    elif p == 2:
                        add(op, 'LD', [AIMM16(2), REG(idx_reg or 'HL')], 3,
                            [20 if idx_reg else 16], kind='ld',
                            access=[('w', 'aimm16')])
                    else:
                        add(op, 'LD', [AIMM16(1), REG('A')], 3,
                            [13 + bump], kind='ld', access=[('w', 'aimm16')])
                else:
                    if p == 0:
                        add(op, 'LD', [REG('A'), IREG('BC')], 1, [7 + bump],
                            kind='ld', access=[('r', 'bc')])
                    elif p == 1:
                        add(op, 'LD', [REG('A'), IREG('DE')], 1, [7 + bump],
                            kind='ld', access=[('r', 'de')])
                    elif p == 2:
                        add(op, 'LD', [REG(idx_reg or 'HL'), AIMM16(2)], 3,
                            [20 if idx_reg else 16], kind='ld',
                            access=[('r', 'aimm16')])
                    else:
                        add(op, 'LD', [REG('A'), AIMM16(1)], 3,
                            [13 + bump], kind='ld', access=[('r', 'aimm16')])
            elif z == 3:
                rp = _rp_sub(RP[p], idx_reg)
                add(op, 'INC' if q == 0 else 'DEC', [REG(rp)], 1,
                    [10 if idx_reg else 6], kind='alu')
            elif z in (4, 5):
                mnem = 'INC' if z == 4 else 'DEC'
                fl = '***V0-' if z == 4 else '***V1-'
                o, is_idx = _reg_operand(R[y], idx_reg)
                if is_idx:
                    add(op, mnem, [o], 2, [23], fl, kind='alu',
                        access=[('r', 'idx'), ('w', 'idx')])
                elif R[y] == '(HL)':
                    add(op, mnem, [o], 1, [11], fl, kind='alu',
                        access=[('r', 'hl'), ('w', 'hl')])
                else:
                    add(op, mnem, [o], 1, [4 + bump], fl, kind='alu',
                        undoc=bool(idx_reg and R[y] in ('H', 'L')))
            elif z == 6:
                o, is_idx = _reg_operand(R[y], idx_reg)
                if is_idx:
                    add(op, 'LD', [o, IMM8], 3, [19], kind='ld',
                        access=[('w', 'idx')])
                elif R[y] == '(HL)':
                    add(op, 'LD', [o, IMM8], 2, [10], kind='ld',
                        access=[('w', 'hl')])
                else:
                    add(op, 'LD', [o, IMM8], 2, [7 + bump], kind='ld',
                        undoc=bool(idx_reg and R[y] in ('H', 'L')))
            else:  # z == 7
                mnem, fl = X0Z7[y]
                add(op, mnem, [], 1, [4 + bump], fl, kind='alu')

        elif x == 1:
            if z == 6 and y == 6:
                add(op, 'HALT', [], 1, [4 + bump], kind='ctl')
            else:
                # DD/FD: an (IX+d) operand on EITHER side suppresses the
                # H/L -> IXH/IXL substitution on the other side.
                src_is_hl = (R[z] == '(HL)')
                dst_is_hl = (R[y] == '(HL)')
                if src_is_hl or dst_is_hl:
                    dst, dst_idx = _reg_operand(R[y], idx_reg if dst_is_hl
                                                else None)
                    src, src_idx = _reg_operand(R[z], idx_reg if src_is_hl
                                                else None)
                else:
                    dst, dst_idx = _reg_operand(R[y], idx_reg)
                    src, src_idx = _reg_operand(R[z], idx_reg)
                acc = []
                if dst_idx:
                    acc.append(('w', 'idx'))
                elif dst_is_hl:
                    acc.append(('w', 'hl'))
                if src_idx:
                    acc.append(('r', 'idx'))
                elif src_is_hl:
                    acc.append(('r', 'hl'))
                if dst_idx or src_idx:
                    ln, cy = 2, 19
                elif dst_is_hl or src_is_hl:
                    ln, cy = 1, 7
                else:
                    ln, cy = 1, 4 + bump
                add(op, 'LD', [dst, src], ln, [cy], kind='ld', access=acc,
                    undoc=bool(idx_reg and not (dst_idx or src_idx)
                               and (R[y] in ('H', 'L') or R[z] in ('H', 'L'))))

        elif x == 2:
            mnem = ALU[y]
            o, is_idx = _reg_operand(R[z], idx_reg)
            operands = [REG('A'), o] if mnem in ALU_TAKES_A else [o]
            if is_idx:
                add(op, mnem, operands, 2, [19], ALU_FLAGS[mnem], kind='alu',
                    access=[('r', 'idx')])
            elif R[z] == '(HL)':
                add(op, mnem, operands, 1, [7], ALU_FLAGS[mnem], kind='alu',
                    access=[('r', 'hl')])
            else:
                add(op, mnem, operands, 1, [4 + bump], ALU_FLAGS[mnem],
                    kind='alu',
                    undoc=bool(idx_reg and R[z] in ('H', 'L')))

        else:  # x == 3
            if z == 0:
                add(op, 'RET', [COND(CC[y])], 1, [11 + bump, 5 + bump],
                    kind='ret', access=[('r', 'sp')])
            elif z == 1:
                if q == 0:
                    rp = _rp_sub(RP2[p], idx_reg)
                    add(op, 'POP', [REG(rp)], 1, [14 if idx_reg else 10],
                        kind='stack', access=[('r', 'sp')])
                else:
                    if p == 0:
                        add(op, 'RET', [], 1, [10 + bump], kind='ret',
                            access=[('r', 'sp')])
                    elif p == 1:
                        add(op, 'EXX', [], 1, [4 + bump], kind='ex')
                    elif p == 2:
                        add(op, 'JP', [IREG(idx_reg or 'HL', 0)], 1,
                            [8 if idx_reg else 4], kind='jump')
                    else:
                        add(op, 'LD', [REG('SP'), REG(idx_reg or 'HL')], 1,
                            [10 if idx_reg else 6], kind='ld')
            elif z == 2:
                add(op, 'JP', [COND(CC[y]), IMM16], 3, [10 + bump],
                    kind='jump')
            elif z == 3:
                if y == 0:
                    add(op, 'JP', [IMM16], 3, [10 + bump], kind='jump')
                elif y == 1:
                    continue                      # CB prefix, handled apart
                elif y == 2:
                    add(op, 'OUT', [PORTN, REG('A')], 2, [11 + bump],
                        kind='io', io=[('out', 'imm8')])
                elif y == 3:
                    add(op, 'IN', [REG('A'), PORTN], 2, [11 + bump],
                        kind='io', io=[('in', 'imm8')])
                elif y == 4:
                    add(op, 'EX', [IREG('SP', 2), REG(idx_reg or 'HL')], 1,
                        [23 if idx_reg else 19], kind='ex',
                        access=[('r', 'sp'), ('w', 'sp')])
                elif y == 5:
                    add(op, 'EX', [REG('DE'), REG('HL')], 1, [4 + bump],
                        kind='ex')
                elif y == 6:
                    add(op, 'DI', [], 1, [4 + bump], kind='ctl')
                else:
                    add(op, 'EI', [], 1, [4 + bump], kind='ctl')
            elif z == 4:
                add(op, 'CALL', [COND(CC[y]), IMM16], 3,
                    [17 + bump, 10 + bump], kind='call',
                    access=[('w', 'sp')])
            elif z == 5:
                if q == 0:
                    rp = _rp_sub(RP2[p], idx_reg)
                    add(op, 'PUSH', [REG(rp)], 1, [15 if idx_reg else 11],
                        kind='stack', access=[('w', 'sp')])
                else:
                    if p == 0:
                        add(op, 'CALL', [IMM16], 3, [17 + bump], kind='call',
                            access=[('w', 'sp')])
                    else:
                        continue                  # DD / ED / FD prefixes
            elif z == 6:
                mnem = ALU[y]
                operands = [REG('A'), IMM8] if mnem in ALU_TAKES_A else [IMM8]
                add(op, mnem, operands, 2, [7 + bump], ALU_FLAGS[mnem],
                    kind='alu')
            else:  # z == 7
                add(op, 'RST', [RST(y * 8)], 1, [11 + bump], kind='call',
                    access=[('w', 'sp')])

    return ops


def _build_cb(prefix=(0xCB,), idx_reg=None):
    """CB page. With idx_reg this is the DDCB/FDCB page (displacement
    byte sits BETWEEN the CB and the opcode)."""
    ops = {}
    for op in range(256):
        x, y, z = op >> 6, (op >> 3) & 7, op & 7
        if idx_reg:
            target = IDX(idx_reg)
            # DDCB: 4 bytes total (DD CB d op)
            ln = 4
            acc_r, acc_w = ('r', 'idx'), ('w', 'idx')
            cyc_rmw, cyc_bit = 23, 20
        else:
            target, _ = _reg_operand(R[z], None)
            ln = 2
            is_hl = (R[z] == '(HL)')
            acc_r, acc_w = ('r', 'hl'), ('w', 'hl')
            cyc_rmw = 15 if is_hl else 8
            cyc_bit = 12 if is_hl else 8

        touches_mem = idx_reg is not None or R[z] == '(HL)'

        if x == 0:
            mnem = ROT[y]
            operands = [target]
            # TWO INDEPENDENT reasons to flag undocumented here, and the
            # flag must be the OR of them (corrected 2026-09-07):
            #  - SLL (y == 6) is not in Zilog's published set at all. The
            #    Nano Systems Z80 Microprocessor Reference Card (1981) p8
            #    lists it among the undocumented instructions and is where
            #    the SLL mnemonic itself comes from ("we have given them
            #    the mnemonic SLL because it seems most appropriate").
            #  - DDCB/FDCB with z != 6 also copies the result into R[z],
            #    which is a separate undocumented behaviour and the only
            #    one that adds an operand.
            copies_to_reg = bool(idx_reg and z != 6)
            undoc = copies_to_reg or y == 6
            if copies_to_reg:
                operands = [target, REG(R[z])]
            ops[prefix + (op,)] = Op(
                prefix, op, mnem, tuple(operands), ln, (cyc_rmw,),
                '**0P0*', 'bit',
                (acc_r, acc_w) if touches_mem else (), (), undoc)
        elif x == 1:
            ops[prefix + (op,)] = Op(
                prefix, op, 'BIT', (BIT(y), target), ln, (cyc_bit,),
                '?*1?0-', 'bit', (acc_r,) if touches_mem else (), (),
                bool(idx_reg and z != 6))
        else:
            mnem = 'RES' if x == 2 else 'SET'
            operands = [BIT(y), target]
            undoc = bool(idx_reg and z != 6)
            if undoc:
                operands.append(REG(R[z]))
            ops[prefix + (op,)] = Op(
                prefix, op, mnem, tuple(operands), ln, (cyc_rmw,),
                '------', 'bit',
                (acc_r, acc_w) if touches_mem else (), (), undoc)
    return ops


def _build_ed():
    """ED page. Documented instructions only; everything else is a
    2-byte no-operation ('NONI') which we surface as invalid so the
    classifier can count it rather than silently accept garbage."""
    ops = {}
    pfx = (0xED,)

    def add(op, mnem, operands, length, cycles, flags='------',
            kind='misc', access=(), io=(), undoc=False):
        ops[pfx + (op,)] = Op(pfx, op, mnem, tuple(operands), length,
                              tuple(cycles), flags, kind, tuple(access),
                              tuple(io), undoc)

    for op in range(256):
        x, y, z = op >> 6, (op >> 3) & 7, op & 7
        p, q = y >> 1, y & 1

        if x == 1:
            if z == 0:
                if y == 6:
                    add(op, 'IN', [REG('F'), PORTC], 2, [12], '**0P0-',
                        kind='io', io=[('in', 'c')], undoc=True)
                else:
                    add(op, 'IN', [REG(R[y]), PORTC], 2, [12], '**0P0-',
                        kind='io', io=[('in', 'c')])
            elif z == 1:
                if y == 6:
                    add(op, 'OUT', [PORTC, FIXED(0)], 2, [12], kind='io',
                        io=[('out', 'c')], undoc=True)
                else:
                    add(op, 'OUT', [PORTC, REG(R[y])], 2, [12], kind='io',
                        io=[('out', 'c')])
            elif z == 2:
                mnem = 'SBC' if q == 0 else 'ADC'
                fl = '***V1*' if q == 0 else '***V0*'
                add(op, mnem, [REG('HL'), REG(RP[p])], 2, [15], fl,
                    kind='alu')
            elif z == 3:
                if q == 0:
                    add(op, 'LD', [AIMM16(2), REG(RP[p])], 4, [20],
                        kind='ld', access=[('w', 'aimm16')])
                else:
                    add(op, 'LD', [REG(RP[p]), AIMM16(2)], 4, [20],
                        kind='ld', access=[('r', 'aimm16')])
            elif z == 4:
                add(op, 'NEG', [], 2, [8], '***V1*', kind='alu',
                    undoc=(y != 0))
            elif z == 5:
                add(op, 'RETI' if y == 1 else 'RETN', [], 2, [14],
                    kind='ret', access=[('r', 'sp')], undoc=(y not in (0, 1)))
            elif z == 6:
                add(op, 'IM', [FIXED(IM_T[y])], 2, [8], kind='ctl',
                    undoc=(y in (0, 3, 4, 7)))
            else:  # z == 7
                if y == 0:
                    add(op, 'LD', [REG('I'), REG('A')], 2, [9], kind='ld')
                elif y == 1:
                    add(op, 'LD', [REG('R'), REG('A')], 2, [9], kind='ld')
                elif y == 2:
                    add(op, 'LD', [REG('A'), REG('I')], 2, [9], '**0*0-',
                        kind='ld')
                elif y == 3:
                    add(op, 'LD', [REG('A'), REG('R')], 2, [9], '**0*0-',
                        kind='ld')
                elif y == 4:
                    add(op, 'RRD', [], 2, [18], '**0P0-', kind='alu',
                        access=[('r', 'hl'), ('w', 'hl')])
                elif y == 5:
                    add(op, 'RLD', [], 2, [18], '**0P0-', kind='alu',
                        access=[('r', 'hl'), ('w', 'hl')])
                else:
                    add(op, 'NOP', [], 2, [8], kind='nop', undoc=True)

        elif x == 2 and z <= 3 and y >= 4:
            mnem = BLI[y - 4][z]
            repeating = mnem.endswith('R')
            cycles = [21, 16] if repeating else [16]
            if z == 0:      # LDI/LDD/LDIR/LDDR
                acc = [('r', 'hl'), ('w', 'de')]
                fl = '--0*0-'
                io = []
            elif z == 1:    # CPI/CPD/CPIR/CPDR
                acc = [('r', 'hl')]
                fl = '***V1-'
                io = []
            elif z == 2:    # INI/IND/INIR/INDR
                acc = [('w', 'hl')]
                fl = '?*??1?'
                io = [('in', 'c')]
            else:           # OUTI/OUTD/OTIR/OTDR
                acc = [('r', 'hl')]
                fl = '?*??1?'
                io = [('out', 'c')]
            add(op, mnem, [], 2, cycles, fl, kind='block', access=acc, io=io)

        else:
            # Undefined ED opcode: behaves as two NOPs on real hardware.
            add(op, 'DB', [], 2, [8], kind='invalid', undoc=True)

    return ops


def build_table():
    """Expand the declarative structure into one flat table."""
    t = {}
    t.update(_build_main())
    t.update(_build_cb())
    t.update(_build_ed())
    for pfx, ireg in ((0xDD, 'IX'), (0xFD, 'IY')):
        t.update(_build_main(prefix=(pfx,), idx_reg=ireg))
        t.update(_build_cb(prefix=(pfx, 0xCB), idx_reg=ireg))
    return t


TABLE = build_table()

# Inverse index for the future assembler: signature -> encoding.
# Built here (not later, by hand) precisely so the assembler never has
# to re-derive ~700 encodings -- see DESIGN.md seam 2.
INVERSE = {}
for _enc, _op in TABLE.items():
    if _op.kind == 'invalid':
        continue
    _sig = _op.signature()
    # Documented encodings win over undocumented aliases.
    if _sig not in INVERSE or (INVERSE[_sig][1].undoc and not _op.undoc):
        INVERSE[_sig] = (_enc, _op)


def dump_json():
    """The table as plain data -- inspectable, diffable, and the form a
    non-Python consumer would read."""
    out = []
    for enc in sorted(TABLE):
        op = TABLE[enc]
        d = asdict(op)
        d['encoding'] = list(enc)
        d['prefix'] = list(op.prefix)
        d['operands'] = [asdict(o) for o in op.operands]
        d['access'] = [list(a) for a in op.access]
        d['io'] = [list(i) for i in op.io]
        d['cycles'] = list(op.cycles)
        d['signature'] = [op.signature()[0], list(op.signature()[1])]
        out.append(d)
    return out


if __name__ == '__main__':
    import json
    import sys
    json.dump(dump_json(), sys.stdout, indent=1)
