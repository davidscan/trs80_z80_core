"""Extractor idiom tests on synthetic listings.

These pin the discriminations that keep the gate number honest -- above
all the ones that stop DATA from being counted as machine code. Every
listing here is written for the test; nothing is corpus material.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from phasea.extract import extract_file                       # noqa: E402
from phasea.basic import (eval_const, parse_program,          # noqa: E402
                          split_statements, data_items)


def run(src):
    with tempfile.NamedTemporaryFile('w', suffix='.bas', delete=False) as fh:
        fh.write(src)
        path = fh.name
    try:
        return extract_file(path)
    finally:
        os.unlink(path)


def only(rep, kind=None):
    ps = rep.payloads if kind is None else [p for p in rep.payloads
                                            if p.kind == kind]
    assert len(ps) == 1, [(p.idiom, p.kind, p.flags) for p in rep.payloads]
    return ps[0]


class TestBasicSurface(unittest.TestCase):

    def test_statement_split_respects_quotes(self):
        self.assertEqual(split_statements('A=1:PRINT"X:Y":B=2'),
                         ['A=1', 'PRINT"X:Y"', 'B=2'])

    def test_dense_keywords_without_spaces(self):
        st = split_statements('FORC=1TO9:READD:POKEC,D:NEXT')
        self.assertEqual(len(st), 4)

    def test_data_without_space(self):
        self.assertEqual(data_items('DATA205,127,10'), [205, 127, 10])
        self.assertEqual(data_items('DATA 1, 2 , 3'), [1, 2, 3])
        self.assertIsNone(data_items('PRINT 1'))

    def test_rem_and_apostrophe_inside_data_are_items(self):
        # The ROM's cruncher leaves a DATA statement's text alone up to the
        # next ':' outside quotes, so REM and ' there are not comments: the
        # items after them, and the statements behind the ':', are real
        # (the 2026-09-19 audit, L-58).
        self.assertEqual(split_statements("DATA IT'S,5:PRINT 1"),
                         ["DATA IT'S,5", 'PRINT 1'])
        self.assertEqual(split_statements('DATA PREMIUM,7:X=2'),
                         ['DATA PREMIUM,7', 'X=2'])
        self.assertEqual(data_items('DATA PREMIUM,7'), [None, 7])
        self.assertEqual(split_statements("X=1:REM A:B"), ['X=1', 'REM A:B'])
        self.assertEqual(split_statements("X=1:' A:B"), ['X=1', "' A:B"])
        p = only(run("10 FOR I=0 TO 7:READ A:POKE 30000+I,A:NEXT\n"
                     "20 DATA 33,0,60,62,'1':DATA 32,119,201\n"))
        self.assertEqual(p.provenance['values_found'], 8)

    def test_an_empty_data_item_reads_as_zero(self):
        # READ of an empty item is 0: the ROM's number reader (224DH) finds
        # nothing and returns 0, and a bare DATA is one such item.  They
        # were dropped or read as non-numeric, which shifted every byte
        # behind them (the 2026-09-19 audit, L-59).
        self.assertEqual(data_items('DATA'), [0])
        self.assertEqual(data_items('DATA 1,,2,'), [1, 0, 2, 0])
        self.assertEqual(data_items('DATA 1, ,2'), [1, 0, 2])
        self.assertEqual(data_items('DATA 1,"",2'), [1, None, 2])  # a quoted one is ?SN
        p = only(run('10 FOR I=0 TO 7:READ A:POKE 30000+I,A:NEXT\n'
                     '20 DATA 62,,50,,60,33,,201\n'))
        self.assertEqual(p.bytes, [62, 0, 50, 0, 60, 33, 0, 201])
        self.assertEqual(p.confidence, 'high')

    def test_eval_const(self):
        self.assertEqual(eval_const('16446'), 16446)
        self.assertEqual(eval_const('&HB000'), 0xB000)
        self.assertEqual(eval_const('-20480'), -20480)
        self.assertEqual(eval_const('32713+I', {'I': 5}), 32718)
        self.assertEqual(eval_const('(&H900C)'), 0x900C)
        self.assertIsNone(eval_const('VARPTR(A(0))'))
        self.assertIsNone(eval_const('X'))

    def test_blocked_header_ignored(self):
        prog = parse_program('0 REM *** BLOCKED: raw bytes in code ***\n'
                             '10 PRINT 1\n')
        self.assertEqual([ln for ln, _b, _s in prog], [10])


class TestLoaderIdioms(unittest.TestCase):

    def test_literal_range_loader(self):
        p = only(run('10 FOR C=32660 TO 32663:READ M:POKE C,M:NEXT\n'
                     '20 DATA 62,1,211,201\n'))
        self.assertEqual((p.base, p.length, p.confidence),
                         (32660, 4, 'high'))
        self.assertEqual(p.bytes, [62, 1, 211, 201])

    def test_negative_addresses_wrap(self):
        p = only(run('10 FOR I=-54 TO -51:READ Y:POKE I,Y:NEXT\n'
                     '20 DATA 1,2,3,4\n'))
        self.assertEqual(p.base, 65482)          # -54 & 0xFFFF
        self.assertEqual(p.length, 4)

    def test_hex_bounds(self):
        p = only(run('10 FOR I=(&H900C) TO (&H900F):READ B:POKE I,B:NEXT\n'
                     '20 DATA 1,2,3,4\n'))
        self.assertEqual(p.base, 0x900C)

    def test_base_plus_index(self):
        p = only(run('10 FOR I=0 TO 3:READ J:POKE 32713+I,J:NEXT\n'
                     '20 DATA 1,2,3,4\n'))
        self.assertEqual((p.base, p.length), (32713, 4))

    def test_symbolic_base_resolved_from_constant(self):
        p = only(run('5 ML=30000\n'
                     '10 FOR X=ML TO ML+3:READ N:POKE X,N:NEXT\n'
                     '20 DATA 1,2,3,4\n'))
        self.assertEqual((p.base, p.length), (30000, 4))

    def test_unresolvable_base_is_flagged_not_guessed(self):
        p = only(run('10 INPUT ML\n'
                     '20 FOR X=ML TO ML+3:READ N:POKE X,N:NEXT\n'
                     '30 DATA 1,2,3,4\n'))
        self.assertEqual(p.kind, 'unextractable')
        self.assertEqual(p.confidence, 'none')
        self.assertIn('loop-bounds-unresolved', p.flags)
        self.assertEqual(p.bytes, [])

    def test_restore_redirects_the_data_pointer(self):
        p = only(run('10 RESTORE 40:FOR I=100 TO 102:READ J:POKE I,J:NEXT\n'
                     '20 DATA 99,99,99\n'
                     '40 DATA 7,8,9\n'))
        self.assertEqual(p.bytes, [7, 8, 9])

    def test_loader_split_across_lines(self):
        """READ and POKE on the lines after the FOR (REPLY 4 item a)."""
        p = only(run('10 FOR I=32000 TO 32002\n'
                     '20 READ J\n'
                     '30 POKE I,J\n'
                     '40 NEXT I\n'
                     '50 DATA 205,127,10\n'))
        self.assertEqual(p.bytes, [205, 127, 10])
        self.assertEqual(p.base, 32000)

    def test_restore_on_the_line_before(self):
        p = only(run('10 RESTORE 40\n'
                     '20 FOR I=100 TO 102:READ J:POKE I,J:NEXT\n'
                     '30 DATA 99,99,99\n'
                     '40 DATA 7,8,9\n'))
        self.assertEqual(p.bytes, [7, 8, 9])

    def test_bare_restore_means_the_first_data(self):
        p = only(run('5 DATA 1,2,3\n'
                     '10 RESTORE:FOR I=100 TO 102:READ J:POKE I,J:NEXT\n'
                     '30 DATA 99,99,99\n'))
        self.assertEqual(p.bytes, [1, 2, 3])
        self.assertEqual(p.provenance['data_from'], 'restore-first')

    def test_transformed_poke_value_is_flagged_not_high(self):
        p = only(run('20 FOR I=100 TO 102:READ J:POKE I,255-J:NEXT\n'
                     '30 DATA 1,2,3\n'))
        self.assertIn('poke-value-transformed', p.flags)
        self.assertNotEqual(p.confidence, 'high')

    def test_adjacency_not_program_order(self):
        """DATA earlier in the file must not be stolen by a later loader."""
        p = only(run('10 DATA 99,98,97\n'
                     '20 FOR I=100 TO 102:READ J:POKE I,J:NEXT\n'
                     '30 DATA 1,2,3\n'))
        self.assertEqual(p.bytes, [1, 2, 3])

    def test_two_loaders_share_one_data_block(self):
        """Level II READ has one sequential pointer, so the second loader
        reads where the first one stopped (the 2026-09-19 audit, H-18:
        both started at "the first DATA after this READ" and came out
        with the same bytes at confidence high).  A RESTORE of its own
        sets the second loader's pointer back; a loader that follows a
        RESTOREd one and lands in its DATA continues behind it."""
        rep = run('10 FOR I=32000 TO 32003:READ A:POKE I,A:NEXT\n'
                  '20 FOR I=32100 TO 32103:READ A:POKE I,A:NEXT\n'
                  '30 DATA 62,1,211,201\n'
                  '40 DATA 175,211,255,201\n')
        self.assertEqual([(p.base, p.bytes, p.confidence) for p in rep.payloads],
                         [(32000, [62, 1, 211, 201], 'high'),
                          (32100, [175, 211, 255, 201], 'high')])
        rep = run('10 FOR I=32000 TO 32003:READ A:POKE I,A:NEXT\n'
                  '20 RESTORE:FOR I=32100 TO 32103:READ A:POKE I,A:NEXT\n'
                  '30 DATA 62,1,211,201\n')
        self.assertEqual([p.bytes for p in rep.payloads],
                         [[62, 1, 211, 201], [62, 1, 211, 201]])
        rep = run('10 RESTORE 900:FOR I=32000 TO 32003:READ A:POKE I,A:NEXT\n'
                  '20 FOR I=32100 TO 32103:READ A:POKE I,A:NEXT\n'
                  '30 DATA 9,9,9\n'
                  '900 DATA 62,1,211,201,175,211,255,201\n')
        self.assertEqual([p.bytes for p in rep.payloads],
                         [[62, 1, 211, 201], [175, 211, 255, 201]])
        # three loaders on one block: each behind the one before it
        rep = run('10 FOR I=1 TO 2:READ A:POKE 32000+I,A:NEXT\n'
                  '20 FOR I=1 TO 2:READ A:POKE 32100+I,A:NEXT\n'
                  '30 FOR I=1 TO 2:READ A:POKE 32200+I,A:NEXT\n'
                  '40 DATA 1,2,3,4,5,6\n')
        self.assertEqual([p.bytes for p in rep.payloads],
                         [[1, 2], [3, 4], [5, 6]])
        self.assertTrue(all(p.confidence == 'medium' for p in rep.payloads[:2]))

    def test_a_loop_variable_with_a_type_suffix(self):
        """I% indexes the POKE like I does (the 2026-09-19 audit, H-19: no
        word boundary follows a %, so the variable was never found and the
        loader filed as fixed-address-unresolved).  I and I% are two
        variables: a loop on I does not index a POKE at I%."""
        p = only(run('10 FOR I%=32000 TO 32003:READ A%:POKE I%,A%:NEXT\n'
                     '20 DATA 62,1,211,201\n'))
        self.assertEqual((p.base, p.bytes, p.confidence),
                         (32000, [62, 1, 211, 201], 'high'))
        p = only(run('10 FOR I%=0 TO 3:READ A:POKE 32000+I%,A:NEXT\n'
                     '20 DATA 62,1,211,201\n'))
        self.assertEqual(p.base, 32000)
        p = only(run('10 FOR I=0 TO 3:READ A:POKE 32000+I%,A:NEXT\n'
                     '20 DATA 62,1,211,201\n'))
        self.assertEqual(p.kind, 'unextractable')
        self.assertIn('fixed-address-unresolved', p.flags)


class TestSymbolsThatStopBeingConstant(unittest.TestCase):
    """A base is a constant only while nothing else can have stored into
    it: flagged, never guessed."""

    DATA = '90 DATA 62,1,211,201\n'

    def test_a_base_the_user_is_asked_for_is_unresolved(self):
        p = only(run('10 ML=32000:INPUT "LOAD ADDRESS";ML\n'
                     '20 FOR I=0 TO 3:READ A:POKE ML+I,A:NEXT\n' + self.DATA))
        self.assertEqual((p.kind, p.base), ('unextractable', None))
        self.assertIn('poke-address-unresolved', p.flags)

    def test_read_for_and_if_branches_unsettle_a_base_too(self):
        for store in ('READ ML', 'FOR ML=1 TO 2:NEXT',
                      'IF Q=1 THEN ML=28000', 'IF Q=1 THEN PRINT:ML=28000',
                      'IFQ=1THEN50ELSEML=28000', 'LINEINPUT#1,ML',
                      'INPUT MLOAD'):
            p = only(run('10 ML=32000\n15 %s\n'
                         '20 FOR I=0 TO 3:READ A:POKE ML+I,A:NEXT\n' % store
                         + self.DATA), 'unextractable')
            self.assertIsNone(p.base, store)

    def test_a_bound_that_is_read_is_flagged_not_skipped(self):
        """N=0 then READ N: the loop is not a zero-trip loop to pass over."""
        p = only(run('10 N=0\n20 READ N\n'
                     '30 FOR I=1 TO N:READ A:POKE 32000+I,A:NEXT\n'
                     '90 DATA 4,62,1,211,201\n'), 'unextractable')
        self.assertIn('loop-bounds-unresolved', p.flags)

    def test_a_name_reused_further_down_still_resolves_above(self):
        """meltdown.bas: X=-1073, the loader, and FOR X= 250 lines later."""
        p = only(run('10 X=-1073:FOR I=1 TO 4:READ A:POKE X+I,A:NEXT\n'
                     '500 FOR X=44 TO 46:SET(X,1):NEXT\n' + self.DATA),
                 'candidate-ml')
        self.assertEqual((p.base, p.confidence), (64464, 'high'))

    def test_the_constant_assigned_again_gives_the_symbol_back(self):
        """compkorn.bas: Y=217, FOR Y= in between, Y=217 before the loader."""
        p = only(run('10 Y=32003\n49 FOR Y=0 TO 5:NEXT\n1010 Y=32003\n'
                     '1020 FOR I=32000 TO Y:READ A:POKE I,A:NEXT\n'
                     '9000 DATA 62,1,211,201\n'))
        self.assertEqual((p.base, p.length), (32000, 4))

    def test_the_signed_address_idiom_is_read_through(self):
        """tty32drv.bas: the IF compares constants, and both values of MS
        are one address."""
        p = only(run('3 MS=48030\n6 IF MS>32767 THEN MS=MS-65536\n'
                     '20 FOR I=0 TO 3:READ A:POKE MS+I,A:NEXT\n' + self.DATA))
        self.assertEqual((p.base, p.confidence), (48030, 'high'))

    def test_a_known_branch_to_another_address_is_not_a_constant(self):
        p = only(run('3 MS=48030\n6 IF MS>32767 THEN MS=MS-1\n'
                     '20 FOR I=0 TO 3:READ A:POKE MS+I,A:NEXT\n' + self.DATA))
        self.assertEqual(p.kind, 'unextractable')


class TestStringPacked(unittest.TestCase):

    def test_chr_concatenation_is_a_payload_at_varptr(self):
        p = only(run('10 A$=CHR$(205)+CHR$(127)+CHR$(10)+CHR$(41)+CHR$(195)+CHR$(154)+CHR$(10)+CHR$(0)\n'
                     '20 DEFUSR=PEEK(VARPTR(A$)+1)+256*PEEK(VARPTR(A$)+2)\n'))
        self.assertEqual(p.idiom, 'string-packed')
        self.assertEqual(p.base_symbol, 'VARPTR(A$)')
        self.assertEqual(p.bytes, [205, 127, 10, 41, 195, 154, 10, 0])
        self.assertEqual(p.confidence, 'high')

    def test_string_dollar_and_literal_terms_and_continuation(self):
        p = only(run('10 M$=STRING$(4,0)+"AB"\n'
                     '20 M$=M$+CHR$(201)+CHR$(&HC9)\n'
                     '30 POKE 16526,PEEK(VARPTR(M$)+1):POKE 16527,PEEK(VARPTR(M$)+2)\n'))
        self.assertEqual(p.bytes, [0, 0, 0, 0, 65, 66, 201, 201])

    def test_unresolved_term_stops_and_flags(self):
        p = only(run('10 A$=CHR$(1)+CHR$(2)+CHR$(3)+CHR$(4)+CHR$(5)+CHR$(6)+CHR$(7)+CHR$(8)+CHR$(X)+CHR$(9)\n'
                     '20 DEFUSR=PEEK(VARPTR(A$)+1)+256*PEEK(VARPTR(A$)+2)\n'))
        self.assertEqual(p.bytes, [1, 2, 3, 4, 5, 6, 7, 8])
        self.assertIn('string-term-unresolved', p.flags)
        self.assertEqual(p.confidence, 'low')

    def test_read_loop_appending_chr_is_string_packing(self):
        p = only(run('10 FOR I=1 TO 8:READ V:A$=A$+CHR$(V):NEXT\n'
                     '20 DATA 205,127,10,41,195,154,10,0\n'
                     '30 V=VARPTR(A$):DEFUSR=PEEK(V+1)+256*PEEK(V+2)\n'))
        self.assertEqual(p.idiom, 'string-packed')
        self.assertEqual(p.base_symbol, 'VARPTR(A$)')
        self.assertEqual(p.bytes, [205, 127, 10, 41, 195, 154, 10, 0])


    def test_the_usr_link_is_followed_through_every_variable(self):
        """V=VARPTR(A$):AD=PEEK(V+1)+256*PEEK(V+2):DEFUSR=AD -- the entry
        names no VARPTR and no variable assigned one directly, only a
        variable computed from such a variable (the 2026-09-19 audit,
        H-17: one hop was followed, this common form was dropped).  The
        hops may sit anywhere in the listing: a subroutine below sets
        them for a DEF USR above."""
        p = only(run('10 A$=CHR$(205)+CHR$(127)+CHR$(10)+CHR$(41)+CHR$(195)+CHR$(154)+CHR$(10)+CHR$(0)\n'
                     '20 V=VARPTR(A$):AD=PEEK(V+1)+256*PEEK(V+2):DEFUSR=AD\n'))
        self.assertEqual((p.idiom, p.base_symbol), ('string-packed', 'VARPTR(A$)'))
        p = only(run('10 FOR I=1 TO 8:READ V:A$=A$+CHR$(V):NEXT\n'
                     '20 DATA 205,127,10,41,195,154,10,0\n'
                     '30 GOSUB 900:POKE 16526,LO:POKE 16527,HI:END\n'
                     '900 P=VARPTR(A$):L=PEEK(P+1):H=PEEK(P+2):LO=L:HI=H:RETURN\n'))
        self.assertEqual((p.idiom, p.base_symbol), ('string-packed', 'VARPTR(A$)'))

    def test_a_string_nobody_takes_varptr_of_is_text(self):
        rep = run('10 PR$=" PREPROCESSING":F$=CHR$(24)+STRING$(34,24)+CHR$(26)+CHR$(13)\n'
                  '20 FOR I=1 TO 8:READ V:L$=L$+CHR$(V):NEXT\n'
                  '30 DATA 1,2,3,4,5,6,7,8\n')
        self.assertEqual([p.idiom for p in rep.payloads], [])

    def test_a_string_passed_as_the_usr_argument_is_text(self):
        # VARPTR(S$) hands the string TO a routine; S$ is not the routine
        rep = run('10 S$="THIS IS A STRING TO REVERSE"\n'
                  '20 DEFUSR=32000:X=USR(VARPTR(S$))\n')
        self.assertEqual([p.idiom for p in rep.payloads], [])


class TestNotMachineCode(unittest.TestCase):
    """The discriminations that stop DATA inflating the gate number."""

    def test_fixed_printer_address_is_a_device_stream(self):
        p = only(run('10 FOR X=1 TO 8:READ A:POKE 14312,A:NEXT\n'
                     '20 DATA 1,2,3,4,5,6,7,8\n'))
        self.assertEqual(p.kind, 'device-stream')
        self.assertIn('fixed-address-printer', p.flags)

    def test_video_ram_target_is_screen_data(self):
        p = only(run('10 FOR T=15360 TO 15363:READ G:POKE T,G:NEXT\n'
                     '20 DATA 128,129,130,131\n'))
        self.assertEqual(p.kind, 'screen-data')
        self.assertIn('target-video-ram', p.flags)

    def test_multi_value_read_is_table_data(self):
        p = only(run('10 FOR I=1 TO 4:READ D,L:POKE 30000+L,D:NEXT\n'
                     '20 DATA 1,0,2,1,3,2,4,3\n'))
        self.assertEqual(p.kind, 'table-data')
        self.assertTrue(any(f.startswith('multi-value-read') for f in p.flags))

    def test_addr_value_pairs_are_not_a_linear_payload(self):
        p = only(run('10 FOR X=1 TO 3:READ A,B:POKE A,B:NEXT\n'
                     '20 DATA 30000,1,30001,2,30002,3\n'))
        self.assertEqual(p.kind, 'table-data')


class TestVarptrIdiom(unittest.TestCase):

    def test_integer_array_becomes_little_endian_bytes(self):
        rep = run('10 DIM US%(2):FOR X=0 TO 2:READ US%(X):NEXT\n'
                  '20 DEF USR=VARPTR(US%(0))\n'
                  '30 DATA 32717,258,-1\n')
        p = only(rep, 'candidate-ml')
        self.assertEqual(p.idiom, 'varptr-array')
        self.assertIsNone(p.base)
        self.assertEqual(p.base_symbol, 'VARPTR(US%(0))')
        # 32717 = 0x7FCD -> CD 7F ; 258 = 0x0102 -> 02 01 ; -1 -> FF FF
        self.assertEqual(p.bytes, [0xCD, 0x7F, 0x02, 0x01, 0xFF, 0xFF])

    def test_varptr_entry_is_recorded_as_symbolic(self):
        rep = run('10 DIM US%(1):FOR X=0 TO 1:READ US%(X):NEXT\n'
                  '20 DEF USR=VARPTR(US%(0))\n'
                  '30 DATA 1,2\n')
        e = [x for x in rep.usr_entries if x.kind == 'varptr']
        self.assertEqual(len(e), 1)
        self.assertIsNone(e[0].addr)
        self.assertEqual(e[0].symbol, 'VARPTR(US%(0))')


class TestUsrEvidence(unittest.TestCase):

    def test_vector_poke_pair(self):
        rep = run('10 POKE16526,62:POKE16527,64\n')
        e = rep.usr_entries[0]
        self.assertEqual((e.kind, e.addr), ('vector-poke', 16446))

    def test_def_usr_slots_and_hex(self):
        rep = run('10 DEF USR0=&HB000:DEF USR1=&HB00D\n')
        self.assertEqual({x.slot: x.addr for x in rep.usr_entries},
                         {0: 0xB000, 1: 0xB00D})

    def test_usr_calls_counted_outside_comments(self):
        rep = run("10 S=USR(1):T=USR(2)\n20 REM USR(3)\n")
        self.assertEqual(rep.usr_calls, 2)


class TestPokeSequences(unittest.TestCase):

    def test_consecutive_literal_pokes_form_a_payload(self):
        src = '10 ' + ':'.join('POKE %d,%d' % (30000 + i, i)
                               for i in range(10)) + '\n'
        p = only(run(src))
        self.assertEqual(p.idiom, 'poke-seq')
        self.assertEqual((p.base, p.length), (30000, 10))

    def test_short_runs_are_ignored(self):
        rep = run('10 POKE 30000,1:POKE 30001,2\n')
        self.assertEqual(rep.payloads, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
