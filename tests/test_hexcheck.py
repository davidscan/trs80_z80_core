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


def check(text):
    blocks = hexcheck.find_blocks(text)
    return [hexcheck.Block(b, 'test').run() for b in blocks]


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
