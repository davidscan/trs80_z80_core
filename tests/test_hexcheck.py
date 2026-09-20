"""tools/hexcheck.py: a damaged listing comes back, or says it could not.

The instrument is a round trip.  A program is assembled, printed as the
period assembler printed it -- address, object bytes, line number, source
-- and then damaged the way a scanner damages a page: the characters that
look alike are swapped, and the occasional one is dropped.  hexcheck reads
that back, and two things are asserted about what it says.

THE ONE THAT MATTERS: no line it accepts may have the wrong bytes.  A
wrong byte accepted silently is the failure this tool exists to prevent,
and it is worse than a line reported unresolved, so the test fails on a
single mismatch and only warns about how many were left unresolved.

THE OTHER: it has to actually resolve most of them, or it is an expensive
way to print the scan back.  The floor is a regression bar, not a claim.

The same round trip covers the third witness: the program is also printed
as the BASIC loader the books put beside a listing, DATA statements of the
same bytes in decimal, and that loader is damaged by the same scanner.
The first assertion holds with the DATA counted as a witness, and the
lines that were a reading of the object column alone mostly stop being
so.  What the DATA may never do is settle a line by itself, and there are
cases for that too.
"""
import io
import os
import random
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import hexcheck                                                 # noqa: E402
from z80 import asm                                             # noqa: E402

SOURCE = """\
VIDEO   EQU     3C00H
BUFLEN  EQU     16
;A LINE OF THE SCREEN, TAKEN APART AND PUT BACK
        ORG     7D00H
START   LD      HL,VIDEO+64
        LD      DE,VIDEO
        LD      BC,1024-64
        LDIR
        LD      HL,VIDEO+960
        LD      A,' '
        LD      B,64
FILL    LD      (HL),A
        INC     HL
        DJNZ    FILL
        CALL    COUNT
        JR      NZ,FILL
        LD      A,(FLAG)
        OR      A
        JP      Z,DONE
        CP      BUFLEN
        JR      C,START
        PUSH    AF
        LD      IX,BUFFER
        LD      (IX+3),0FFH
        POP     AF
        RES     7,(IX+1)
COUNT   LD      A,(FLAG)
        INC     A
        LD      (FLAG),A
        RET
DONE    XOR     A
        LD      (FLAG),A
        RET
FLAG    DEFB    0
BUFFER  DEFS    16,0
MSG     DEFM    'READY'
        DEFW    START
        END     START
"""

def manual_page(res, listing):
    """A page in the shape the reference manuals print: the listing, the
    prose that introduces the loader, the loader with the page's own line
    numbers and its READ/POKE loop spread over a page break, and the DATA
    statement at the end -- plus the manual's habit of losing the space in
    'END START'."""
    image = b''.join(data for _, data in res.segments)
    listing = listing.replace('END     START', 'ENDSTART')
    return '\n'.join([
        'Listed below is an assembled program that clears a line of the',
        'display and counts the calls.', '', listing,
        'This routine can be POKEd into RAM and accessed as a USR routine,',
        'as follows.', '',
        '100 \' PROGRAM: USR', '110 \' POKE THE MACHINE PROGRAM INTO MEMORY',
        '150 POKE 16526,0: POKE 16527,125',
        '160 FOR X=32000 TO %d' % (32000 + len(image) - 1), '', '', '8-10', '',
        '## Page 105', '',
        '170     READ A', '180     POKE X,A', '190 NEXT X',
        '270 X=USR (0)', '300 \'',
        '310 \' ******* DATA IS DECIMAL CODE FOR HEX PROGRAM *******',
        '330 DATA %s' % ','.join(str(b) for b in image), '',
        'RUN the program.  An equivalent BASIC routine takes a long time',
        'by comparison!', ''])


# What a scanner does to a page, as the books show it: the shapes that
# collide, and the character it drops now and then.
CONFUSIONS = {
    '0': 'Oo@Q', '1': 'lI!|', '2': 'Zz', '3': 'S', '4': 'uH', '5': 'S$s',
    '6': 'Gb', '7': 'T?', '8': 'BR', '9': 'gq', 'A': 'aR', 'B': '8b',
    'C': 'c(G', 'D': 'DbO', 'E': 'eF', 'F': 'FPE', 'H': 'Hh4', 'I': 'iI1',
    'J': 'jI', 'L': 'Lu1', 'M': 'MN', 'N': 'Nn', 'O': 'O0Q', 'P': 'pF',
    'R': 'rA8', 'S': 's5', 'T': 't7', 'U': 'uV', 'V': 'vU', 'X': 'x',
    'Z': 'z2', ';': ':i#j', ',': '.', '-': '~', '(': 'C', ')': ')',
}


def render(res):
    """The listing as the assembler printed it: the three columns and the
    editor's line number."""
    out = []
    for i, s in enumerate(res.stmts):
        n = 100 + 10 * i
        text = s.text.strip()
        if s.op == 'EQU':
            out.append('%04X %05d %s' % (s.value & 0xFFFF, n, text))
        elif s.op is None and s.label is None:
            out.append('%05d %s' % (n, text))
        elif s.op in ('ORG', 'END'):
            out.append('%04X %05d %s' % (s.pc & 0xFFFF, n, text))
        else:
            out.append('%04X %s %05d %s'
                       % (s.pc & 0xFFFF, s.bytes.hex().upper(), n, text))
    return '\n'.join(out) + '\n'


def damage(text, rate, seed):
    """Scan the page badly but reproducibly."""
    rng = random.Random(seed)
    out = []
    for line in text.splitlines():
        chars = []
        for ch in line:
            if ch != ' ' and rng.random() < rate:
                if rng.random() < 0.08:
                    continue                            # the character is lost
                chars.append(rng.choice(CONFUSIONS.get(ch.upper(), ch)))
            else:
                chars.append(ch)
        out.append(''.join(chars))
    return '\n'.join(out) + '\n'


def truth(res):
    """{address: bytes} for every statement that emitted any."""
    return {s.pc & 0xFFFF: s.bytes for s in res.stmts if s.bytes}


def render_data(res, per_line=8, first=1000):
    """The same bytes as the books print them a second time: a BASIC loader
    whose DATA statements hold the image in decimal."""
    image = b''.join(data for _, data in res.segments)
    out = ['10 FOR I=0 TO %d: READ A: POKE 32000+I,A: NEXT' % (len(image) - 1),
           '20 X=USR(0)']
    for i in range(0, len(image), per_line):
        out.append('%d DATA %s' % (first + 10 * (i // per_line),
                                   ','.join(str(b) for b in image[i:i + per_line])))
    return '\n'.join(out) + '\n'


def check(text, data=True):
    blocks = hexcheck.find_blocks(text)
    streams = hexcheck.find_data(text) if data else []
    return [hexcheck.Block(b, 'test', streams).run() for b in blocks]


class HexCheck(unittest.TestCase):
    def setUp(self):
        self.res = asm.assemble(SOURCE)
        self.assertEqual(self.res.errors, [], 'the fixture must assemble')
        self.listing = render(self.res)
        self.truth = truth(self.res)

    def resolved(self, blocks, checked_only=False):
        """(right, wrong, unresolved) over every line that carries bytes.
        `checked_only` drops the lines hexcheck says it read off the object
        column alone: those are a reading of one column, reported as such
        line by line, and the test holds them to a lower bar."""
        right = wrong = unresolved = 0
        for b in blocks:
            for r in b.recs:
                if r.status == 'unresolved':
                    unresolved += 1
                elif r.bytes and r.addr is not None:
                    if checked_only and r.status == 'hexonly':
                        continue
                    if self.truth.get(r.addr) == r.bytes:
                        right += 1
                    else:
                        wrong += 1
        return right, wrong, unresolved

    def statuses(self, blocks):
        out = {}
        for b in blocks:
            for r in b.recs:
                out[r.status] = out.get(r.status, 0) + 1
        return out

    # -- the DATA statements as a third witness ------------------------------
    def test_the_data_statements_are_a_third_witness(self):
        """Both the listing and its loader scanned badly.  Nothing accepted on
        two witnesses may be wrong, the DATA now being one of them; and the
        lines that were a reading of the object column alone mostly become
        two-witness lines, because the decimal column vouches for them."""
        wrong_all = alone_with = alone_without = 0
        came = [0, 0]
        for seed in range(12):
            page = damage(self.listing + '\n' + render_data(self.res), 0.10, seed)
            with_data = check(page)
            without = check(page, data=False)
            right, wrong, unresolved = self.resolved(with_data, checked_only=True)
            wrong_all += wrong
            came[0] += right
            came[1] += right + unresolved
            alone_with += self.statuses(with_data).get('hexonly', 0)
            alone_without += self.statuses(without).get('hexonly', 0)
            for b in with_data:
                self.assertIsNotNone(b.stream, 'seed %d: the loader was not aligned' % seed)
        self.assertEqual(wrong_all, 0, 'a two-witness line had the wrong bytes')
        self.assertGreater(alone_without, 10, 'the fixture stopped exercising this')
        self.assertLess(alone_with, 0.5 * alone_without,
                        'the DATA left %d of %d object-column readings unvouched'
                        % (alone_with, alone_without))
        self.assertGreater(came[0] / float(came[1]), 0.80)

    def test_the_data_settles_a_hex_field_scanned_into_another_instruction(self):
        """3E20 scanned as 3820 -- a valid JR C -- with the source lightly
        damaged and the DATA printed.  Without the loader the line has one
        column against a source that cannot assemble; with it, the source as
        the page printed it agrees with the decimal bytes, and the hex column
        is what gets repaired."""
        line = "7D0E 3E20 00190 LD      A,' '"
        self.assertIn(line, self.listing, 'the fixture moved')
        listing = self.listing.replace(line, "7D0E 3820 00190         Lb      A,' '")
        (b,) = check(listing + '\n' + render_data(self.res))
        (r,) = [r for r in b.recs if r.addr == 0x7D0E]
        self.assertEqual(r.bytes, b'\x3e\x20')
        self.assertIn(r.status, ('hex', 'source'))
        self.assertEqual(b.verify(), [])

    def test_the_data_alone_cannot_settle_a_line_the_source_says_nothing_about(self):
        """Source destroyed, hex 3820, DATA 62,32: one column against another
        and no third.  The line is reported with both readings, not chosen."""
        (b,) = check(self.wrecked() + '\n' + render_data(self.res))
        (r,) = [r for r in b.recs if r.addr == 0x7D0E]
        self.assertEqual(r.status, 'unresolved')
        self.assertIn('3E20', r.note)
        self.assertIn('3820', r.note)

    def test_a_loader_that_disagrees_with_a_settled_line_is_reported_not_believed(self):
        """A clean listing whose DATA says something else at one byte: the
        two-witness line stands, the report marks it, and the command fails."""
        loader = render_data(self.res).replace('62,32', '62,42')
        self.assertNotEqual(loader, render_data(self.res), 'the fixture moved')
        (b,) = check(self.listing + '\n' + loader)
        (r,) = [r for r in b.recs if r.addr == 0x7D0E]
        self.assertEqual((r.status, r.bytes, r.conflict), ('clean', b'\x3e\x20', True))
        out = io.StringIO()
        counts, conflicts = hexcheck.report(b, False, out)
        self.assertEqual(conflicts, 1)
        self.assertIn('# 7D0E', out.getvalue())
        self.assertIn('the listing says 32', out.getvalue())
        import contextlib
        import tempfile
        with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False) as f:
            f.write(self.listing + '\n' + loader)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(hexcheck.main([f.name]), 1)
        finally:
            os.unlink(f.name)

    def test_a_comma_the_scan_lost_shifts_the_stream_but_not_the_witness(self):
        """Two DATA values welded into one token: the lines after it take
        their bytes one position on, from between settled neighbours that
        agree on the new offset, and the welded token is named."""
        loader = render_data(self.res).replace('62,32', '6232')
        self.assertIn('6232', loader)
        (b,) = check(self.listing + '\n' + loader)
        after = [r for r in b.recs if r.addr is not None and r.addr > 0x7D10 and r.bytes]
        self.assertTrue(after)
        self.assertTrue(all(r.data for r in after),
                        'lines after the welded token lost their witness')
        self.assertTrue(all(r.bytes in r.data for r in after))
        out = io.StringIO()
        hexcheck.report(b, False, out)
        self.assertIn("'6232'", out.getvalue())
        self.assertIn("6 values for 7 bytes; the listing says 33,192,63,62,32,6,64",
                      out.getvalue())

    def test_an_unreadable_data_value_is_named_with_what_the_listing_says(self):
        loader = render_data(self.res).replace('237,176', '237,1%6')
        (b,) = check(self.listing + '\n' + loader)
        names = [t for t, matters in b.data_damage() if matters]
        self.assertEqual(len(names), 1, names)
        self.assertIn("'1%6' cannot be read: the listing says 176", names[0])

    def test_a_basic_data_line_is_not_a_listing_line(self):
        """`DATA` is four hex-shaped letters, and a BASIC line number is a
        line number: a loader must never be taken for a listing."""
        for raw in ('1260 DATA 20136 140172 583+109+-1', '145@ DATA 23925 958:59',
                    render_data(self.res, per_line=14, first=330).splitlines()[2]):
            self.assertIsNone(hexcheck.parse_line(raw, 1250, None), raw)
        self.assertEqual(hexcheck.find_blocks(render_data(self.res)), [])

    def test_a_data_statement_wrapped_on_the_page_is_read_whole(self):
        """A long DATA statement wraps in the scan, and the wrapped part has
        no line number and no keyword.  The values under the values belong
        to it; a page number under it does not."""
        loader = render_data(self.res, per_line=16)
        first = loader.splitlines()[2]
        parts = first.rsplit(',', 6)
        wrapped = loader.replace(first, parts[0] + ',\n' + ','.join(parts[1:]))
        (s,) = hexcheck.find_data(wrapped)
        self.assertEqual([t.text for t in s], [t.text for t in hexcheck.find_data(loader)[0]])
        (b,) = check(self.listing + '\n' + wrapped)
        self.assertEqual(b.tally['lines the DATA statements witness'],
                         check(self.listing + '\n' + loader)[0].tally['lines the DATA statements witness'])
        (s,) = hexcheck.find_data(loader + '181\n')
        self.assertEqual(len(s), len(hexcheck.find_data(loader)[0]))

    def test_a_page_break_does_not_part_a_listing(self):
        """A page number, a running head and 'Program continued' fall in
        the middle of a listing; the addresses carry on across them, so it
        is one block, and one loader witnesses all of it."""
        lines = self.listing.splitlines()
        cut = next(i for i, l in enumerate(lines) if l.startswith('7D10'))
        page = '\n'.join(lines[:cut] + ['', 'Program continued', '', '181', '',
                                        '## Page 191', '', 'utility', '']
                         + lines[cut:]) + '\n'
        blocks = check(page + '\n' + render_data(self.res))
        self.assertEqual(len(blocks), 1)
        self.assertEqual(self.resolved(blocks)[1:], (0, 0))
        self.assertIsNotNone(blocks[0].stream)
        self.assertEqual(blocks[0].verify(), [])

    # -- yield on ruined pages ---------------------------------------------
    def test_a_label_whose_first_letter_became_a_digit(self):
        """8UFFER is BUFFER: the symbol reader wants a letter first, so the
        name is invisible to it, and the line assembled to nothing."""
        line = '7D27 DD21427D 00320 LD      IX,BUFFER'
        self.assertIn(line, self.listing, 'the fixture moved')
        (b,) = check(self.listing.replace(line, line.replace('BUFFER', '8UFFER')))
        (r,) = [r for r in b.recs if r.addr == 0x7D27]
        self.assertEqual((r.status, r.bytes, r.fargs), ('clean', b'\xdd\x21\x42\x7d', 'IX,BUFFER'))
        self.assertEqual(b.verify(), [])

    def test_lines_the_scan_lost_do_not_move_the_line_after_them(self):
        """A two-byte line ruined past parsing, and the next line's address
        scanned right, two bytes on -- which is one slip from where the
        last parsed line ended, so the chain used to 'repair' it back.  The
        ruined line on the page and the editor's line numbers skipping one
        say the gap is the page's, not the scan's."""
        lines = self.listing.splitlines()
        i = next(k for k, l in enumerate(lines) if l.startswith('7D10'))
        self.assertTrue(lines[i + 1].startswith('7D12') and lines[i + 2].startswith('7D13')
                        and lines[i + 3].startswith('7D14') and lines[i + 4].startswith('7D16'),
                        'the fixture moved')
        lines[i] = '?!;: ruined'
        lines[i + 2] = '&*() ruined'           # and two after, so nothing follows
        lines[i + 3] = '<>{} ruined'           # to confirm the address either
        (b,) = check('\n'.join(lines) + '\n')
        (r,) = [r for r in b.recs if r.lineno == 210]
        self.assertEqual(r.addr, 0x7D12)
        self.assertIn('lost before it', r.anote)
        (r,) = [r for r in b.recs if r.lineno == 240]
        self.assertEqual((r.addr, r.status), (0x7D16, 'clean'))
        self.assertEqual(self.resolved([b])[1], 0)
        self.assertEqual(b.verify(), [])

    def test_a_b_scanned_as_an_e_is_a_shape(self):
        """DEFE for DEFB, 31 times in the reference library: B and E look
        alike to the scan, so a hex field E7 is B7 with one slip, and the
        DATA saying 183 makes the object column a two-witness line."""
        self.assertTrue(hexcheck.plausible_hex('E7', b'\xb7'))
        line = '7D1E B7 00270 OR      A'
        self.assertIn(line, self.listing, 'the fixture moved')
        page = self.listing.replace(line, '7D1E E7 00270 OB      Q')
        (b,) = check(page + '\n' + render_data(self.res))
        (r,) = [r for r in b.recs if r.addr == 0x7D1E]
        self.assertEqual((r.status, r.bytes), ('data', b'\xb7'))

    def test_a_column_rule_stuck_to_a_line_number(self):
        cases = [('TFDF E601 00210» AND o1H', ('7FDF', 'E601', 210, 'AND o1H')),
                 ('TFE1 FEO —-00220«S CP o1H', ('7FE1', 'FE0', 220, 'CP o1H')),
                 ('7FE6 3EOA = 00240. LD A,OAH', ('7FE6', '3E0A', 240, 'LD A,OAH'))]
        for raw, want in cases:
            got = hexcheck.parse_line(raw, 200, None)
            self.assertIsNotNone(got, raw)
            addr, hexs, _, _, lineno, src = got
            self.assertEqual((addr, hexs, lineno, src), want, raw)

    def test_a_page_in_the_manuals_shape(self):
        """Listing, prose, a loader whose loop crosses a page break, and the
        DATA statement at the end: every byte-bearing line witnessed, the
        alignment holding across the prose between, and ENDSTART read as
        END START."""
        (b,) = check(manual_page(self.res, self.listing))
        self.assertEqual(self.statuses([b]).get('unresolved', 0), 0)
        self.assertIsNotNone(b.stream)
        n = len(self.truth)
        self.assertEqual(b.tally['lines the DATA statements witness'], n)
        self.assertEqual(b.tally['DATA statements agree'], n)
        self.assertNotIn('DATA statements disagree', b.tally)
        self.assertEqual([r.fargs for r in b.recs if r.fop == 'END'], ['START'])
        self.assertEqual(b.verify(), [])

    # -- yield on ruined pages, round two -----------------------------------
    MESSAGE = """\
        ORG     9286H
        DEFB    'E'
        DEFB    'T'
        DEFB    '*'
        DEFB    ' '
        DEFB    0
        DEFB    13
        DEFB    ','
MSG     DEFM    'READY'
        DEFW    MSG
        END
"""

    def test_a_quoted_character_between_the_shapes_of_its_quotes(self):
        """The Encyclopedia prints a message one DEFB 'x' a line, and the
        scan makes ‘Et, wT and Nt of the quotes: the character between two
        quote shapes is that character, read as printed, so the hex agreeing
        is two witnesses.  A token garbled past that (tee for '*') is the
        object column's reading alone -- until the DATA agrees."""
        res = asm.assemble(self.MESSAGE)
        self.assertEqual(res.errors, [])
        page = render(res)
        for printed, scanned in (("'E'", '‘Et'), ("'T'", 'wT'), ("'*'", 'tee'),
                                 ("' '", 'an'), ('DEFB    0\n', 'DEFB    oO\n'), ("','", '‘,'),
                                 ("'READY'", '‘READY’')):
            self.assertEqual(page.count(printed), 1, printed)
            page = page.replace(printed, scanned)
        (b,) = check(page)
        by = {r.addr: r for r in b.recs if r.bytes}
        self.assertEqual((by[0x9286].status, by[0x9286].fargs), ('clean', "'E'"))
        self.assertEqual((by[0x9287].status, by[0x9287].fargs), ('clean', "'T'"))
        self.assertEqual((by[0x9288].status, by[0x9288].fargs), ('hexonly', "'*'"))
        self.assertEqual((by[0x9289].status, by[0x9289].fargs), ('hexonly', "' '"))
        self.assertEqual((by[0x928A].status, by[0x928A].bytes), ('clean', b'\x00'))
        self.assertEqual((by[0x928C].status, by[0x928C].fargs), ('clean', "','"))
        self.assertEqual((by[0x928D].status, by[0x928D].fargs), ('clean', "'READY'"))
        self.assertEqual(b.verify(), [])
        # The loader beside it promotes the garbled ones.
        (b,) = check(page + '\n' + render_data(res))
        by = {r.addr: r for r in b.recs if r.bytes}
        self.assertEqual((by[0x9288].status, by[0x9289].status), ('data', 'data'))
        self.assertEqual(self.statuses([b]).get('unresolved', 0), 0)

    def test_a_quoted_character_the_object_column_does_not_meet_is_not_believed(self):
        """wT read as 'T' is 54H; a hex field 57 is one slip from it under
        the ordinary allowance, but a garbled token re-read as a character
        has to be met exactly or by shape, so the line is the object
        column's alone -- and its bytes are the column's, 57."""
        res = asm.assemble(self.MESSAGE)
        page = render(res).replace("9287 54 00120 DEFB    'T'", "9287 57 00120 DEFB    wT")
        self.assertIn('57', page, 'the fixture moved')
        (b,) = check(page)
        (r,) = [r for r in b.recs if r.addr == 0x9287]
        self.assertEqual((r.status, r.bytes), ('hexonly', b'\x57'))

    def test_a_name_that_is_the_whole_encoding_is_one_witness(self):
        """DEFB WT: nothing defines WT, and fitting it from the object code
        would make a two-witness line of one column under a symbol the scan
        invented.  The line is read off the object column and marked."""
        res = asm.assemble(self.MESSAGE)
        page = render(res).replace("DEFB    'T'", 'DEFB    WT')
        (b,) = check(page)
        (r,) = [r for r in b.recs if r.addr == 0x9287]
        self.assertEqual((r.status, r.bytes, r.fargs), ('hexonly', b'\x54', "'T'"))
        self.assertNotIn('WT', b.symbols)
        self.assertEqual(b.verify(), [])

    TABLE = """\
KBWAIT  EQU     0049H
        ORG     704EH
T44     DEFW    0846H
        DEFW    0A18FH
        DEFW    0AAA7H
        DEFW    0AF91H
        DEFW    0BEB8H
        DEFB    0FFH
        DEFW    6A59H
        DEFW    KBWAIT
        END
"""

    def test_a_table_of_defw_entries_with_the_directive_one_slip_off(self):
        """A DEFW table's bytes decode as no instruction, so the disassembly
        gave the mnemonic repair nothing to work from; the printed directive
        does.  DEFH and DEF for DEFW, DEFS for DEFB, the column rule as ©
        between the fields, a dash where the rule was, a leading zero the
        scan lost, a literal parted by a space, QU for EQU after a label."""
        res = asm.assemble(self.TABLE)
        self.assertEqual(res.errors, [])
        page = render(res)
        edits = [('T44     DEFW    0846H', 't44 DEF = 0846H'),
                 ('DEFW    0A18FH', 'DEFW © OAL8FH'),
                 ('DEFW    0AAA7H', 'DEFH © OAAA7H'),
                 ('DEFW    0AF91H', 'DEFW © -OAF9IH'),
                 ('DEFW    0BEB8H', 'DEFW © BEB8H'),
                 ('DEFB    0FFH', 'DEFS © OFFH'),
                 ('DEFW    6A59H', 'DEFW 6 A59H'),
                 ('KBWAIT  EQU     0049H', 'KBWAIT QU 0049H')]
        for printed, scanned in edits:
            self.assertEqual(page.count(printed), 1, printed)
            page = page.replace(printed, scanned)
        (b,) = check(page)
        self.assertEqual(self.statuses([b]).get('unresolved', 0), 0, [
            (r.raw, r.note) for r in b.recs if r.status == 'unresolved'])
        by = {r.addr: r for r in b.recs if r.bytes}
        self.assertEqual((by[0x704E].status, by[0x704E].fop, by[0x704E].label), ('source', 'DEFW', 'T44'))
        self.assertEqual((by[0x7050].status, by[0x7050].fargs), ('clean', '0A18FH'))
        self.assertEqual((by[0x7052].status, by[0x7052].fop), ('source', 'DEFW'))
        self.assertEqual((by[0x7054].status, by[0x7054].fargs), ('clean', '0AF91H'))
        self.assertEqual((by[0x7056].status, by[0x7056].fargs), ('clean', '0BEB8H'))
        self.assertEqual((by[0x7058].status, by[0x7058].fop, by[0x7058].bytes), ('source', 'DEFB', b'\xff'))
        self.assertEqual((by[0x7059].status, by[0x7059].bytes), ('clean', b'\x59\x6a'))
        self.assertEqual(b.symbols.get('KBWAIT'), 0x49)
        self.assertEqual(by[0x705B].fargs, 'KBWAIT')
        self.assertEqual(b.verify(), [])

    def test_a_loader_printed_in_hex_pairs(self):
        """The books also print a loader as DATA 99,AD,B5,... for a program
        that reads VAL("&H"+X$).  It is the same bytes in the object
        column's alphabet, so it aligns and witnesses -- but a printed hex
        digit reads as ITSELF: the second readings the object column gets
        (D as 0) are not the loader's, or two columns read in one alphabet
        would agree on the same wrong byte."""
        res = asm.assemble(self.TABLE)
        image = b''.join(data for _, data in res.segments)
        loader = '\n'.join('%d DATA %s' % (1000 + 10 * i, ','.join('%02X' % c for c in image[k:k + 8]))
                           for i, k in enumerate(range(0, len(image), 8))) + '\n'
        (s,) = hexcheck.find_data(loader)
        self.assertTrue(all(t.hex for t in s))
        self.assertEqual([t.cands for t in s][:4], [[0x46], [0x08], [0x8F], [0xA1]])
        shapes = hexcheck.find_data(loader.replace('A1', 'Al').replace('BE', 'B£'))[0]
        self.assertEqual((shapes[3].text, shapes[3].cands, shapes[9].text, shapes[9].cands),
                         ('Al', [0xA1], 'B£', [0xBE]))
        (b,) = check(render(res) + '\n' + loader)
        self.assertIsNotNone(b.stream)
        self.assertEqual(b.tally['lines the DATA statements witness'], 8)
        self.assertNotIn('DATA statements disagree', b.tally)
        # A destroyed source line and a hex field 8F0F where the loader says
        # 8F,A1: one column against the other, not two agreeing on 8F0F.
        page = render(res).replace('7050 8FA1 00130 DEFW    0A18FH', '7050 8F0F 00130 OEXX QAlBFH')
        self.assertIn('8F0F', page, 'the fixture moved')
        (b,) = check(page + '\n' + loader)
        (r,) = [r for r in b.recs if r.addr == 0x7050]
        self.assertEqual(r.status, 'unresolved')
        self.assertIn('8FA1', r.note)

    def test_a_defm_whose_object_column_shows_its_first_byte_only(self):
        """EDTASM prints one byte of a DEFM string.  Nothing checks the rest
        of the string, so the line stays unresolved -- and the chain does
        not take that one byte for the line's length and 'repair' the next
        address on the strength of it."""
        page = ('7004 49 00250 RDMSG   DEFM    \'INSERT \'\n'
                '700B 45 00260 EDNAME  DEFM    \'EDTASM FOR READ\'\n'
                '701A 0D 00270         DEFB    0DH\n'
                '701B C9 00280         RET\n'
                '701C 00 00290         NOP\n')
        (b,) = check(page)
        by = {r.n: r for r in b.recs}
        self.assertEqual((by[1].status, by[2].status), ('unresolved', 'unresolved'))
        self.assertEqual((by[2].addr, by[3].addr, by[3].status), (0x700B, 0x701A, 'clean'))
        self.assertNotIn('->', by[2].anote + by[3].anote)

    def test_a_data_value_that_lost_a_digit_contradicts_nothing(self):
        """20 for 201 is a plausible scan of the value: the two-witness RET
        is not marked as conflicting with it, and the token is named."""
        loader = render_data(self.res).replace('201,', '20,', 1)
        self.assertNotEqual(loader, render_data(self.res), 'the fixture moved')
        (b,) = check(self.listing + '\n' + loader)
        self.assertFalse(any(r.conflict for r in b.recs))
        self.assertTrue(any("'20': the listing says 201" in t for t, _ in b.data_damage()))

    def test_the_shapes_that_round_two_added_stay_in_their_place(self):
        self.assertEqual(hexcheck.as_hex('92k0'), '92A0')
        self.assertIsNone(hexcheck.as_hex('POKE'))
        self.assertIsNone(hexcheck.lineno_token('32703,62'))
        self.assertEqual(hexcheck.lineno_token('01240,'), 1240)
        self.assertIsNone(hexcheck.parse_line('500 POKE 32703,62 E224', None, None))
        self.assertEqual(hexcheck.split_source('MSGB =~ DEFB tee')[:3], ('MSGB', 'DEFB', 'tee'))
        self.assertEqual(hexcheck.split_source('VMSG © DEFM © \'WRONG\'')[:3], ('VMSG', 'DEFM', "'WRONG'"))
        self.assertEqual(hexcheck.split_source('SETO CALL «=OATFH ;GET')[:3], ('SETO', 'CALL', 'OATFH'))
        self.assertEqual(hexcheck.split_source('csIN —-EQu 0235H')[:3], ('CSIN', 'EQU', '0235H'))

    EDTASM_DEFS = (
        '7D00          00100        ORG  7D00H\n'
        '7D00 210A7D   00110 START  LD   HL,BUF\n'
        '7D03 3620     00120        LD   (HL),20H\n'
        '7D05 3A0C7D   00130        LD   A,(FLAG)\n'
        '7D08 C9       00140        RET\n'
        '7D09 00       00150        NOP\n'
        '0002          00160 BUF    DEFS 2\n'
        '7D0C 01       00170 FLAG   DEFB 1\n'
        '7D0D C9       00180 EXIT   RET\n'
        '7D0E          00190        END\n')

    def test_a_defs_line_prints_its_size_where_the_address_goes(self):
        """EDTASM's own shape (Barden's listings: `0002  00640 AI  DEFS 2`):
        the first column of a DEFS line is the size.  Read as an address it
        made an undamaged page exit 1, and the chain repaired the line after."""
        b, = check(self.EDTASM_DEFS)
        self.assertEqual({r.status for r in b.recs}, {'clean'})
        defs = b.recs[6]
        self.assertEqual((defs.addr, defs.reserve, defs.fop, defs.fargs), (0x7D0A, 2, 'DEFS', '2'))
        self.assertEqual([r.addr for r in b.recs[7:9]], [0x7D0C, 0x7D0D])
        self.assertEqual(b.symbols['BUF'], 0x7D0A)
        self.assertEqual(b.verify(), [])
        self.assertEqual(b.tally.get('addresses repaired'), 0)

    def test_defs_lines_after_a_ruined_line_rejoin_their_listing(self):
        """Barden's page: the line before the DEFS block did not scan, and
        blank lines stand between all of them.  The DEFS lines belong to
        the listing (their first column is no address to part them by), and
        after a lost line the chain's address for them is not believed."""
        page = self.EDTASM_DEFS.replace('7D09 00       00150        NOP', '7D09 O0 0O1 50 aR N0P,') \
                               .replace('DEFS 2', 'DEFS) 2').replace('\n', '\n\n')
        b, = check(page)
        defs = [r for r in b.recs if hexcheck.is_defs(r.op)]
        self.assertEqual([(r.reserve, r.addr, r.status) for r in defs], [(2, None, 'clean')])
        self.assertEqual([r.addr for r in b.recs if r.hexs][-2:], [0x7D0C, 0x7D0D])

    def test_a_defs_size_the_operand_does_not_confirm_is_not_taken(self):
        """One column is not two witnesses: 0003 against DEFS 2 stays out."""
        b, = check(self.EDTASM_DEFS.replace('0002          00160', '0003          00160'))
        self.assertIsNone(b.recs[6].reserve)
        self.assertNotEqual(b.recs[6].status, 'clean')

    def test_a_defs_line_that_prints_its_address_still_reads(self):
        """Other assemblers print the address there; the operand is the size."""
        b, = check(self.EDTASM_DEFS.replace('0002          00160', '7D0A          00160'))
        self.assertEqual({r.status for r in b.recs}, {'clean'})
        self.assertEqual((b.recs[6].addr, b.recs[6].reserve), (0x7D0A, 2))

    def test_a_clean_listing_reads_as_clean(self):
        blocks = check(self.listing)
        self.assertEqual(len(blocks), 1)
        right, wrong, unresolved = self.resolved(blocks)
        self.assertEqual((wrong, unresolved), (0, 0))
        self.assertEqual(right, len(self.truth))
        self.assertTrue(all(r.status in ('clean', 'text')
                            for r in blocks[0].recs), 'nothing needed repair')

    def test_a_damaged_listing_comes_back(self):
        """Nothing the two columns between them vouch for may be wrong."""
        bad, totals = [], [0, 0, 0]
        for seed in range(12):
            blocks = check(damage(self.listing, 0.10, seed))
            right, wrong, unresolved = self.resolved(blocks, checked_only=True)
            for i, v in enumerate((right, wrong, unresolved)):
                totals[i] += v
            if wrong:
                bad.append(seed)
        self.assertEqual(totals[1], 0,
                         'lines were accepted with the wrong bytes (seeds %s)' % bad)
        share = totals[0] / float(totals[0] + totals[2])
        self.assertGreater(share, 0.70,
                           'only %.0f%% of the damaged lines came back' % (100 * share))

    def test_what_the_object_column_alone_says_is_mostly_right_and_always_named(self):
        """A line only the object column vouches for is a reading, not a fact.
        It is worth having -- it is right far more often than not -- but the
        report has to name every one of them, because when the object field is
        damaged into another valid instruction nothing can tell."""
        seen = wrong = 0
        for seed in range(12):
            for b in check(damage(self.listing, 0.10, seed)):
                out = io.StringIO()
                hexcheck.report(b, False, out)
                for r in b.recs:
                    if r.status != 'hexonly':
                        continue
                    seen += 1
                    wrong += self.truth.get(r.addr) != r.bytes
                    self.assertIn('%04X' % r.addr, out.getvalue(),
                                  'an object-column reading went unreported')
        self.assertGreater(seen, 10, 'the fixture stopped exercising this')
        self.assertLess(wrong, 0.15 * seen,
                        '%d of %d object-column readings were wrong' % (wrong, seen))

    def test_the_recovered_source_assembles_to_what_was_reconciled(self):
        for seed in range(6):
            for b in check(damage(self.listing, 0.10, seed)):
                self.assertEqual(b.verify(), [],
                                 'seed %d: the recovered source does not '
                                 'produce the reconciled bytes' % seed)

    def test_a_line_damaged_in_both_columns_is_not_guessed_at(self):
        """Neither column readable, and no guess: the line is reported."""
        blocks = check(self.wrecked())
        _, wrong, unresolved = self.resolved(blocks)
        self.assertEqual(wrong, 0)
        self.assertEqual(unresolved, 1)

    def wrecked(self):
        """The listing with LD A,' ' scanned past recovery in both columns:
        3E20 read as 3820, which is a whole instruction of the same length,
        and a source column that says nothing either way."""
        line = "7D0E 3E20 00190 LD      A,' '"
        self.assertIn(line, self.listing, 'the fixture moved')
        return self.listing.replace(line, '7D0E 3820 00190         Lb Ayre')

    def test_the_command_exits_nonzero_on_an_unresolved_line(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            bad, good = os.path.join(d, 'bad.txt'), os.path.join(d, 'good.txt')
            for path, text in ((bad, self.wrecked()), (good, self.listing)):
                with open(path, 'w') as f:
                    f.write(text)
            out = subprocess.run([sys.executable, 'tools/hexcheck.py', bad],
                                 cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
            self.assertIn('UNRESOLVED', out.stdout)
            ok = subprocess.run([sys.executable, 'tools/hexcheck.py', good],
                                cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)

    def test_the_columns_come_apart(self):
        """The line number ends the columns, whatever the scan did to them."""
        cases = [
            ('7D00 21403C 00140 START   LD HL,VIDEO+64',
             ('7D00', '21403C', 140, 'START   LD HL,VIDEO+64')),
            ('7D03 11003C 0Ol50         LD DE,VIDEO',
             ('7D03', '11003C', 150, 'LD DE,VIDEO')),
            ('7D09 EDBO 00170 LDIR', ('7D09', 'EDB0', 170, 'LDIR')),
            ('00180 ;A COMMENT LINE', (None, '', 180, ';A COMMENT LINE')),
            ('7D1E 52', ('7D1E', '52', None, '')),
        ]
        for raw, want in cases:
            got = hexcheck.parse_line(raw, 130, None)
            self.assertIsNotNone(got, raw)
            addr, hexs, _, _, lineno, src = got
            self.assertEqual((addr, hexs, lineno, ' '.join(src.split())),
                             (want[0], want[1], want[2], ' '.join(want[3].split())), raw)

    def test_prose_is_not_a_listing(self):
        self.assertEqual(hexcheck.find_blocks(
            'The first method of embedding machine code is to include\n'
            'the code in DATA statements and then move it to a fixed\n'
            'location in memory, as Figure 5-3 shows.\n'), [])


if __name__ == '__main__':
    unittest.main()
