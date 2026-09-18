"""tools/romcalls.py: the ROM entry points a listing calls, tallied from
what hexcheck settled -- two-witness lines counted, one-column lines
counted apart, data lines not at all."""
import io
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'tests'))

import romcalls                                                 # noqa: E402
import test_hexcheck                                            # noqa: E402
from z80 import asm                                             # noqa: E402
from z80 import coprocess                                       # noqa: E402

SOURCE = """\
        ORG     7000H
        CALL    0A7FH
        CALL    0033H
        LD      A,'X'
        CALL    0033H
        RST     28H
        CALL    Z,01C9H
        CALL    7100H
        JP      NZ,7000H
        LD      HL,1A19H
        DEFW    0033H
        JP      1A19H
        END
"""


class RomCalls(unittest.TestCase):
    def setUp(self):
        self.res = asm.assemble(SOURCE)
        self.assertEqual(self.res.errors, [])
        self.listing = test_hexcheck.render(self.res)

    def test_the_tally_counts_calls_into_rom_and_nothing_else(self):
        (b,) = test_hexcheck.check(self.listing)
        calls = romcalls.rom_calls(b.recs)
        targets = sorted(t for t, _, _, _ in calls)
        # 7100H and 7000H are RAM; LD HL,1A19H is no call; DEFW 0033H is data.
        self.assertEqual(targets, [0x0028, 0x0033, 0x0033, 0x01C9, 0x0A7F, 0x1A19])
        self.assertEqual(sorted({op for _, op, _, _ in calls}), ['CALL', 'JP', 'RST'])
        self.assertFalse(any(alone for _, _, alone, _ in calls))

    def test_a_one_column_line_is_counted_apart(self):
        line = '7008 CD3300 00140 CALL    0033H'
        self.assertIn(line, self.listing, 'the fixture moved')
        (b,) = test_hexcheck.check(self.listing.replace(line, '7008 CD3300 00140 CALL    0O33N'))
        (r,) = [r for r in b.recs if r.addr == 0x7008]
        self.assertEqual(r.status, 'hexonly')
        calls = romcalls.rom_calls(b.recs)
        self.assertEqual([alone for t, _, alone, _ in calls if t == 0x0033], [False, True])

    def test_the_report_names_the_served_entries(self):
        with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False) as f:
            f.write('A page of prose.\n\n' + self.listing + '\nMore prose.\n')
        try:
            table, seen = romcalls.tally([f.name])
        finally:
            os.unlink(f.name)
        self.assertEqual(seen, 1)
        self.assertEqual(table[0x0033]['calls'], 2)
        self.assertEqual(table[0x0033]['files'], {f.name})
        out = io.StringIO()
        romcalls.report(table, out=out)
        text = out.getvalue()
        self.assertIn('0033H  DSP display char', text)
        self.assertIn('6 ROM-range calls to 5 entry points', text)
        for target in (0x0A7F, 0x01C9, 0x1A19):
            self.assertIn(target, coprocess.SERVED)
        self.assertRegex(text, r'0A7FH .* yes ')
        self.assertRegex(text, r'0033H .* no ')
        self.assertIn('the core serves 3 of the 5 entries, 3 of the 6 calls', text)

    def test_no_listing_exits_2(self):
        with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False) as f:
            f.write('nothing here\n')
        try:
            with io.StringIO() as err:
                sys.stderr, saved = err, sys.stderr
                try:
                    self.assertEqual(romcalls.main([f.name]), 2)
                finally:
                    sys.stderr = saved
        finally:
            os.unlink(f.name)


if __name__ == '__main__':
    unittest.main()
