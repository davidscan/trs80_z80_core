"""z80/asm.py: the assembler agrees with the table, the disassembler and the core.

Four things are under test.  Every signature in the inverse index
assembles to bytes the disassembler decodes as that same signature, and
the disassembler's own text assembles back to the same bytes (so a
listing from goal (4) is source for goal (3)).  CATCH, the one real
program the table has assembled so far, comes out byte for byte from
its disassembly.  The EDTASM-shaped source syntax -- line numbers,
labels, EQU forward references, $, the number forms, the data
directives, the dotted operators -- produces the bytes a period listing
would.  And the output formats read back: the load module, the SYSTEM
tape with its checksums, the DATA/POKE loader run by the interpreter
against this core when the interpreter is checked out beside this repo.
"""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from z80 import asm                                             # noqa: E402
from z80.asm import assemble                                    # noqa: E402
from z80.coprocess import Machine                               # noqa: E402
from z80.disasm import decode, disassemble                      # noqa: E402
from z80.table import INVERSE                                   # noqa: E402

ORG = 0x7D00


def one(src, **kw):
    """Assemble one program; fail loudly on errors; return the bytes."""
    r = assemble(src, **kw)
    if r.errors:
        raise AssertionError('errors: %r\n%s' % (r.errors, src))
    return r


def sample_text(ops, op):
    """Source operands for a signature, with values the round trip checks."""
    parts = []
    for tok, o in zip(ops, op.operands):
        k = o.kind
        if k == 'imm8':
            parts.append('0B2H')
        elif k == 'port_imm':
            parts.append('(0B2H)')
        elif k == 'imm16':
            parts.append('0ABCDH')
        elif k == 'aimm16':
            parts.append('(0ABCDH)')
        elif k == 'rel':
            parts.append('%04XH' % (ORG + 0x10))
        elif k == 'idx':
            parts.append('(%s-3)' % o.value)
        else:
            parts.append(tok)
    return ','.join(parts)


class TestTableRoundTrip(unittest.TestCase):
    def test_every_signature_assembles_and_decodes_back(self):
        """asm -> bytes -> disasm gives the signature back, with the
        immediates, displacement and target the source named; and the
        disassembler's text re-assembles to the same bytes."""
        n = 0
        for (m, ops), (enc, op) in INVERSE.items():
            src = '  ORG %04XH\n  %s %s' % (ORG, m, sample_text(ops, op))
            r = assemble(src)
            self.assertFalse(r.errors, '%s: %r' % (src, r.errors))
            b = r.segments[0][1]
            self.assertEqual(len(b), op.length, src)
            self.assertEqual(b[:len(enc)] if enc[1:2] != (0xCB,) or len(enc) < 3 else b[:2] + b[3:4],
                             bytes(enc), src)
            ins = decode(b, 0, ORG)
            self.assertFalse(ins.invalid, src)
            self.assertEqual(ins.length, len(b), src)
            self.assertEqual(ins.op.signature(), (m, ops), src)
            self.assertEqual(ins.op.undoc, op.undoc, 'a documented form must win: ' + src)
            for o in op.operands:
                if o.kind in ('imm8', 'port_imm'):
                    self.assertEqual(ins.imm, 0xB2, src)
                elif o.kind in ('imm16', 'aimm16'):
                    self.assertEqual(ins.imm, 0xABCD, src)
                elif o.kind == 'rel':
                    self.assertEqual(ins.target, ORG + 0x10, src)
                elif o.kind == 'idx':
                    self.assertEqual(ins.disp, -3, src)
            r2 = assemble('  ORG %04XH\n  %s' % (ORG, ins.text))
            self.assertFalse(r2.errors, '%s -> %r: %r' % (src, ins.text, r2.errors))
            self.assertEqual(r2.segments[0][1], b, '%s -> %r' % (src, ins.text))
            n += 1
        self.assertEqual(n, len(INVERSE))

    def test_ddcb_displacement_sits_before_the_last_opcode_byte(self):
        b = one('  ORG 0\n  BIT 0,(IX+3)\n  SET 7,(IY-1)\n  RLC (IX+7FH)').segments[0][1]
        self.assertEqual(b.hex(), 'ddcb0346' 'fdcbfffe' 'ddcb7f06')

    def test_catch_reassembles_byte_for_byte(self):
        """The disassembly of the game (data rendered as DEFB) is source
        that assembles to the game."""
        import mkgame
        org = 32000
        _, code, _, _ = mkgame.build(org, 30)
        lines = ['  ORG %d' % org]
        for ins in disassemble(code, org):
            if ins.invalid or ins.ignored_prefixes or ins.truncated:
                lines.append('  DEFB ' + ','.join('%02XH' % x for x in ins.raw))
            else:
                lines.append('  ' + ins.text)
        r = one('\n'.join(lines))
        self.assertEqual(r.segments, [(org, code)])

    def test_mkgame_asm_agrees_on_an_indexed_bit_instruction(self):
        """The game tool's little assembler emits the same DD CB bytes."""
        import mkgame
        a = mkgame.Asm(0)
        a.op('BIT', ('0', '(IX+d)'), 3)
        a.op('LD', ('(IX+d)', 'n'), 5, 0x12)
        self.assertEqual(a.assemble(),
                         one('  ORG 0\n  BIT 0,(IX+3)\n  LD (IX+5),12H').segments[0][1])


SAMPLE = '''\
00100 ; A SAMPLE IN THE EDITOR/ASSEMBLER'S SHAPE
00110 VIDEO   EQU  3C00H
00120 LAST    EQU  DONE-1        ;a forward reference
00130         ORG  7D00H
00140 START   LD   HL,VIDEO
00150         LD   DE, VIDEO+1   ; a space after the comma
00160         LD   BC,1023
00170         LD   (HL),' '
00180         LDIR
00190 LOOP:   LD   A,(3840H)
00200         BIT  7,A
00210         JR   Z,LOOP
00220         LD   A,(IX+5)
00230         LD   (IY-2),0FFH
00240         SUB  A,B
00250         ADD  B
00260         CP   A,'A'
00270         RST  38H
00280         IM   1
00290         OUT  (0FFH),A
00300         IN   A,(C)
00310         JP   (HL)
00320         LD   A,(IX)
00330         DJNZ LOOP
00340         LD   HL,$-2
00350         LD   A,1010B+377Q+.NOT.0 .AND. 0FH
00360         LD   A,-1
00370         DEFB 1,2,'AB',3
00380 MSG     DEFM 'IT''S OK'
00390         DEFW MSG,1234H,'Z'
00400         DEFS 3,0AAH
00410 DONE    NOP
00420         EX   AF,AF'
00430         END  START
* a comment after END is not assembled
'''

SAMPLE_HEX = (
    '21003c' '11013c' '01ff03' '3620' 'edb0' '3a4038' 'cb7f' '28f9'
    'dd7e05' 'fd36feff' '90' '80' 'fe41' 'ff' 'ed56' 'd3ff' 'ed78' 'e9'
    'dd7e00' '10e1' '212a7d' '3e08' '3eff' '01024142' '03' '495427532' '04f4b'
    '387d' '3412' '5a00' 'aaaaaa' '00' '08')


class TestSyntax(unittest.TestCase):
    def test_sample_bytes_symbols_and_entry(self):
        r = one(SAMPLE)
        self.assertEqual(r.segments[0][1].hex(), SAMPLE_HEX)
        self.assertEqual(r.segments[0][0], 0x7D00)
        self.assertEqual(r.entry, 0x7D00)
        self.assertEqual(r.symbols['VIDEO'], 0x3C00)
        self.assertEqual(r.symbols['LOOP'], 0x7D0D)
        self.assertEqual(r.symbols['DONE'], 0x7D48)
        self.assertEqual(r.symbols['LAST'], 0x7D47)      # the forward EQU

    def test_listing_shows_address_bytes_and_source(self):
        lst = one(SAMPLE).listing()
        self.assertIn('7D00  21 00 3C     00140 START   LD   HL,VIDEO', lst)
        self.assertIn('3C00  =            00110 VIDEO   EQU  3C00H', lst)
        self.assertIn('7D38  49 54 27 53  00380 MSG     DEFM', lst)
        self.assertIn('7D3C  20 4F 4B', lst)                 # the continuation line

    def test_numbers_and_operators(self):
        b = one('  ORG 0\n  DEFW 0FFFFH,65535,177777Q,1111111111111111B,\'AB\'\n'
                '  DEFB 7.MOD.4, 1.SHL.4, 255.SHR.4, 0FH.AND.3, 4.OR.1, 5.XOR.1, .NOT.0\n'
                '  DEFB 2+3*4, (2+3)*4, -1, 10/3').segments[0][1]
        self.assertEqual(b.hex(), 'ffff' 'ffff' 'ffff' 'ffff' '4142'
                                  '03' '10' '0f' '03' '05' '04' 'ff'
                                  '0e' '14' 'ff' '03')

    def test_memory_versus_value_operands(self):
        b = one('  ORG 100H\nBUF DEFS 2\n  LD A,(BUF+1)\n  LD HL,BUF+1\n  LD HL,(BUF)\n'
                '  JP (IX)\n  LD A,(IY)').segments[0][1]
        self.assertEqual(b.hex(), '0000' '3a0101' '210101' '2a0001' 'dde9' 'fd7e00')

    def test_lowercase_and_no_line_numbers(self):
        b = one('   org 7000h\nstart:  ld a,0ffh\n        jr start\n        end start')
        self.assertEqual(b.segments[0][1].hex(), '3eff18fc')
        self.assertEqual(b.entry, 0x7000)

    def test_org_blocks_and_bin_image(self):
        r = one('  ORG 100H\n  DEFB 1,2\n  ORG 102H\n  DEFB 3\n  ORG 110H\n  DEFB 4')
        self.assertEqual(r.segments, [(0x100, b'\x01\x02\x03'), (0x110, b'\x04')])
        self.assertEqual(r.to_bin(), b'\x01\x02\x03' + bytes(13) + b'\x04')

    def test_org_and_entry_fallbacks(self):
        r = one('  LD A,1\n', org=0x8000)
        self.assertEqual(r.segments, [(0x8000, b'\x3e\x01')])
        self.assertEqual(r.entry, 0x8000)
        self.assertEqual(one('  LD A,1\n', org=0x8000, entry=0x9000).entry, 0x9000)
        self.assertEqual(one('  ORG 1\n  NOP\n  END 5\n', entry=0x9000).entry, 5)

    def test_undocumented_forms_assemble_only_when_asked(self):
        """SLL and IXH exist in the table as undocumented; a documented
        spelling must never land on an undocumented encoding."""
        self.assertEqual(one('  ORG 0\n  SLL B').segments[0][1].hex(), 'cb30')
        self.assertEqual(one('  ORG 0\n  LD IXH,5').segments[0][1].hex(), 'dd2605')
        self.assertEqual(one('  ORG 0\n  RLC B').segments[0][1].hex(), 'cb00')


class TestErrors(unittest.TestCase):
    def errors(self, src, **kw):
        return assemble(src, **kw).errors

    def test_syntax_errors_name_the_line_and_stop_before_emission(self):
        e = self.errors('  ORG 0\n  LD A,1\n  FOO BAR\n  BIT 9,A\n  LD A,(3\n')
        self.assertEqual([ln for ln, _ in e], [3, 4, 5])
        self.assertIn('unknown instruction', e[0][1])
        self.assertIn('no such instruction: BIT 9,A', e[1][1])

    def test_value_errors_are_reported_together(self):
        e = self.errors('  ORG 0\n  LD A,300\n  JR 1000H\n  LD A,UNDEF\n  LD (IX+200),A\n'
                        '  LD HL,70000\n')
        self.assertEqual([ln for ln, _ in e], [2, 3, 4, 5, 6])
        self.assertIn('out of range', e[0][1])
        self.assertIn('relative jump out of range', e[1][1])
        self.assertIn('undefined symbol UNDEF', e[2][1])
        self.assertIn('displacement', e[3][1])

    def test_the_rest(self):
        self.assertIn('no ORG', self.errors('  LD A,1\n')[0][1])
        self.assertIn('duplicate label', self.errors('  ORG 0\nA1 NOP\nA1 NOP\n')[0][1])
        self.assertIn('EQU needs a label', self.errors('  ORG 0\n  EQU 5\n')[0][1])
        self.assertIn('undefined symbol', self.errors('  ORG 0\nX EQU Y+1\n  NOP\n')[0][1])
        self.assertIn('unterminated', self.errors("  ORG 0\n  DEFM 'ABC\n")[0][1])
        self.assertIn('known here', self.errors('  ORG 0\n  DEFS N\nN EQU 3\n')[0][1])
        self.assertIn('no such instruction', self.errors('  ORG 0\n  RST FWD\nFWD EQU 8\n')[0][1])
        self.assertIn('division by zero', self.errors('  ORG 0\n  DEFB 1/0\n')[0][1])
        self.assertIn('bad number', self.errors('  ORG 0\n  DEFB 12G\n')[0][1])

    def test_a_label_is_defined_once_however_it_is_made(self):
        for src in ('  ORG 0\nX NOP\nX EQU 5\n  LD HL,X\n',
                    '  ORG 0\nX EQU 5\nX NOP\n',
                    '  ORG 0\nX EQU 5\nX EQU 6\n',
                    '  ORG 0\nX EQU Y\nX NOP\nY EQU 1\n',        # the first X is deferred
                    '  ORG 0\nX NOP\nX ORG 100H\n',
                    'X ORG 0\nX NOP\n'):
            e = self.errors(src)
            self.assertEqual(len(e), 1, src)
            self.assertIn('duplicate label X', e[0][1])

    def test_the_location_counter_stops_at_the_top_of_memory(self):
        e = self.errors('  ORG 0FFFEH\n  DEFB 1,2,3,4\n  NOP\n')
        self.assertEqual([ln for ln, _ in e], [2])
        self.assertIn('runs past 0FFFFH: 4 byte(s) at FFFEH', e[0][1])
        self.assertIn('runs past', self.errors('  ORG 0FFFFH\n  LD HL,0\n')[0][1])
        self.assertIn('runs past', self.errors('  ORG 8000H\n  DEFS 8001H\n')[0][1])
        r = assemble('  ORG 0FFFEH\n  DEFB 1,2\nTOP EQU $\n  END\n')   # the last byte is usable
        self.assertEqual((r.errors, r.segments, r.symbols['TOP']),
                         ([], [(0xFFFE, b'\x01\x02')], 0x10000))


TINY = '  ORG 7D00H\n  LD HL,1234H\n  JP 0A9AH\n  END\n'


def headless(code, org, entry):
    """Run the bytes in the core with no keyboard and no ticks."""
    m = Machine(lambda s: None, lambda: 'K 0', 0.0)
    for i, b in enumerate(code):
        m.ram[org + i] = b
        m.known[org + i] = 1
    m.run(entry, 0, 0xFF00)
    return m


class TestOutputs(unittest.TestCase):
    def test_cmd_records_read_back(self):
        r = one('  ORG 7000H\n  DEFS 300,1\n  ORG 8000H\n  DEFB 2\n  END 7005H\n')
        data = r.to_cmd('sample')
        i, blocks, entry, name = 0, [], None, None
        while i < len(data):
            t, n = data[i], data[i + 1]
            body = data[i + 2:i + 2 + n]
            i += 2 + n
            if t == 0x05:
                name = body.decode()
            elif t == 0x01:
                blocks.append((body[0] | (body[1] << 8), bytes(body[2:])))
            elif t == 0x02:
                entry = body[0] | (body[1] << 8)
        self.assertEqual(name, 'SAMPLE')
        self.assertEqual(entry, 0x7005)
        self.assertEqual([(a, len(b)) for a, b in blocks], [(0x7000, 253), (0x70FD, 47), (0x8000, 1)])
        self.assertEqual(b''.join(b for _, b in blocks), bytes([1]) * 300 + b'\x02')
        self.assertEqual(i, len(data))

    def test_cas_blocks_and_checksums_read_back(self):
        r = one('  ORG 4300H\n  DEFS 300,7\n  END 4302H\n')
        data = r.to_cas('sample')
        self.assertEqual(data[:258], bytes(256) + b'\xa5\x55')
        self.assertEqual(data[258:264], b'SAMPLE')
        i, blocks = 264, []
        while data[i] == 0x3C:
            n = data[i + 1] or 256
            a = data[i + 2] | (data[i + 3] << 8)
            body = data[i + 4:i + 4 + n]
            self.assertEqual(data[i + 4 + n], (sum(body) + data[i + 2] + data[i + 3]) & 0xFF)
            blocks.append((a, bytes(body)))
            i += 5 + n
        self.assertEqual(data[i:], b'\x78\x02\x43')
        self.assertEqual([(a, len(b)) for a, b in blocks], [(0x4300, 256), (0x4400, 44)])
        self.assertEqual(b''.join(b for _, b in blocks), bytes([7]) * 300)

    def test_bas_loader_shape(self):
        r = one(TINY)
        bas = r.to_bas('tiny')
        self.assertIn('20 E=32000:C=0', bas)
        self.assertIn('30 FOR I=0 TO 5:READ B:POKE E+I,B:C=C+B:NEXT', bas)
        self.assertIn('40 IF C<>%d THEN' % sum(r.segments[0][1]), bas)
        self.assertIn('50 DEFUSR=32000', bas)
        self.assertIn('1000 DATA 33,52,18,195,154,10', bas)
        with self.assertRaises(ValueError):
            one('  ORG 0\n  NOP\n  ORG 10H\n  NOP\n').to_bas('two')

    def test_the_core_runs_what_was_assembled(self):
        r = one(TINY)
        m = headless(r.segments[0][1], 0x7D00, r.entry)
        self.assertEqual(m.result, 1)
        self.assertEqual(m.cpu.hl, 0x1234)

    def test_the_interpreter_runs_the_bas_loader(self):
        """`PRINT USR(0)` through the BASIC loader, the interpreter checked
        out beside this repo driving this core.  Skipped without it."""
        basic = os.path.join(os.path.dirname(ROOT), 'trs80basic', 'basic')
        if not os.access(basic, os.X_OK):
            self.skipTest('no ../trs80basic/basic beside this repo')
        r = one(TINY)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'tiny.bas')
            with open(path, 'w') as f:
                f.write(r.to_bas('tiny'))
            env = dict(os.environ, TRS80_Z80='python3 ' + os.path.join(ROOT, 'core.py'),
                       TRS80_DUMB='1', TRS80_USR='strict')
            p = subprocess.run([basic, path], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('4660', p.stdout)


class TestCommandLine(unittest.TestCase):
    def test_main_writes_the_object_and_the_listing(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, 't.asm')
            with open(src, 'w') as f:
                f.write(TINY)
            out = os.path.join(d, 't.cmd')
            lst = os.path.join(d, 't.lst')
            self.assertEqual(asm.main([src, '-o', out, '--list', lst, '--symbols']), 0)
            with open(out, 'rb') as f:
                self.assertEqual(f.read()[:4], b'\x05\x01T\x01')
            with open(lst) as f:
                self.assertIn('7D00  21 34 12       LD HL,1234H', f.read())
            bad = os.path.join(d, 'bad.asm')
            with open(bad, 'w') as f:
                f.write('  ORG 0\n  LD A,(3\n')
            self.assertEqual(asm.main([bad, '-o', out]), 1)


if __name__ == '__main__':
    unittest.main()
