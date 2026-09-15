"""Phase A CLASSIFIER -- Z80 knowledge, consuming the shared table.

Buckets a payload: sound / keyboard / video / pure-compute / ROM-calling
(recording WHICH entry points), and answers the gate question directly:
does STAGE 1 (the CPU plus the USR traps) unlock this routine, or does it
need a Stage 2 HLE trap?

EVIDENCE IS TIERED AND REPORTED SEPARATELY. Three tiers, weakest last:

  direct    an absolute operand: LD A,(3800H), OUT (FFH),A, CALL 0A7FH.
            Visible in the bytes regardless of load address, which is
            why a symbolic VARPTR base does not block classification
            (only relative branches need the base).
  inferred  register-indirect access whose pointer register held a
            known constant: LD HL,3C00H ... LD (HL),A. Without this a
            video routine is invisible, so it must exist -- but it is a
            propagation heuristic, so it is counted apart from direct.
  weak      a 16-bit immediate that merely FALLS IN a device range with
            no access observed through it.

Reporting the tiers separately is the point. A single blended number
would be a plausible heuristic wearing a measurement's clothes.
"""

from dataclasses import dataclass, field

from z80.disasm import disassemble, decode

VIDEO_LO, VIDEO_HI = 0x3C00, 0x3FFF
KBD_LO, KBD_HI = 0x3800, 0x38FF
PRINTER_LO, PRINTER_HI = 0x37E0, 0x37FF
ROM_HI = 0x2FFF                     # Level II ROM occupies 0000-2FFF

# The two ROM entry points Stage 1 was specified with (the USR idiom).
STAGE1_TRAPS = {0x0A7F, 0x0A9A}

# Documented candidates for Stage 2 traps, for naming what we find.
# Names cross-checked 2026-09-06 against the scanned reference library
# (ROM Routines Documented, Micro-80 Level II ROM Reference Manual, Tab
# Books Level II ROMs, Farvour).
# The two Stage 1 traps are named by their ROM SERVICE, not by the USR
# idiom that composes them: 0A7FH is CINT, 0A9AH stores HL into ACCUM.
ROM_NAMES = {
    0x0000: 'RESET', 0x002B: 'KBD scan-once', 0x0033: 'char to display',
    0x003B: 'char to printer', 0x0049: 'wait key', 0x0060: 'delay',
    0x01D3: 'RANDOM', 0x0A7F: 'CINT: ACCUM -> HL (the USR arg fetch)',
    0x0A9A: 'ACCUM = HL (the USR result store)', 0x1BC0: 'tokenize/COMPRESS a BASIC line',
    0x1C90: 'CLS', 0x1D78: 'LIST',
    0x28A7: 'PRINT string', 0x3033: 'DOS entry',
}

PAIRS = ('BC', 'DE', 'HL', 'IX', 'IY', 'SP')
HALVES = {'B': 'BC', 'C': 'BC', 'D': 'DE', 'E': 'DE', 'H': 'HL', 'L': 'HL',
          'IXH': 'IX', 'IXL': 'IX', 'IYH': 'IY', 'IYL': 'IY'}
SRC_TO_PAIR = {'hl': 'HL', 'de': 'DE', 'bc': 'BC', 'sp': 'SP'}


@dataclass
class Evidence:
    direct: set = field(default_factory=set)
    inferred: set = field(default_factory=set)
    weak: set = field(default_factory=set)

    def add(self, tier, tag):
        getattr(self, tier).add(tag)

    def any(self, tag):
        return tag in self.direct or tag in self.inferred

    def as_dict(self):
        return {'direct': sorted(self.direct),
                'inferred': sorted(self.inferred),
                'weak': sorted(self.weak)}


@dataclass
class Classification:
    bucket: str
    buckets_all: list
    evidence: dict
    rom_calls: list                 # sorted [(addr, name)]
    stage1_ok: bool
    stage2_traps: list
    reason: str
    quality: dict
    ports_out: list
    ports_in: list


def _region(addr):
    if KBD_LO <= addr <= KBD_HI:
        return 'keyboard'
    if VIDEO_LO <= addr <= VIDEO_HI:
        return 'video'
    if PRINTER_LO <= addr <= PRINTER_HI:
        return 'printer'
    return None


def walk_reachable(data, base, entries):
    """Recursive descent from the entry offsets.

    Linear sweep alone decodes embedded data as instructions and
    invents evidence. Following flow from a real entry point sees only
    what the CPU would see. Returns (ordered_insns, visited_offsets).
    """
    n = len(data)
    seen = {}
    todo = list(dict.fromkeys(o for o in entries if 0 <= o < n)) or [0]
    while todo:
        off = todo.pop()
        while 0 <= off < n and off not in seen:
            ins = decode(data, off, base)
            if ins.op is None or ins.length <= 0:
                break
            seen[off] = ins
            k = ins.op.kind
            mn = ins.op.mnemonic
            nxt = off + ins.length
            if mn in ('RET', 'RETI', 'RETN') and not ins.op.operands:
                break
            if mn == 'HALT':
                break
            if k == 'jump':
                tgt = ins.target
                inside = (tgt is not None and base <= tgt < base + n)
                cond = any(o.kind == 'cond' for o in ins.op.operands)
                if mn == 'DJNZ':
                    cond = True
                if inside:
                    todo.append(tgt - base)
                if not cond:
                    break                      # unconditional: no fallthru
            elif k == 'call':
                tgt = ins.target
                if tgt is not None and base <= tgt < base + n:
                    todo.append(tgt - base)
            off = nxt
    order = [seen[o] for o in sorted(seen)]
    return order, set(seen)


def _propagate(insns):
    """Attach a best-effort constant to each pointer register.

    Conservative: anything not provably a constant load invalidates.
    """
    regs = {}
    out = []
    for ins in insns:
        out.append((ins, dict(regs)))
        op = ins.op
        if op is None:
            regs.clear()
            continue
        mn = op.mnemonic
        if mn == 'EXX' or mn == 'EX':
            regs.clear()
            continue
        if op.kind == 'block':
            for r in ('HL', 'DE', 'BC'):
                regs.pop(r, None)
            continue
        if (mn == 'LD' and len(op.operands) == 2
                and op.operands[0].kind == 'reg'
                and op.operands[0].value in PAIRS
                and op.operands[1].kind == 'imm16'
                and ins.imm is not None):
            regs[op.operands[0].value] = ins.imm & 0xFFFF
            continue
        # Any other write to a register (or its half) invalidates.
        if op.operands:
            dst = op.operands[0]
            if dst.kind == 'reg':
                v = dst.value
                if v in PAIRS:
                    regs.pop(v, None)
                elif v in HALVES:
                    regs.pop(HALVES[v], None)
            if mn in ('POP',):
                for o in op.operands:
                    if o.kind == 'reg' and o.value in PAIRS:
                        regs.pop(o.value, None)
        if mn in ('INC', 'DEC', 'ADD', 'ADC', 'SBC') and op.operands:
            d = op.operands[0]
            if d.kind == 'reg':
                if d.value in PAIRS:
                    regs.pop(d.value, None)
                elif d.value in HALVES:
                    regs.pop(HALVES[d.value], None)
    return out


def classify(data, base=None, entries=(), payload_kind='candidate-ml'):
    """Classify one payload. `base` may be None for a symbolic load
    address -- classification keys on absolute operands, which do not
    move with the load address."""
    ev = Evidence()
    eff_base = 0 if base is None else base
    insns, visited = walk_reachable(data, eff_base, entries)
    linear = disassemble(data, eff_base)

    rom_calls = {}
    ports_out, ports_in = set(), set()
    invalid = sum(1 for i in insns if i.invalid)

    for ins, regs in _propagate(insns):
        op = ins.op
        if op is None:
            continue

        # ---- tier: direct (absolute operands)
        for mode, addr, _w in ins.abs_addresses():
            r = _region(addr)
            if r == 'keyboard' and mode == 'r':
                ev.add('direct', 'keyboard-read')
            elif r == 'keyboard':
                ev.add('direct', 'keyboard-write')
            elif r == 'video':
                ev.add('direct', 'video-' + ('write' if mode == 'w' else 'read'))
            elif r == 'printer':
                ev.add('direct', 'printer-' + ('write' if mode == 'w' else 'read'))

        p = ins.port()
        if p:
            mode, num = p
            if num is None:
                (ports_out if mode == 'out' else ports_in).add('C')
                ev.add('inferred', 'port-out-indirect' if mode == 'out'
                       else 'port-in-indirect')
            else:
                (ports_out if mode == 'out' else ports_in).add(num)
                if num == 0xFF:
                    ev.add('direct', 'port-FF-' + mode)
                else:
                    ev.add('direct', 'port-%02X-%s' % (num, mode))

        if op.kind == 'call' and ins.target is not None:
            t = ins.target
            if t <= ROM_HI:
                rom_calls[t] = ROM_NAMES.get(t)
                ev.add('direct', 'rom-call')

        # ---- tier: inferred (register-indirect through a known constant)
        for mode, src in op.access:
            pair = SRC_TO_PAIR.get(src)
            if src == 'idx':
                for o in op.operands:
                    if o.kind == 'idx':
                        pair = o.value
            if not pair or pair not in regs:
                continue
            addr = regs[pair]
            if src == 'idx' and ins.disp is not None:
                addr = (addr + ins.disp) & 0xFFFF
            r = _region(addr)
            if r == 'keyboard' and mode == 'r':
                ev.add('inferred', 'keyboard-read')
            elif r == 'video':
                ev.add('inferred', 'video-' +
                       ('write' if mode == 'w' else 'read'))
            elif r == 'printer':
                ev.add('inferred', 'printer-' +
                       ('write' if mode == 'w' else 'read'))

        # ---- tier: weak (a constant that merely lands in a range)
        if (op.mnemonic == 'LD' and len(op.operands) == 2
                and op.operands[1].kind == 'imm16' and ins.imm is not None):
            r = _region(ins.imm)
            if r:
                ev.add('weak', '%s-immediate' % r)

    # ---- decode quality
    last = insns[-1] if insns else None
    ends_clean = bool(last and last.op
                      and last.op.mnemonic in ('RET', 'RETN', 'RETI', 'JP')
                      and (last.offset + last.length) == len(data))
    has_ret = any(i.op and i.op.mnemonic in ('RET', 'RETI', 'RETN')
                  for i in insns)
    covered = sum(i.length for i in insns)
    quality = {
        'reachable_bytes': covered,
        'total_bytes': len(data),
        'coverage': round(covered / len(data), 3) if data else 0.0,
        'invalid_in_reachable': invalid,
        'invalid_in_linear': sum(1 for i in linear if i.invalid),
        'has_ret': has_ret,
        'ends_exactly_on_ret': ends_clean,
    }

    # ---- bucketing
    buckets = []
    if ev.any('port-FF-out'):
        buckets.append('sound')
    if ev.any('keyboard-read'):
        buckets.append('keyboard')
    if ev.any('video-write') or ev.any('video-read'):
        buckets.append('video')
    if ev.any('printer-write'):
        buckets.append('printer')
    non_stage1 = sorted(a for a in rom_calls if a not in STAGE1_TRAPS)
    if non_stage1:
        buckets.append('rom-calling')
    if not buckets:
        buckets.append('pure-compute')

    primary = buckets[0]
    stage1_ok = not non_stage1
    if stage1_ok:
        reason = 'Stage 1 covers this: no ROM call outside 0A7FH/0A9AH.'
    else:
        reason = ('Needs Stage 2 HLE for ' +
                  ', '.join('%04XH' % a for a in non_stage1))

    return Classification(
        bucket=primary,
        buckets_all=buckets,
        evidence=ev.as_dict(),
        rom_calls=sorted((a, ROM_NAMES.get(a)) for a in rom_calls),
        stage1_ok=stage1_ok,
        stage2_traps=non_stage1,
        reason=reason,
        quality=quality,
        ports_out=sorted(ports_out, key=str),
        ports_in=sorted(ports_in, key=str),
    )
