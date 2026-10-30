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
import io
import os
import random
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr

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

    def test_a_disassembly_listing_assembles_back_to_its_bytes(self):
        """The README's claim, held to: undefined ED opcodes, second
        encodings (ED 77, ED 4C) and prefixes that change nothing come back
        as DB, so no line is shorter than its bytes and no address moves."""
        from z80.disasm import listing
        rng = random.Random(19780801)
        soup = bytes(rng.randrange(256) for _ in range(6000))
        stray = bytes.fromhex('ED00 ED77 DD00 DDDD213412 FDED44 DDFD7E01 DDCB01C9 ED4C 18FE')
        for data, base in ((soup, 0x4000), (stray, 0x7000), (stray + b'\xdd', 0xFFE0)):
            lines = listing(data, base).splitlines()
            src = ' ORG %d\n' % base + ''.join(' %s\n' % ln[20:].split('  ', 1)[-1].strip()
                                               for ln in lines)
            r = assemble(src)
            self.assertEqual(r.errors, [])
            self.assertEqual(r.segments, [(base, data)])
        self.assertIn('DB 0EDH,00H', listing(stray, 0))
        self.assertIn('DB 0EDH,77H ;NOP', listing(stray, 0))

    def test_an_empty_db_is_an_error(self):
        for d in ('DB', 'DEFB', 'DEFW', 'DEFM'):
            e = assemble('  ORG 0\n  %s\n' % d).errors
            self.assertEqual(len(e), 1, d)
            self.assertIn('at least one item', e[0][1])

    def test_the_exact_jr_and_index_displacement_limits(self):
        """the boundaries themselves, so a mutant off by one fails."""
        # JR e: -128..+127 from the byte after the instruction
        self.assertEqual(one('  ORG 0\n  JR $+129\n').segments[0][1].hex(), '187f')
        self.assertEqual(one('  ORG 0\n  JR $-126\n').segments[0][1].hex(), '1880')
        for bad in ('  JR $+130\n', '  JR $-127\n'):
            e = assemble('  ORG 0\n' + bad).errors
            self.assertEqual(len(e), 1, bad)
            self.assertIn('relative jump out of range', e[0][1])
        # (IX+d): -128..+127
        self.assertEqual(one('  ORG 0\n  LD A,(IX+127)\n').segments[0][1].hex(),
                         'dd7e7f')
        self.assertEqual(one('  ORG 0\n  LD A,(IX-128)\n').segments[0][1].hex(),
                         'dd7e80')
        for bad in ('  LD A,(IX+128)\n', '  LD A,(IX-129)\n'):
            e = assemble('  ORG 0\n' + bad).errors
            self.assertEqual(len(e), 1, bad)
            self.assertIn('index displacement out of range', e[0][1])

    def test_a_register_or_flag_name_is_not_a_label(self):
        """`I EQU 10 / LD A,I` assembled the register form ED 57 with the
        label silently unread."""
        for bad in ('I EQU 10\n', 'C EQU 20H\n', 'NZ EQU 5\n', 'B NOP\n',
                    'HL: NOP\n'):
            e = assemble('  ORG 0\n' + bad).errors
            self.assertEqual(len(e), 1, bad)
            self.assertIn('register or flag name', e[0][1])

    def test_edtasm_ampersand_and_shift_operators(self):
        """Barden p.47: EDTASM's own operators are +, -, & and <."""
        b = one('  ORG 0\n'
                'HEADA EQU 1234H\n'
                '  DEFB HEADA&0FFH\n'
                '  LD A,1<3\n'
                '  DEFB 300H<-4\n').segments[0][1]
        self.assertEqual(b.hex(), '34' '3e08' '30')
        e = assemble('  ORG 0\n  DEFB 1<17\n').errors
        self.assertEqual(len(e), 1)
        self.assertIn('shift count', e[0][1])

    def test_an_indented_word_is_an_opcode_never_a_label(self):
        """Barden p.40-42: the label field ends where the indentation
        begins, so a misspelled mnemonic is an error, not a silent label."""
        for bad in ('  RETT\n', '  HLT\n', '00100   ENDZAP\n'):
            e = assemble('  ORG 0\n' + bad).errors
            self.assertEqual(len(e), 1, bad)
            self.assertIn('unknown instruction', e[0][1])
        r = assemble('  ORG 0\nSTART NOP\nLOOP: JR LOOP\n  END START')
        self.assertEqual(r.errors, [])

    def test_a_column_one_label_may_be_spelled_like_an_opcode(self):
        """Barden p.41-42, free format as long as an op-code does not
        start in column 1; corpus sources label lines OUT, SET, BIT, END,
        AND, INC, DEC, RET.  An op-code in column 1 is refused, saying so."""
        r = one('  ORG 0\nOUT LD H,B\nSET NOP\nEND JR OUT\nBIT: INC A\nDEFB EQU 7\n'
                '00100 AND RET\n  LD A,DEFB\n  END OUT\n')
        self.assertEqual(r.symbols, {'OUT': 0, 'SET': 1, 'END': 2, 'BIT': 4, 'DEFB': 7, 'AND': 5})
        self.assertEqual(r.segments[0][1].hex(), '60' '00' '18fc' '3c' 'c9' '3e07')
        self.assertEqual(r.entry, 0)
        for bad in ('LD A,1\n', '00100 JP 0\n', 'ORG 100H\n'):
            e = assemble('  ORG 0\n' + bad).errors
            self.assertEqual(len(e), 1, bad)
            self.assertIn('in column 1 is a label; an op-code is indented', e[0][1])
        # a column-1 word alone is a label on its own line, as ever
        self.assertEqual(one('  ORG 0\n00100 NOP\n  RET\n').symbols, {'NOP': 0})

    def test_a_data_string_with_no_closing_quote_runs_to_the_end_of_the_line(self):
        """As EDTASM took it: TBBS's MINIHOST/SRC line 5140 against its
        period object.  A lost quote anywhere else is still an error."""
        r = one("  ORG 0\n  DEFM 'ABC ; not a comment\n  DB 1,'D''E\n  DEFM \"F\n")
        self.assertEqual(r.segments[0][1], b"ABC ; not a comment" b"\x01D'E" b"F")
        for bad in ("  LD A,'X\n", "  DEFW 'A\n", "  DEFM 'A','B\n  LD A,'\n"):
            e = assemble('  ORG 0\n' + bad).errors
            self.assertTrue(e, bad)
            self.assertIn('unterminated', e[0][1])

    def test_defs_reserves_its_bytes_and_writes_none(self):
        """Barden p.45-46, "A DEFS does not fill the vacant space with
        zeroes"; every period object beside a corpus source that uses DEFS
        skips the space.  The object's blocks end before it and start after;
        a trailing DEFS leaves nothing; a fill operand (this assembler's own)
        still fills; the labels and the location counter are as before."""
        r = one('  ORG 7000H\n  LD A,1\nBUF DEFS 300\nNEXT LD A,2\n  DEFS 4,0AAH\n'
                'TAIL DEFS 100H\nTOP EQU $\n  END\n')
        self.assertEqual(r.segments, [(0x7000, b'\x3e\x01'),
                                      (0x712E, b'\x3e\x02' + b'\xaa' * 4)])
        self.assertEqual((r.symbols['BUF'], r.symbols['NEXT'], r.symbols['TAIL'],
                          r.symbols['TOP']), (0x7002, 0x712E, 0x7134, 0x7234))
        self.assertEqual(r.to_bin(), b'\x3e\x01' + bytes(300) + b'\x3e\x02' + b'\xaa' * 4)
        cmd = r.to_cmd('x')
        self.assertEqual(cmd[-4:], b'\x02\x02\x00\x70')
        self.assertNotIn(bytes(100), cmd)
        self.assertEqual(len(r.to_cas('x')), 256 + 2 + 6 + (5 + 2) + (5 + 6) + 3)
        # the harm case: a screen buffer declared over the display
        r = one('  ORG 3C00H\nSCREEN DEFS 1024\n  ORG 7000H\n  RET\n')
        self.assertEqual(r.segments, [(0x7000, b'\xc9')])
        # a DEFS that would run past the top of memory is still refused
        self.assertIn('runs past', assemble('  ORG 0FF00H\n  DEFS 101H\n').errors[0][1])

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
        # 1234H is here because the four spellings of 0FFFFH before it are
        # palindromes: the line could not tell a word stored low byte first
        # from one stored high byte first, and so it pinned DEFW 'AB' as
        # 41 42 for a value the module documents as 4142H (the 2026-09-19
        # audit).  A word is a word however it is written.
        b = one('  ORG 0\n  DEFW 0FFFFH,65535,177777Q,1111111111111111B,1234H,\'AB\'\n'
                '  DEFB 7.MOD.4, 1.SHL.4, 255.SHR.4, 0FH.AND.3, 4.OR.1, 5.XOR.1, .NOT.0\n'
                '  DEFB 2+3*4, (2+3)*4, -1, 10/3, -7/2').segments[0][1]
        self.assertEqual(b.hex(), 'ffff' 'ffff' 'ffff' 'ffff' '3412' '4241'
                                  '03' '10' '0f' '03' '05' '04' 'ff'
                                  '14' '14' 'ff' '03' 'fd')       # 2+3*4 is 20: EDTASM's order

    def test_the_order_of_evaluation_is_edtasms_unless_asked(self):
        """Left to right with no precedence by default (the Editor/Assembler
        manual; the user's ruling of 2026-10-15), the usual order with
        precedence=True (--precedence); parentheses and unary signs work in
        both.  `/` truncates toward zero either way (-7/2 is -3)."""
        src = ('  ORG 0\n  DEFB 2+3*4, 10-2-3, 2*3+4, 1+2.AND.3, 20/2/5, 2+3*-1\n'
               '  DEFW 1<4+1, 100H+(2+3)*4, -7/2, 0FFH&0FH+1\n')
        ltr = one(src).segments[0][1]
        self.assertEqual(ltr.hex(), '14' '05' '0a' '03' '02' 'fb'
                                    '1100' '1404' 'fdff' '1000')
        usual = one(src, precedence=True).segments[0][1]
        self.assertEqual(usual.hex(), '0e' '05' '0a' '03' '02' 'ff'
                                      '1100' '1401' 'fdff' '1000')

    def test_an_expression_whose_value_depends_on_the_order_is_a_warning(self):
        """Both values are reported, once per expression, in either mode;
        an expression that comes out the same either way is not."""
        r = one('  ORG 0\nV EQU 2+3*4\n  LD A,V\n  LD HL,V+1\n  DEFB 1+2+3, 4*5, (1+2)*3, V\n')
        self.assertEqual([ln for ln, _ in r.warnings], [2])
        self.assertIn('2+3*4 is 20 left to right (EDTASM, used) and 14 with operator '
                      'precedence (--precedence)', r.warnings[0][1])
        self.assertEqual(r.segments[0][1].hex(), '3e14' '211500' '06' '14' '09' '14')
        r = one('  ORG 0\n  LD A,2+3*4\n  LD HL,2+3*4\n', precedence=True)
        self.assertEqual([ln for ln, _ in r.warnings], [2, 3])      # once a line, two passes
        self.assertIn('20 left to right (EDTASM) and 14 with operator precedence '
                      '(--precedence, used)', r.warnings[0][1])
        self.assertEqual(r.segments[0][1].hex(), '3e0e' '210e00')
        self.assertEqual(one('  ORG 0\n  DEFB 1+2+3, 2*3*4, (2+3)*4\n').warnings, [])
        # the other order failing (a shift count out of range) is no warning
        self.assertEqual(one('  ORG 0\n  DEFW 1<4+1\n').warnings, [])

    def test_memory_versus_value_operands(self):
        r = one('  ORG 100H\nBUF DEFS 2\n  LD A,(BUF+1)\n  LD HL,BUF+1\n  LD HL,(BUF)\n'
                '  JP (IX)\n  LD A,(IY)')
        self.assertEqual(r.segments, [(0x102, bytes.fromhex('3a0101' '210101' '2a0001'
                                                            'dde9' 'fd7e00'))])

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
        self.assertIn('unterminated', self.errors("  ORG 0\n  DEFW 'ABC\n")[0][1])
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

    def test_operands_are_not_quietly_cut_to_fit(self):
        for src, what in (('  DB 1 2\n', 'missing operator or comma'),
                          ('  LD A,1 0\n', 'missing operator or comma'),
                          ("  DEFM 'A' 'B'\n", 'missing operator or comma'),
                          ('  LD A,(HL) 5\n', 'missing operator or comma'),
                          ('  LD A,-200\n', 'out of range'),
                          ('  DEFB -129\n', 'out of range'),
                          ('  DEFB 256\n', 'out of range'),
                          ('  DEFW -32769\n', 'out of range'),
                          ('  LD HL,65536\n', 'out of range'),
                          ('  RST 138H\n', 'no such instruction'),
                          ('  RST -200\n', 'no such instruction')):
            e = self.errors('  ORG 0\n' + src)
            self.assertEqual(len(e), 1, src)
            self.assertIn(what, e[0][1], src)

    def test_blanks_around_operators_and_signed_values_still_assemble(self):
        r = assemble("  ORG 0\nV EQU 3C00H\n  LD HL, 5 * 64 + V\n  LD A, ( V )\n  LD (IX + 2), -1\n"
                     "  DEFB -128, 255, 'A' , 1 .SHL. 3\n  DEFW -32768, 65535, -2 .SHR. 1, 1 .SHL. 16\n"
                     "  DEFM 'DON''T', 13\n  RST 38H\n  EX AF, AF'\n")
        self.assertEqual(r.errors, [])
        self.assertEqual(r.segments[0][1],
                         bytes.fromhex('21403d' '3a003c' 'dd3602ff' '80ff4108'
                                       '0080ffffff7f0000') + b"DON'T\r" + bytes.fromhex('ff08'))

    def test_a_shift_count_is_checked(self):
        self.assertIn('shift count out of range: -1',
                      self.errors('  ORG 0\n  DEFB 1 .SHL. -1\n')[0][1])
        self.assertIn('shift count', self.errors('  ORG 0\n  DEFW 1 .SHR. 99999999\n')[0][1])

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
        self.assertIn('50 POKE 16526,0:POKE 16527,125', bas)
        self.assertIn('1000 DATA 33,52,18,195,154,10', bas)
        with self.assertRaises(ValueError):
            one('  ORG 0\n  NOP\n  ORG 10H\n  NOP\n').to_bas('two')
        with self.assertRaisesRegex(ValueError, 'DEFS inside the code'):
            one('  ORG 0\n  NOP\n  DEFS 10H\n  NOP\n').to_bas('split')
        self.assertIn('1000 DATA 0', one('  ORG 0\n  NOP\n  DEFS 10H\n').to_bas('trailing'))
        # above 7FFFH the loader uses the signed POKE idiom (Level II)
        hi = one('  ORG 0A000H\n  RET\n  END 0A000H\n').to_bas('hi')
        self.assertIn('20 E=-24576:C=0', hi)
        self.assertIn('50 POKE 16526,0:POKE 16527,160', hi)
        self.assertIn('20 E=-32768:C=0', one('  ORG 8000H\n  RET\n').to_bas('edge'))
        self.assertIn('20 E=32767:C=0', one('  ORG 7FFFH\n  RET\n').to_bas('edge'))
        # a block straddling 8000H turns the address over as it crosses
        st = one('  ORG 7FF8H\n  DEFS 10,0\n  LD HL,1234H\n  JP 0A9AH\n').to_bas('st')
        self.assertIn('20 E=32760:C=0', st)
        self.assertIn('30 FOR I=0 TO 15:READ B:A=E+I:IF A>32767 THEN A=A-65536', st)
        self.assertIn('35 POKE A,B:C=C+B:NEXT', st)
        self.assertIn('50 POKE 16526,248:POKE 16527,127', st)

    def test_the_interpreter_loads_a_block_straddling_8000h(self):
        """`ORG 7FF8H`, 16 bytes, gave `?OV ERROR IN 30`.  Through the
        interpreter driving this core: the routine runs and answers."""
        basic = os.path.join(os.path.dirname(ROOT), 'trs80basic', 'basic')
        if not os.access(basic, os.X_OK):
            self.skipTest('no ../trs80basic/basic beside this repo')
        r = one('  ORG 7FF8H\n  DEFS 10,0\n  LD HL,1234H\n  JP 0A9AH\n')
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'st.bas')
            with open(path, 'w') as f:
                f.write(r.to_bas('st'))
            env = dict(os.environ, TRS80_Z80='python3 ' + os.path.join(ROOT, 'core.py'),
                       TRS80_DUMB='1', TRS80_USR='strict')
            p = subprocess.run([basic, path], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn('?OV', p.stdout + p.stderr)
        self.assertIn('4660', p.stdout)

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

    def test_precedence_switch_and_warnings_on_the_command_line(self):
        src_text = '  ORG 7D00H\n  LD HL,2+3*4\n  END\n'
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, 'p.asm')
            with open(src, 'w') as f:
                f.write(src_text)
            out = os.path.join(d, 'p.bin')
            err = io.StringIO()
            with redirect_stderr(err):
                self.assertEqual(asm.main([src, '-o', out]), 0)
            with open(out, 'rb') as f:
                self.assertEqual(f.read(), b'\x21\x14\x00')
            self.assertIn('p.asm:2: warning: 2+3*4 is 20 left to right (EDTASM, used) and 14 '
                          'with operator precedence (--precedence)', err.getvalue())
            with redirect_stderr(io.StringIO()):
                self.assertEqual(asm.main([src, '-o', out, '--precedence']), 0)
            with open(out, 'rb') as f:
                self.assertEqual(f.read(), b'\x21\x0e\x00')

    def test_an_output_that_is_the_source_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, 't.asm')
            with open(src, 'w') as f:
                f.write(TINY)
            link = os.path.join(d, 'link.asm')
            os.symlink(src, link)
            out = os.path.join(d, 'same.out')
            with redirect_stderr(io.StringIO()):
                for argv in ([src, '-o', src], [src, '--list', src],
                             [src, '-o', os.path.join(d, '.', 't.asm')], [src, '-o', link],
                             [src, '-o', out, '--list', out]):
                    self.assertEqual(asm.main(argv), 1, argv)
            with open(src) as f:
                self.assertEqual(f.read(), TINY)
            self.assertFalse(os.path.exists(out))

    def test_bad_command_lines_are_messages_not_tracebacks(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, 't\u00e9.asm')
            with open(src, 'w') as f:
                f.write(TINY)
            err = io.StringIO()
            with redirect_stderr(err):
                self.assertEqual(asm.main([os.path.join(d, 'missing.asm')]), 1)
                for ext in ('cmd', 'cas'):          # the name comes from the file's
                    self.assertEqual(asm.main([src, '-o', os.path.join(d, 'o.' + ext)]), 1)
                self.assertEqual(asm.main([src, '-o', os.path.join(d, 'o.cmd'), '--name', 'TE']), 0)
                self.assertEqual(asm.main([src, '-o', os.path.join(d, 'nowhere', 'o.bin')]), 1)
                self.assertEqual(asm.main([src, '--list', os.path.join(d, 'nowhere', 'o.lst')]), 1)
                for bad in ('10000H', '0xZZ', '65536'):
                    with self.assertRaises(SystemExit):
                        asm.main([src, '--entry', bad])
            self.assertIn('not printable ASCII', err.getvalue())
            self.assertIn('past 0FFFFH', err.getvalue())


def edtasm_file(lines, name='SAMPLE'):
    """Bytes as the Editor/Assembler saved them (Prentice Hall p.156-157)."""
    out = bytearray(b'\xd3' + name.ljust(6).encode())
    for n, text in lines:
        out += bytes(0x80 | ord(c) for c in '%05d' % n) + b' ' + text.encode('latin-1') + b'\r'
    return bytes(out) + b'\x1a'


class TestEditorAssemblerFiles(unittest.TestCase):
    """read_source: the Editor's own file format (ruled with the 2026-09-30
    audit; 52 of the corpus's 84 distinct sources) decodes to the text
    the assembler reads, and plain text passes through."""

    LINES = [(100, 'START\tLD\tHL,3C00H'), (110, '\tLD\t(HL),41H'), (120, '\tRET'),
             (130, '\tEND\tSTART')]

    def test_a_native_file_decodes_and_assembles(self):
        data = edtasm_file(self.LINES, 'HELLO')
        self.assertEqual(data[:7], b'\xd3HELLO ')
        self.assertEqual(data[7:12], b'\xb0\xb0\xb1\xb0\xb0')       # bit 7 on the digits
        text, name = asm.read_source(data)
        self.assertEqual(name, 'HELLO')
        self.assertEqual(text, '00100 START\tLD\tHL,3C00H\n00110 \tLD\t(HL),41H\n'
                               '00120 \tRET\n00130 \tEND\tSTART\n')
        r = one(text, org=0x7000)
        self.assertEqual(r.segments, [(0x7000, bytes.fromhex('21003c' '3641' 'c9'))])
        self.assertEqual(r.entry, 0x7000)

    def test_without_the_header_and_with_a_tab_after_the_number(self):
        data = edtasm_file(self.LINES)[7:]
        self.assertEqual(asm.read_source(data)[1], None)
        self.assertEqual(asm.read_source(data)[0].count('\n'), 4)
        tabbed = data.replace(b'\xb0 ', b'\xb0\t')                   # TBBS's MINIHOST/SRC
        self.assertEqual(asm.read_source(tabbed), asm.read_source(data))

    def test_a_dropped_bit_in_a_line_number_reads_as_zero(self):
        data = edtasm_file(self.LINES).replace(b'\xb0\xb0\xb1\xb1\xb0', b'\xb0\xb0\x91\xb1\xb0')
        self.assertIn('\n00010 \tLD\t(HL),41H\n', asm.read_source(data)[0])
        self.assertEqual(one(asm.read_source(data)[0], org=0).size, 6)

    def test_a_record_without_a_line_number_is_an_error_naming_the_byte(self):
        data = edtasm_file(self.LINES)
        first = edtasm_file(self.LINES[:1])[:-1]                     # header and one record
        with self.assertRaisesRegex(ValueError, 'at byte %d' % len(first)):
            asm.read_source(first + b'xx\r' + data[len(first):])
        # the EOF byte ends the file; bytes after it are not read
        self.assertEqual(asm.read_source(data + b'junk')[0].count('\n'), 4)

    def test_text_passes_through(self):
        self.assertEqual(asm.read_source(b'  ORG 0\n  NOP\n'), ('  ORG 0\n  NOP\n', None))
        self.assertEqual(asm.read_source(b'\xd3'), ('\xd3', None))
        self.assertEqual(asm.read_source(b''), ('', None))

    def test_the_command_line_reads_one_and_takes_its_name(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, 'anything.src')
            with open(src, 'wb') as f:
                f.write(edtasm_file([(90, '\tORG\t7000H')] + self.LINES, 'HELLO'))
            out = os.path.join(d, 'o.cmd')
            with redirect_stderr(io.StringIO()):
                self.assertEqual(asm.main([src, '-o', out]), 0)
            with open(out, 'rb') as f:
                self.assertEqual(f.read()[:7], b'\x05\x05HELLO')
            with redirect_stderr(io.StringIO()):
                self.assertEqual(asm.main([src, '-o', out, '--name', 'MINE']), 0)
            with open(out, 'rb') as f:
                self.assertEqual(f.read()[:6], b'\x05\x04MINE')


CORPUS = os.path.join(ROOT, 'corpus', 'programs')

# Period sources beside the object their author built from them:
# the one oracle for the assembler that is not this project's own
# reading of the books.  Measured 2026-10-16 over every source in the
# corpus, loose or inside the archive's zips (1,159 distinct, by SHA-1),
# against every load module in the same zip or directory: these 97 come
# out IMAGE-identical (every byte at every address, no byte more or
# less: so DEFS space is absent on both sides; TBBS's MINIHOST
# relies on an unterminated DEFM running to the end of its line).  Not
# byte-identical files: the period objects differ among themselves in
# record size (128 or 256), in sector padding after the transfer record
# and in whether a DOS added a name record, and nine (ene, multsrch,
# GRAPHIC among them) carry the transfer address 0 of an END with no
# operand, where this assembler's documented fallback is the first ORG.
# A place is a path under corpus/programs, or 'ZIP :: MEMBER'.  Of the
# loose pairs pinned 2026-10-15 that do not match: SCHED differs in one
# operand byte (LD DE,INTER: the object was built from a slightly
# different source), quaver1 and INVASION.SRC (the [BAS] copy) from
# other versions of their sources, FRAMER's object is damaged (record
# type BEH), hrg.asm holds NUL bytes inside lines (multied.asm's object
# holds another version of its line 4).
PAIRS = [
    ('LargeCollection/Display Directories by Password (19xx)(Author Unknown)[BAS]/dirpw.asm',
     'LargeCollection/Display Directories by Password (19xx)(Author Unknown)[BAS]/dirpw.cmd'),
    ('LargeCollection/Gin Rummy (1979)(Robert Sturmer)[a][BAS]/view.src',
     'LargeCollection/Gin Rummy (1979)(Robert Sturmer)[a][BAS]/view.cim'),
    ('LargeCollection/Invasion Orion v3.0 (1979)(Automated Simulations)[a][BAS]/invasion.src',
     'LargeCollection/Invasion Orion v3.0 (1979)(Automated Simulations)[a][BAS]/invasion.cmd'),
    ('LargeCollection/Mini-BBS v2.01 (19xx)(Mike Bernstein-Kandy Shack)[BAS]/minihost.asm',
     'LargeCollection/Mini-BBS v2.01 (19xx)(Mike Bernstein-Kandy Shack)[BAS]/minihost.cmd'),
    ('LargeCollection/Playing God with Life v1.9.3 (1979)(Dennis Bathory-Kitsz)[BAS]/LIFE9.SRC',
     'LargeCollection/Playing God with Life v1.9.3 (1979)(Dennis Bathory-Kitsz)[BAS]/LIFE9.CMD'),
    ('LargeCollection/Printer Driver for MX-FX-RX-80 (19xx)(Author Unknown)(De)[BAS]/drutreib.asm',
     'LargeCollection/Printer Driver for MX-FX-RX-80 (19xx)(Author Unknown)(De)[BAS]/drutreib.cmd'),
    ('LargeCollection/TBBS v3.0 (19xx)(Author Unknown)[BAS]/MINIHOST.SRC',
     'LargeCollection/TBBS v3.0 (19xx)(Author Unknown)[BAS]/MINIHOST.CMD'),
    ('LargeCollection/TRS3Link (19xx)(G Rahman)(Nl)[BAS]/ene.src',
     'LargeCollection/TRS3Link (19xx)(G Rahman)(Nl)[BAS]/ene.cmd'),
    ('LargeCollection/Window of TRS-Times (19xx)(Author Unknown)[BAS]/window.src',
     'LargeCollection/Window of TRS-Times (19xx)(Author Unknown)[BAS]/window.bin'),
    ('LargeCollection/Zone Display Program (1980)(Author Unknown)[BAS]/zdsply.src',
     'LargeCollection/Zone Display Program (1980)(Author Unknown)[BAS]/zdsply16.cmd'),
    ('Model1/Disk Sort Merge v2.0 (1979)(Racet Computers)[CMD]/wipe.asm',
     'Model1/Disk Sort Merge v2.0 (1979)(Racet Computers)[CMD]/wipe.cmd'),
    ('Model1/Fast Screen Print Program (19xx)(Serge Y Calmettes)[CMD]/scrprt.src',
     'Model1/Fast Screen Print Program (19xx)(Serge Y Calmettes)[CMD]/scrprt.cmd'),
    ('Model1/Multikey Editor v1.1 (19xx)(J Szajman)[CMD]/mult.asm',
     'Model1/Multikey Editor v1.1 (19xx)(J Szajman)[CMD]/mult.cmd'),
    ('Model1/Multikey Editor v1.1 (19xx)(J Szajman)[CMD]/multsrch.asm',
     'Model1/Multikey Editor v1.1 (19xx)(J Szajman)[CMD]/multsrch.cmd'),
    ('Model1/PowerDRAW v1.0 (1981)(Kim Watt)[CMD]/MERGE.ASM',
     'Model1/PowerDRAW v1.0 (1981)(Kim Watt)[CMD]/PMERGE.CMD'),
    ('Model1/PowerDRAW v1.0 (1981)(Kim Watt)[CMD]/PLAY.ASM',
     'Model1/PowerDRAW v1.0 (1981)(Kim Watt)[CMD]/PLAY.CMD'),
    ('Model1/Quaver (19xx)(Dennis Bathory-Kitsz)[a][CMD]/quaver7.asm',
     'Model1/Quaver (19xx)(Dennis Bathory-Kitsz)[a][CMD]/music7.bin'),
    ('Model1/Quaver Music Compiler (1981)(Dennis Bathory-Kitsz)[ASM]/quaver2.asm',
     'Model1/Quaver Music Compiler (1981)(Dennis Bathory-Kitsz)[ASM]/quaver2.cmd'),
    ('Model1/Title Graphics (19xx)(Author Unknown)[CMD]/GRAPHIC.SRC',
     'Model1/Title Graphics (19xx)(Author Unknown)[CMD]/GRAPHIC.CMD'),
    ('TRS-80 Model I/Various/CP-M Hardware and Software Conversion (19xx)(Author Unknown)[CMD].zip :: cpmbios.asm',
     'TRS-80 Model I/Various/CP-M Hardware and Software Conversion (19xx)(Author Unknown)[CMD].zip :: cpmbios.cmd'),
    ('TRS-80 Model I/Various/Convert Binary Number to 1s and 0s (1983)(Mel Patrick)[CMD].zip :: convbin.asm',
     'TRS-80 Model I/Various/Convert Binary Number to 1s and 0s (1983)(Mel Patrick)[CMD].zip :: convbin.cmd'),
    ('TRS-80 Model I/Various/Convert Upper Case to Lower Case (1986)(Rod Stevenson)[CMD].zip :: ULCNVRT.ASM',
     'TRS-80 Model I/Various/Convert Upper Case to Lower Case (1986)(Rod Stevenson)[CMD].zip :: ULCNVRT.CMD'),
    ('TRS-80 Model I/Various/DOSPlus II Misc Source files (19xx)(Kim Watt)[SRC][Partial].zip :: RANDOM.ASM',
     'TRS-80 Model I/Various/DOSPlus II Misc Source files (19xx)(Kim Watt)[SRC][Partial].zip :: RANDOM.CMD'),
    ('TRS-80 Model I/Various/DOSPlus v3.5 Sort Routine for Use With Other DOSes (19xx)(Author Unknown)[SRC].zip :: o.asm',
     'TRS-80 Model I/Various/DOSPlus v3.5 Sort Routine for Use With Other DOSes (19xx)(Author Unknown)[SRC].zip :: oo.cim'),
    ('TRS-80 Model I/Various/Dir Slot (19xx)(Joachim Kelterbaum)[CMD].zip :: dirslot.asm',
     'TRS-80 Model I/Various/Dir Slot (19xx)(Joachim Kelterbaum)[CMD].zip :: dirslot.cmd'),
    ('TRS-80 Model I/Various/Directory Cataloge Program (1983)(Mel Patrick)[CMD].zip :: diskcat.asm',
     'TRS-80 Model I/Various/Directory Cataloge Program (1983)(Mel Patrick)[CMD].zip :: diskcat.cmd'),
    ('TRS-80 Model I/Various/Disable POKE and SYSTEM (1983)(Nick Andrew)[CMD].zip :: disabl.edt',
     'TRS-80 Model I/Various/Disable POKE and SYSTEM (1983)(Nick Andrew)[CMD].zip :: disabl.cmd'),
    ('TRS-80 Model I/Various/Disk Modification Utility for LDOS v1.0 (1982)(Kim Watt)[CMD].zip :: pmodldos.asm',
     'TRS-80 Model I/Various/Disk Modification Utility for LDOS v1.0 (1982)(Kim Watt)[CMD].zip :: pmod1a.cmd'),
    ('TRS-80 Model I/Various/Disk Route v84.07.19 (1984)(Arne Rohde)[CMD].zip :: dr.asm',
     'TRS-80 Model I/Various/Disk Route v84.07.19 (1984)(Arne Rohde)[CMD].zip :: dr.cmd'),
    ('TRS-80 Model I/Various/Diskcomp (19xx)(Jerry Vabulas)[CMD].zip :: diskcomp.asm',
     'TRS-80 Model I/Various/Diskcomp (19xx)(Jerry Vabulas)[CMD].zip :: diskcomp.cmd'),
    ('TRS-80 Model I/Various/Diskette Label Maker (19xx)(Timothy E Sewell)[CMD][DMP 200].zip :: label200.src',
     'TRS-80 Model I/Various/Diskette Label Maker (19xx)(Timothy E Sewell)[CMD][DMP 200].zip :: label200.cmd'),
    ('TRS-80 Model I/Various/Display TRSDOS Directory in NEWDOS-80 (19xx)(Author Unknown)[CMD].zip :: TRSDIR.ASM',
     'TRS-80 Model I/Various/Display TRSDOS Directory in NEWDOS-80 (19xx)(Author Unknown)[CMD].zip :: TRSDIR.CMD'),
    ('TRS-80 Model I/Various/Display and Sort Diskette Catalogs (1983)(Mel Patrick)[CMD].zip :: ndcat.asm',
     'TRS-80 Model I/Various/Display and Sort Diskette Catalogs (1983)(Mel Patrick)[CMD].zip :: ndcat.cmd'),
    ('TRS-80 Model I/Various/Error Finder v2.2 (19xx)(Mike Brotherton)[CMD].zip :: where.asm',
     'TRS-80 Model I/Various/Error Finder v2.2 (19xx)(Mike Brotherton)[CMD].zip :: where.cmd'),
    ('TRS-80 Model I/Various/File Transfer Utility (19xx)(Kim Watt)[a2][CMD].zip :: S2.ASM',
     'TRS-80 Model I/Various/File Transfer Utility (19xx)(Kim Watt)[a2][CMD].zip :: S2.CMD'),
    ('TRS-80 Model I/Various/Filter Collection (19xx)(Misosys Inc)[FLT].zip :: REMOVE.ASM',
     'TRS-80 Model I/Various/Filter Collection (19xx)(Misosys Inc)[FLT].zip :: REMOVE.CMD'),
    ('TRS-80 Model I/Various/Flight Simulator T80-FS1 Loader (19xx)(Author Unknown)[CMD].zip :: loader.src',
     'TRS-80 Model I/Various/Flight Simulator T80-FS1 Loader (19xx)(Author Unknown)[CMD].zip :: loader.cmd'),
    ('TRS-80 Model I/Various/Genie RAM Spooler (19xx)(Author Unknown)(De)[ASM].zip :: genspool.asm',
     'TRS-80 Model I/Various/Spooler (19xx)(Author Unknown)(De)[CMD].zip :: spooler1.cmd'),
    ('TRS-80 Model I/Various/Hayes Modem ASCII Commands from DOS (19xx)(Mel Patrick)[CMD].zip :: hayes.src',
     'TRS-80 Model I/Various/Hayes Modem ASCII Commands from DOS (19xx)(Mel Patrick)[CMD].zip :: hayes.cmd'),
    ('TRS-80 Model I/Various/Hex and Decimal Calculator (1983)(Mel Patrick)[CMD].zip :: hexcal.asm',
     'TRS-80 Model I/Various/Hex and Decimal Calculator (1983)(Mel Patrick)[CMD].zip :: hexcal.cmd'),
    ('TRS-80 Model I/Various/Host-80 (1983)(Mel Patrick)[CMD].zip :: host80.src',
     'TRS-80 Model I/Various/Host-80 (1983)(Mel Patrick)[CMD].zip :: host80.cmd'),
    ('TRS-80 Model I/Various/Interrupt (19xx)(Joachim Kelterbaum)[CMD].zip :: interrpt.asm',
     'TRS-80 Model I/Various/Interrupt (19xx)(Joachim Kelterbaum)[CMD].zip :: interrpt.cmd'),
    ('TRS-80 Model I/Various/KB Audio (19xx)(Author Unknown)[CMD].zip :: kbaudio.src',
     'TRS-80 Model I/Various/KB Audio (19xx)(Author Unknown)[CMD].zip :: kbaudio.cmd'),
    ('TRS-80 Model I/Various/LISP v5.0 (1986)(Mike Stump)[CMD].zip :: LISP.SRC',
     'TRS-80 Model I/Various/LISP v5.0 (1986)(Mike Stump)[CMD].zip :: LISP.CMD'),
    ('TRS-80 Model I/Various/Level III G2 Cassette Basic (1979)(GRT-Microsoft)[CMD].zip :: l3help.src',
     'TRS-80 Model I/Various/Level III G2 Cassette Basic (1979)(GRT-Microsoft)[CMD].zip :: l3help.cmd'),
    ('TRS-80 Model I/Various/Macro-Key v2.0 Removal Utility (1984)(Mel Patrick)[CMD].zip :: unmacro.asm',
     'TRS-80 Model I/Various/Macro-Key v2.0 Removal Utility (1984)(Mel Patrick)[CMD].zip :: unmacro.cmd'),
    ('TRS-80 Model I/Various/Make-80 v1.2 (1980)(Kim Watt)[CMD].zip :: MAKE80.ASM',
     'TRS-80 Model I/Various/Make-80 v1.2 (1980)(Kim Watt)[CMD].zip :: MAKE80.CMD'),
    ('TRS-80 Model I/Various/Marquee for Video Screen (19xx)(Author Unknown)[CMD].zip :: marq.asm',
     'TRS-80 Model I/Various/Marquee for Video Screen (19xx)(Author Unknown)[CMD].zip :: marq.cmd'),
    ('TRS-80 Model I/Various/Morse Code Generator (1983)(Mel Patrick)[CMD].zip :: morse.asm',
     'TRS-80 Model I/Various/Morse Code Generator (1983)(Mel Patrick)[CMD].zip :: morse.cmd'),
    ('TRS-80 Model I/Various/Music (19xx)(Author Unknown)[CMD].zip :: music.src',
     'TRS-80 Model I/Various/Music (19xx)(Author Unknown)[CMD].zip :: MUSIC.CMD'),
    ('TRS-80 Model I/Various/Organ-Synthesizer (19xx)(Kim Watt-Breeze Computing)[CMD].zip :: organkw.src',
     'TRS-80 Model I/Various/Organ-Synthesizer (19xx)(Kim Watt-Breeze Computing)[CMD].zip :: organkw1.cmd'),
    ('TRS-80 Model I/Various/PClear LDOS Disk Clear Utility v1.0 (1982)(Kim Watt-Breeze Computing)[CMD].zip :: pclear1a.asm',
     'TRS-80 Model I/Various/PClear LDOS Disk Clear Utility v1.0 (1982)(Kim Watt-Breeze Computing)[CMD].zip :: pclear1a.cmd'),
    ('TRS-80 Model I/Various/PClear LDOS Disk Clear Utility v2.1 (1982)(Kim Watt-Breeze Computing)[CMD].zip :: pclear21.asm',
     'TRS-80 Model I/Various/PClear LDOS Disk Clear Utility v2.1 (1982)(Kim Watt-Breeze Computing)[CMD].zip :: pclear21.cmd'),
    ('TRS-80 Model I/Various/PDrive Menu for NEWDOS-80 (1991)(Lance Wolstrup)[CMD].zip :: pdm.src',
     'TRS-80 Model I/Various/PDrive Menu for NEWDOS-80 (1991)(Lance Wolstrup)[CMD].zip :: pdm.cmd'),
    ('TRS-80 Model I/Various/Peek at the HASH Codes (19xx)(Nick Andrew)[CMD].zip :: peekhash.edt',
     'TRS-80 Model I/Various/Peek at the HASH Codes (19xx)(Nick Andrew)[CMD].zip :: peekhash.cmd'),
    ('TRS-80 Model I/Various/Printer Controls from DOS Line (19xx)(Author Unknown)[CMD].zip :: P.ASM',
     'TRS-80 Model I/Various/Printer Controls from DOS Line (19xx)(Author Unknown)[CMD].zip :: P.CMD'),
    ('TRS-80 Model I/Various/Printer Graphics (19xx)(Author Unknown)[CMD].zip :: GRAPH.SRC',
     'TRS-80 Model I/Various/Printer Graphics (19xx)(Author Unknown)[CMD].zip :: GRAPH.CMD'),
    ('TRS-80 Model I/Various/Printer Oriented DIR v1.2 (19xx)(Nick Andrew)[CMD].zip :: pdir12.asm',
     'TRS-80 Model I/Various/Printer Oriented DIR v1.2 (19xx)(Nick Andrew)[CMD].zip :: pdir12.cmd'),
    ('TRS-80 Model I/Various/Printer Oriented DIR v1.4 (19xx)(Nick Andrew)[CMD].zip :: pdir14.asm',
     'TRS-80 Model I/Various/Printer Oriented DIR v1.4 (19xx)(Nick Andrew)[CMD].zip :: pdir14.cmd'),
    ('TRS-80 Model I/Various/Printer Setup (19xx)(Dennis Bathory-Kitsz)[CMD].zip :: prints2.asm',
     'TRS-80 Model I/Various/Printer Setup (19xx)(Dennis Bathory-Kitsz)[CMD].zip :: prints2.cmd'),
    ('TRS-80 Model I/Various/Printer Setup (19xx)(Dennis Bathory-Kitsz)[CMD].zip :: prints3.asm',
     'TRS-80 Model I/Various/Printer Setup (19xx)(Dennis Bathory-Kitsz)[CMD].zip :: prints3.cmd'),
    ('TRS-80 Model I/Various/Printer Setup (19xx)(Dennis Bathory-Kitsz)[CMD].zip :: prints4.asm',
     'TRS-80 Model I/Various/Printer Setup (19xx)(Dennis Bathory-Kitsz)[CMD].zip :: prints4.cmd'),
    ('TRS-80 Model I/Various/Printer Setup (19xx)(Dennis Bathory-Kitsz)[CMD].zip :: printset.asm',
     'TRS-80 Model I/Various/Printer Setup (19xx)(Dennis Bathory-Kitsz)[CMD].zip :: printset.cmd'),
    ('TRS-80 Model I/Various/Printer Setup v1.6E (19xx)(Dan Shelby)[CMD].zip :: prnt.src',
     'TRS-80 Model I/Various/Printer Setup v1.6E (19xx)(Dan Shelby)[CMD].zip :: prnt.cmd'),
    ('TRS-80 Model I/Various/Quaver (19xx)(Dennis Bathory-Kitsz)[a2][CMD].zip :: quaver2.asm',
     'TRS-80 Model I/Various/Quaver (19xx)(Dennis Bathory-Kitsz)[a2][CMD].zip :: music4.bin'),
    ('TRS-80 Model I/Various/Quaver (19xx)(Dennis Bathory-Kitsz)[a2][CMD].zip :: quaver4.asm',
     'TRS-80 Model I/Various/Quaver (19xx)(Dennis Bathory-Kitsz)[a2][CMD].zip :: music5.bin'),
    ('TRS-80 Model I/Various/Quick-Fix (19xx)(Kim Watt)[CMD].zip :: boot1.asm',
     'TRS-80 Model I/Various/Quick-Fix (19xx)(Kim Watt)[CMD].zip :: boot1.cmd'),
    ('TRS-80 Model I/Various/Quick-Fix (19xx)(Kim Watt)[CMD].zip :: boot2.asm',
     'TRS-80 Model I/Various/Quick-Fix (19xx)(Kim Watt)[CMD].zip :: boot2.cmd'),
    ('TRS-80 Model I/Various/Screen Dump to Disk File (19xx)(Ron A Zajac)[CMD].zip :: sd456.asm',
     'TRS-80 Model I/Various/Screen Dump to Disk File (19xx)(Ron A Zajac)[CMD].zip :: sd456.cmd'),
    ('TRS-80 Model I/Various/Skrewup RAM (19xx)(CC Morris)[CMD].zip :: skrewup.src',
     'TRS-80 Model I/Various/Skrewup RAM (19xx)(CC Morris)[CMD].zip :: skrewup.cmd'),
    ('TRS-80 Model I/Various/Smart Driver Host Program v1.0 (19xx)(Mel Patrick)[CMD].zip :: BYE.SRC',
     'TRS-80 Model I/Various/Smart Driver Host Program v1.0 (19xx)(Mel Patrick)[CMD].zip :: BYE.CMD'),
    ('TRS-80 Model I/Various/Smart Driver Host Program v1.0 (19xx)(Mel Patrick)[CMD].zip :: SMARTDVR.SRC',
     'TRS-80 Model I/Various/Smart Driver Host Program v1.0 (19xx)(Mel Patrick)[CMD].zip :: SMARTDVR.CMD'),
    ('TRS-80 Model I/Various/Sort Directory (1984)(Author Unknown)[CMD].zip :: sdir.asm',
     'TRS-80 Model I/Various/Sort Directory (1984)(Author Unknown)[CMD].zip :: sdir.cmd'),
    ('TRS-80 Model I/Various/Space Bomber (19xx)(Dale Chernak)[CMD].zip :: BOMBER.ASM',
     'TRS-80 Model I/Various/Space Bomber (19xx)(Dale Chernak)[CMD].zip :: BOMBER.CMD'),
    ('TRS-80 Model I/Various/Special Disk Copy III- I-III File Transfer Utility (19xx)(Kim Watt)[a][CMD].zip :: boot1s.asm',
     'TRS-80 Model I/Various/Special Disk Copy III- I-III File Transfer Utility (19xx)(Kim Watt)[a][CMD].zip :: boot1s.cmd'),
    ('TRS-80 Model I/Various/Special Disk Copy III- I-III File Transfer Utility (19xx)(Kim Watt)[a][CMD].zip :: mod1fix.asm',
     'TRS-80 Model I/Various/Special Disk Copy III- I-III File Transfer Utility (19xx)(Kim Watt)[a][CMD].zip :: mod1fix.cmd'),
    ('TRS-80 Model I/Various/Spooler (1981)(John J Schultz)[CMD].zip :: datadump.asm',
     'TRS-80 Model I/Various/Spooler (1981)(John J Schultz)[CMD].zip :: datadump.cmd'),
    ('TRS-80 Model I/Various/Spooler (1981)(John J Schultz)[CMD].zip :: gprint.asm',
     'TRS-80 Model I/Various/Spooler (1981)(John J Schultz)[CMD].zip :: gprint.cmd'),
    ('TRS-80 Model I/Various/Super Script (1980)(Acorn Software)[CMD].zip :: lc.edt',
     'TRS-80 Model I/Various/Super Script (1980)(Acorn Software)[CMD].zip :: lc.cmd'),
    ('TRS-80 Model I/Various/Super Utility + Boot Routines (19xx)(Kim Watt)[SRC].zip :: BOOT1B.ASM',
     'TRS-80 Model I/Various/Super Utility + Boot Routines (19xx)(Kim Watt)[SRC].zip :: BOOT1B.CMD'),
    ('TRS-80 Model I/Various/Super Utility + Boot Routines (19xx)(Kim Watt)[SRC].zip :: BOOT1N.ASM',
     'TRS-80 Model I/Various/Super Utility + Boot Routines (19xx)(Kim Watt)[SRC].zip :: BOOT1N.CMD'),
    ('TRS-80 Model I/Various/Super Utility + Boot Routines (19xx)(Kim Watt)[SRC].zip :: BOOT3A.ASM',
     'TRS-80 Model I/Various/Super Utility + Boot Routines (19xx)(Kim Watt)[SRC].zip :: BOOT3A.CMD'),
    ('TRS-80 Model I/Various/Super Utility + Boot Routines (19xx)(Kim Watt)[SRC].zip :: BOOT3B.ASM',
     'TRS-80 Model I/Various/Super Utility + Boot Routines (19xx)(Kim Watt)[SRC].zip :: BOOT3B.CMD'),
    ('TRS-80 Model I/Various/Super Utility + Boot Routines (19xx)(Kim Watt)[SRC].zip :: BOOT3N.ASM',
     'TRS-80 Model I/Various/Super Utility + Boot Routines (19xx)(Kim Watt)[SRC].zip :: BOOT3N.CMD'),
    ('TRS-80 Model I/Various/Super Utility + Source Code (19xx)(Kim Watt)[a][SRC].zip :: sucopy.asm',
     'TRS-80 Model I/Various/Super Utility + Source Code (19xx)(Kim Watt)[a][SRC].zip :: sucopy.cmd'),
    ('TRS-80 Model I/Various/Super Utility + Source Code (19xx)(Kim Watt)[a][SRC].zip :: uk.asm',
     'TRS-80 Model I/Various/Super Utility + Source Code (19xx)(Kim Watt)[a][SRC].zip :: uk.cmd'),
    ('TRS-80 Model I/Various/Super Utility + Source Code (19xx)(Kim Watt)[a][SRC].zip :: uk3.asm',
     'TRS-80 Model I/Various/Super Utility + Source Code (19xx)(Kim Watt)[a][SRC].zip :: uk3.cmd'),
    ('TRS-80 Model I/Various/SuperCop (19xx)(Dan Robinson)[CMD].zip :: supercp2.asm',
     'TRS-80 Model I/Various/SuperCop (19xx)(Dan Robinson)[CMD].zip :: supercp2.cmd'),
    ('TRS-80 Model I/Various/Terminal Program v1.4 (19xx)(Nick Andrew)[CMD].zip :: term14.asm',
     'TRS-80 Model I/Various/Terminal Program v1.4 (19xx)(Nick Andrew)[CMD].zip :: trmprg14.cmd'),
    ('TRS-80 Model I/Various/Tic Tac Toe (1985)(Lance Wolstrup)[CMD].zip :: ttt.src',
     'TRS-80 Model I/Various/Tic Tac Toe (1985)(Lance Wolstrup)[CMD].zip :: ttt.cmd'),
    ('TRS-80 Model I/Various/Time & Date Saver v1.0 (19xx)(Michael Keller)[CMD].zip :: TMEDAT1.SRC',
     'TRS-80 Model I/Various/Time & Date Saver v1.0 (19xx)(Michael Keller)[CMD].zip :: TMEDAT1.CMD'),
    ('TRS-80 Model I/Various/Trace Function (1985)(Greg Small)[CMD].zip :: trace.asm',
     'TRS-80 Model I/Various/Trace Function (1985)(Greg Small)[CMD].zip :: trace.cmd'),
    ('TRS-80 Model I/Various/VHF Data Link Program (19xx)(W4UCH)[ASM].zip :: vhfdlp.asm',
     'TRS-80 Model I/Various/VHF Data Link Program (19xx)(W4UCH)[ASM].zip :: vhfdlp.cmd'),
    ('TRS-80 Model I/Various/Verfile (1983)(Laurie Shields)[CMD].zip :: verfile.asm',
     'TRS-80 Model I/Various/Verfile (1983)(Laurie Shields)[CMD].zip :: verfile.cmd'),
    ('TRS-80 Model I/Various/View ASCII File (1983)(Mel Patrick)[CMD].zip :: ascfmt.asm',
     'TRS-80 Model I/Various/View ASCII File (1983)(Mel Patrick)[CMD].zip :: ascfmt.cmd'),
    ('TRS-80 Model I/Various/XModem v1.20 (1984)(Nick Andrew)[CMD].zip :: xmf.asm',
     'TRS-80 Model I/Various/XModem v1.20 (1984)(Nick Andrew)[CMD].zip :: xmf.cmd'),
    ('TRS-80 Model I/Various/Zap Debug (1983)(Tony Domigan)[CMD].zip :: zapdebug.asm',
     'TRS-80 Model I/Various/Zap Debug (1983)(Tony Domigan)[CMD].zip :: zapdebug.cmd'),
]

# Kim Watt's Super Utility patch files have no ORG (the address was given
# to the assembler) and no END: assembled at the object's own first
# address.  uk.asm's object carries the transfer address of the program
# it patches, which nothing in the file names.
ORG_GIVEN = {'uk.asm': 0x4200, 'uk3.asm': 0x4300}
NO_ENTRY = {'uk.asm'}

# The one pair whose bytes depend on the order of evaluation: Misosys's
# REMOVE/ASM rounds up to a page with `ORG $<-8+1<8`, and the object holds
# the left-to-right value (EDTASM's order), not the precedence one.
WARNED = {'REMOVE.ASM': 1}


def corpus_bytes(place):
    import zipfile
    if ' :: ' in place:
        z, member = place.split(' :: ', 1)
        with zipfile.ZipFile(os.path.join(CORPUS, z)) as zf:
            return zf.read(member)
    with open(os.path.join(CORPUS, place), 'rb') as f:
        return f.read()


def image(segments):
    m = {}
    for org, data in segments:
        for i, b in enumerate(data):
            m[org + i] = b
    return m


@unittest.skipUnless(os.path.isdir(CORPUS), 'the corpus is not linked beside this repo')
class TestPeriodObjects(unittest.TestCase):
    def test_every_pair_assembles_to_its_period_object(self):
        from z80.load import load_cmd
        self.assertEqual(len(PAIRS), 97)
        for src, obj in PAIRS:
            stem = src.replace(' :: ', '/').rsplit('/', 1)[1]
            with self.subTest(src):
                text, name = asm.read_source(corpus_bytes(src))
                theirs, entry, _ = load_cmd(corpus_bytes(obj))
                r = assemble(text, org=ORG_GIVEN.get(stem))
                self.assertEqual(r.errors, [])
                self.assertEqual(len(r.warnings), WARNED.get(stem, 0))
                self.assertEqual(image(r.segments), image(theirs))
                if entry and stem not in NO_ENTRY:
                    self.assertEqual(r.entry, entry)

    def test_the_left_to_right_order_is_the_one_the_period_object_holds(self):
        src = [s for s, _ in PAIRS if s.endswith(':: REMOVE.ASM')][0]
        text = asm.read_source(corpus_bytes(src))[0]
        warning = assemble(text).warnings[0][1]
        self.assertIn('is 22016 left to right', warning)
        self.assertIn('341 with operator precedence', warning)
        self.assertNotEqual(image(assemble(text, precedence=True).segments),
                            image(assemble(text).segments))

    def test_the_period_objects_skip_their_defs_space(self):
        """The harm case of the DEFS fill held against the oracle: the four sources
        the audit named reserve 256, 319, 64 and 290 bytes, and their
        objects hold none of them."""
        from z80.load import load_cmd
        for rel, reserved in (('LargeCollection/Display Directories by Password (19xx)'
                               '(Author Unknown)[BAS]/dirpw.asm', 256),
                              ('LargeCollection/Mini-BBS v2.01 (19xx)(Mike Bernstein-Kandy Shack)'
                               '[BAS]/minihost.asm', 319)):
            path = os.path.join(CORPUS, rel)
            with open(path, 'rb') as f:
                r = assemble(asm.read_source(f.read())[0])
            held = sum(s.size for s in r.stmts if s.op in ('DEFS', 'DS') and s.items is None)
            self.assertEqual(held, reserved, rel)
            top = max(s.pc + s.size for s in r.stmts if s.size)
            low = min(s.pc for s in r.stmts if s.size)
            self.assertEqual(r.size, top - low - held, rel)


class TestRelativeJumpsAcrossTheTop(unittest.TestCase):
    """The PC wraps at 64K, so a JR over the top is an ordinary short jump.

    The displacement was `target - (pc + length)` with no wrap, so a JR
    from FFFEH to 0002H computed -65534 and was refused -- although the
    disassembler wraps its own target and hands back exactly that line, so
    the two tools disagreed about a listing (the 2026-09-19 audit).
    """

    def bytes_of(self, org, ins):
        r = assemble(' ORG %d\n %s\n' % (org, ins))
        self.assertEqual(r.errors, [], '%04X %s' % (org, ins))
        return r.segments[0][1]

    def test_forward_across_the_top(self):
        self.assertEqual(self.bytes_of(0xFFFE, 'JR 0002H'), bytes([0x18, 0x02]))

    def test_backward_across_the_bottom(self):
        self.assertEqual(self.bytes_of(0x0002, 'JR 0FFFFH'), bytes([0x18, 0xFB]))
        self.assertEqual(self.bytes_of(0x0000, 'JR 0FFF0H'), bytes([0x18, 0xEE]))

    def test_a_disassembled_wrap_assembles_back(self):
        """What disasm prints for the wrap is what asm takes."""
        raw = bytes([0x18, 0x02])
        for base in (0xFFFE, 0xFF00, 0x0000):
            ins = disassemble(raw, base=base)[0]
            r = assemble(' ORG %d\n %s\n' % (ins.addr, ins.text))
            self.assertEqual(r.errors, [], '%04X %s' % (base, ins.text))
            self.assertEqual(r.segments[0][1], raw, '%04X %s' % (base, ins.text))

    def test_a_jump_that_really_is_too_far_is_still_refused(self):
        r = assemble(' ORG 7D00H\n JR 7E00H\n')
        self.assertTrue(r.errors)
        # 7E00H from 7D02H, the address after the two-byte JR, is 254 --
        # just past the reach, and the message names the wrapped signed
        # displacement rather than a five-digit one
        self.assertIn('out of range: 254 bytes', r.errors[0][1])

    def test_the_far_side_of_the_wrap_is_also_refused(self):
        """Wrapping does not make every address reachable: 8000H away is
        -32768 either way round, and still too far."""
        r = assemble(' ORG 0\n JR 8000H\n')
        self.assertTrue(r.errors)
        self.assertIn('out of range', r.errors[0][1])


class TestDefwTakesWords(unittest.TestCase):
    """DEFW's items are words, quoted characters included.

    This module's own rule is that a quoted one or two characters is a
    number -- 'AB' is 4142H.  DEFW took both as strings instead, so
    DEFW 'AB' emitted 41 42 where 4142H stored as a word is 42 41, and
    DEFW "A" emitted a single byte, which is not a word at all (the
    2026-09-19 audit).
    """

    def bytes_of(self, src):
        r = assemble(' ORG 0\n' + src + '\n')
        self.assertEqual(r.errors, [], src)
        self.assertEqual(len(r.segments), 1, src)
        return r.segments[0][1]

    def test_two_characters_are_one_word_low_byte_first(self):
        self.assertEqual(self.bytes_of(" DEFW 'AB'"), bytes([0x42, 0x41]))
        self.assertEqual(self.bytes_of(" DEFW 'AB'"), self.bytes_of(' DEFW 4142H'))

    def test_one_character_is_a_whole_word(self):
        self.assertEqual(self.bytes_of(" DEFW 'A'"), bytes([0x41, 0x00]))
        self.assertEqual(self.bytes_of(' DEFW "A"'), bytes([0x41, 0x00]))

    def test_several_items(self):
        self.assertEqual(self.bytes_of(" DEFW 'AB','CD',1"),
                         bytes([0x42, 0x41, 0x44, 0x43, 0x01, 0x00]))

    def test_longer_text_is_an_error_naming_defm(self):
        r = assemble(" ORG 0\n DEFW 'ABC'\n")
        self.assertTrue(r.errors)
        self.assertIn('DEFM', r.errors[0][1])

    def test_defb_and_defm_still_take_strings(self):
        self.assertEqual(self.bytes_of(" DEFB 'AB'"), b'AB')
        self.assertEqual(self.bytes_of(" DEFM 'ABC'"), b'ABC')
        self.assertEqual(self.bytes_of(" DEFB 'A'"), b'A')

    def test_pass_one_and_pass_two_agree_on_the_size(self):
        """A size the two passes disagree on is an internal error, so a
        label after the DEFW proves the sizing."""
        r = assemble(" ORG 0\n DEFW 'AB','C'\nAFTER EQU $\n DEFW AFTER\n")
        self.assertEqual(r.errors, [])
        self.assertEqual(r.segments[0][1], bytes([0x42, 0x41, 0x43, 0x00, 0x04, 0x00]))


if __name__ == '__main__':
    unittest.main()
