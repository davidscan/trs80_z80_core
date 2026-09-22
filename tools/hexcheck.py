#!/usr/bin/env python3
"""tools/hexcheck.py -- read a scanned assembly listing back by making its
three columns check each other.

    python3 tools/hexcheck.py FILE [--out DIR] [--block N] [-v]

A period assembler printed a listing's address column, its object (hex)
column and its source column from ONE source file, so the three agree by
construction: the source assembles to the hex, and each address is the
one before it plus the bytes on that line.  OCR breaks that agreement,
and every disagreement it leaves is damage in exactly one column --
which makes the other two a check on it, and usually a repair:

    7D00 21403  00140 START  LD HL, 3COOH+64 : SOURCE
    7D03 11003C 00150        Lp DE, 3Co0H : DESTINATION
    7O06 01C003 00160        cp BC, 1024~64 :@ BYTES

Line 1: the source says 21 40 3C once `3COOH` is read in the alphabet a
hex literal is written in, so it is the object column that lost a digit.
Line 2: `Lp` is not an instruction, but those bytes disassemble as
`LD DE,3C00H`, whose text is one slip from what is printed, and whose
operand the source itself confirms.  Line 3: `cp BC,1024-64` assembles
to 01 C0 03, which is what the object column already says, so the
mnemonic is the damage -- and 7O06 must be 7D06, the address before it
plus three bytes.  Nothing here is a guess: two witnesses agree on the
bytes of every line accepted, or the line is reported instead.

WHAT IT DOES
  1. Splits every line into address / hex / line-number / source.  In the
     address, hex and line-number fields the alphabet is digits (and
     A-F), so O->0, l/I->1, S->5, G->6, Z->2, @->0 and their friends
     resolve mechanically, and a column rule the scan stuck to a line
     number (00210», 00240.) is cut off it.  A listing parted by a page
     break -- the page number, the running head, 'Program continued' --
     is joined back where its addresses or line numbers carry on across
     the break.
  2. Chains the addresses: each line's address is the previous one plus
     its length, so a damaged address is repaired from its neighbours and
     a damaged hex field's LENGTH is known independently.  Where the page
     lost lines -- lines that would not parse at all, or the editor's
     line numbers skipping -- a scanned address a few bytes ahead of the
     chain is the address of the line after them, and is kept.
  3. Takes the labels the listing itself defines (a label's value is its
     own line's address) and assembles each source line alone at its own
     address with z80.asm.  A name one slip from exactly one of those
     labels is that label, even when the slip put a digit first (8UFFER).
  4. Reconciles, line by line, into one of four outcomes:
       clean       the columns agree as printed;
       repaired    one column was damaged and the other two say how -- the
                   bytes rest on two witnesses, as a clean line does;
       one object  the source column was destroyed, so the bytes are a
       column      READING OF ONE COLUMN, the hex or the DATA.  It is
       alone       usually right and worth having, but nothing checks it,
                   so the report names every such line and the recovered
                   source marks it;
       unresolved  the columns are damaged past agreement.  What each
                   decodes to is printed for a human to judge; nothing is
                   guessed at.
  5. Re-assembles the recovered source as a whole and requires it to
     produce the reconciled bytes.  Exit status is 1 if any line is
     unresolved or that re-assembly disagrees, so a listing is never
     accepted silently.
  6. Reads the BASIC DATA statements printed near the listing as a THIRD
     WITNESS.  The books print a routine twice -- the assembly listing,
     and a DATA/POKE loader of the same bytes in decimal -- and the
     decimal column was printed from the same bytes.  The DATA lines in
     the file are read in the decimal alphabet (O->0, l->1, S->5, U->4
     ...) into a stream of byte values, the stream is aligned against the
     lines already settled on two witnesses (three lines and six bytes
     must agree at one offset, which chance does not supply), and then
     the decimal bytes of every line are one more reading of its object
     field.  So a source line read as printed that assembles to what the
     DATA says is accepted even where the hex column reads as something
     else; a line read off the object column alone becomes a two-witness
     line when the DATA agrees, and is UNRESOLVED when it does not; and a
     line settled on two witnesses that the DATA contradicts is kept but
     marked '#', because either the loader was scanned wrong or the book
     printed two versions, and only a human can say which.  The DATA
     block gets checked in return: every decimal token the listing's
     bytes contradict or cannot read is named, with the byte it should be.
     The alignment is piecewise -- a comma the scan lost shifts the
     stream by one from there on, and the offset may change between two
     settled lines that agree on the new one -- and a line takes its DATA
     bytes only from between settled neighbours that agree, so a shifted
     stream never becomes a false witness.  A loader printed in HEX PAIRS
     (DATA 99,AD,B5,... for a program that reads VAL("&H"+X$)) is read
     the same way, but a printed hex digit reads as ITSELF -- the shapes
     of the alphabet resolve (O for 0, £ for E), the second readings the
     object column gets (D as 0) do not, because the object column is read
     in that same alphabet and two columns agreeing on the same second
     reading is not two witnesses.
  7. Reads tables and messages in the alphabets THEY are printed in.  A
     DEF directive's operand holds no register, so a short token is a
     number or a quoted character: the character between the shapes of two
     quote marks (‘Et, wT, Nt) is that character as printed, and the hex
     has to meet it exactly or by shape -- a garbled token re-read as a
     character is not owed the ordinary allowance; a token of digit shapes
     (oO) is those digits.  A DEFW table's entries decode as no
     instruction, so the disassembly gives the mnemonic repair nothing to
     work from; the printed directive does: a mnemonic one slip from a DEF
     directive (DEFH, DEF, OEFW, DEFS for DEFB) is repaired from the
     printed operand, or, the operand destroyed, the entry is read off the
     object column as that directive (one column, marked).  A name that
     nothing defines and that IS the whole encoding (DEFB WT) is never
     fitted from the object code: that would make two witnesses of one
     column under a symbol the scan invented.  The column rule the scan
     read as '©', '=', '—' between the fields is a mark, not an operand.
     An EQU whose value column and operand disagree by one slip (0A7EH
     against 0A7FH) is DISPUTED: one witness each, so a source line that
     assembles only through that name cannot repair the hex with it, and
     a use in the code whose bytes hold the operand's value settles the
     equate that way.

WHAT IT DOES NOT DO
  Comments carry no bytes, so nothing can check them; they are passed
  through as scanned.  An object field damaged into a DIFFERENT VALID
  INSTRUCTION of the same length, on a line whose source is also gone,
  cannot be caught by the listing alone -- the columns agree on the
  wrong answer.  The DATA statements catch it, when the book printed
  them: the decimal bytes disagree, and the line is reported instead of
  accepted.  What the DATA cannot do is settle that line by itself: one
  column says 3820, another says 3E20, the source says nothing, and the
  tool prints both rather than choosing.  A decimal digit scanned as
  another digit (a 6 read as an 8) is invisible inside its token, so the
  DATA is never a witness on its own either.  A DEFM whose object column
  shows the string's first byte only (EDTASM prints one) stays
  unresolved: the chain knows the length, the hex knows one byte, and
  nothing checks the letters between.  A page the scanner split into
  columns -- the address column as one run of lines, the object bytes as
  another, the mnemonics as a third, in an order of its own -- holds no
  line to read; those pages need scanning again, not a parser.
"""
import argparse
import itertools
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from z80 import asm                                             # noqa: E402
from z80 import disasm                                          # noqa: E402

HEXDIGITS = set('0123456789ABCDEF')

# OCR of a character that can only be a hex digit.  Lower case letters that
# ARE hex digits (a-f) are simply upper-cased; the rest are shapes.
HEXFIX = {
    'O': '0', 'o': '0', 'Q': '0', '@': '0', 'U': '0', 'u': '0', 'D': 'D',
    'l': '1', 'I': '1', 'i': '1', '|': '1', '!': '1', 'L': '1', '[': '1',
    'Z': '2', 'z': '2', 'J': '3', 'S': '5', 's': '5', '$': '5',
    'G': '6', 'g': '9', 'q': '9', 'T': '7', '?': '7', 'Y': '7',
    'P': 'F', 'R': '8', 'H': '4', 'M': 'M', 'N': 'M',
    '¢': 'C', '(': 'C', 'c': 'C', '{': 'C', '©': 'C',
    'x': 'X', '°': '0', '‘': '1', '“': '4', '£': 'E',
    'k': 'A', 'K': 'A',     # 92k0 for 92A0, six lines of one listing; 58k for 58A
}
# The line-number column is decimal only.  A-F are left out on purpose: they
# are hex digits, so allowing them would read an object field as a line number.
DIGFIX = {
    'O': '0', 'o': '0', 'Q': '0', '@': '0', 'U': '0', '°': '0',
    'l': '1', 'I': '1', 'i': '1', '|': '1', '!': '1', 'L': '1', '‘': '1',
    'Z': '2', 'z': '2', 'J': '3', 'S': '5', 's': '5', '$': '5',
    'G': '6', 'T': '7', '?': '7', 'R': '8', 'g': '9', 'q': '9',
}

# A DATA statement's values are decimal too, but there the letters A-F are
# not hex digits and can only be shapes: a B is an 8, an A a 4.
DECFIX = dict(DIGFIX, A='4', B='8', b='6', D='0', d='0', h='4', H='4')
# Shapes with a second decimal digit behind them, tried one at a time.  A
# printed digit reads as itself: a 6 scanned as an 8 is invisible inside its
# token, and that is a reason the DATA column is never a witness alone.
DECALT = {'U': '4', 'u': '4', 'S': '3', 's': '3', 'l': '7', 'I': '7', 'i': '7',
          'T': '1', 'g': '6', 'q': '4', 'Z': '7'}

MNEMONICS = sorted(asm.MNEMONICS | asm.DIRECTIVES)
# Characters OCR confuses for one another, for scoring a repair.  Case is
# kept: half of these pairs only look alike in one case ('c'/'e', 'B'/'8').
SHAPES = [set('O0Qo@DU'), set('1lI|!i'), set('2Zz'), set('5S$s'), set('6Gb'),
          set('8B'), set('9gq'), set('7T?'), set('CG('), set('EF'), set('BH'),
          set('PF'), set('AR'), set('MN'), set('UV'), set('nm'), set('rn'),
          set('ce'), set('tf'), set('uv'), set('il'), set('Jj)'), set('yv'),
          set('aou'), set('sS5'), set('LI1'), set('DO0'), set('Xx'), set('Zz'),
          set('IJ'), set('aJ'), set('uL'), set('pD'), set('rP'), set('4H'),
          set('4u'), set('ED'), set('CO'), set('bD'), set('tE'), set('oe'),
          set('BE')]     # DEFE for DEFB 31 times in the reference library


SHAPE_OF = {}
for _s in SHAPES:
    for _c in _s:
        SHAPE_OF.setdefault(_c.lower(), set()).update(x.lower() for x in _s)


def same_shape(a, b):
    a, b = a.lower(), b.lower()
    return a == b or b in SHAPE_OF.get(a, ())


def ocr_distance(a, b):
    """Edit distance where an OCR-plausible substitution costs half."""
    prev = [2 * j for j in range(len(b) + 1)]
    for i, ca in enumerate(a, 1):
        cur = [2 * i]
        for j, cb in enumerate(b, 1):
            sub = prev[j - 1] + (0 if ca == cb else (1 if same_shape(ca, cb) else 2))
            cur.append(min(sub, prev[j] + 2, cur[-1] + 2))
        prev = cur
    return prev[-1] / 2.0


def close_enough(scan, cand, share=0.5):
    """Is `cand` near enough to what was scanned to be the same text damaged?
    Half the characters may differ; OCR-plausible ones count as half that."""
    if not scan:
        return False
    return ocr_distance(scan, cand) <= share * max(len(scan), len(cand))


def carries_bytes(args):
    """Does this operand put a value of its own into the encoding, rather than
    only naming registers?  A mnemonic taken from the object column is checked
    by the bytes only where the answer depends on the operand the page printed."""
    return bool(re.search(r'[0-9]|[A-Z_@?][A-Z0-9_@?$]{2,}', (args or '').upper()))


def near_hex(scan, b):
    """Is the scanned object field these bytes, badly read?  The threshold
    grows with the field, but one slip in two bytes is already a lot."""
    if not scan:
        return False
    # Compared in the field's own alphabet: a '(' for C or an O for 0 is
    # a mechanical reading, not a slip to pay for ((D3308 against CD3300
    # is the one slip 8 for 0, not two).
    scan = as_hex(scan) or scan.upper()
    return ocr_distance(scan, b.hex().upper()) < max(1.5, 0.2 * len(scan))


def shape_cost(scan, want):
    """The cost of reading `scan` as `want` when only shapes may differ: half
    a slip per look-alike, and no way at all for anything else."""
    if len(scan) != len(want):
        return 9.0
    return sum(0 if a == c else (0.5 if same_shape(a, c) else 9.0)
               for a, c in zip(scan, want))


def plausible_hex(scan, b):
    """Is the scanned object field these bytes with nothing worse than shape
    slips -- the strict form of near_hex, for one object column to vouch
    for the other's reading."""
    return bool(scan) and shape_cost(as_hex(scan) or scan.upper(), b.hex().upper()) <= 1.0


def hexlit(v):
    """A hex literal the assembler will read: it must start with a digit."""
    s = '%04X' % (v & 0xFFFF)
    return (s if s[0].isdigit() else '0' + s) + 'H'


def fix_field(tok, table):
    """Map a scanned field into its alphabet, or None if a character cannot be."""
    out = []
    for ch in tok:
        u = ch.upper()
        if u in HEXDIGITS and table is HEXFIX:
            out.append(u)
        elif table is not HEXFIX and ch.isdigit():
            out.append(ch)
        elif ch in table:
            out.append(table[ch])
        elif u in table:
            out.append(table[u])
        else:
            return None
    return ''.join(out)


def as_hex(tok):
    if re.search('[kK]', tok) and 2 * sum(c.isdigit() for c in tok) < len(tok):
        return None                     # k is A among digits (92k0), not in a word (POKE)
    v = fix_field(tok, HEXFIX)
    return v if v and all(c in HEXDIGITS for c in v) else None


# Shapes with more than one hex digit behind them.  HEXFIX picks the commonest
# reading; these are the others, tried when the first satisfies nobody.
AMBIGUOUS = {'u': '4', 'U': '4', 'S': '35', 'G': 'C6', 'b': '6D',
             'l': '17', 'I': '17', 'i': '17', 'Z': '72', 'g': '69', 'T': '17',
             'o': 'C0D', 'O': 'C0D', 'Q': 'C0', 'D': '0', 'E': 'F8', 'F': 'E',
             '8': 'B', '0': 'D', '6': '8', 'B': '8', 'C': 'G', 'A': '4'}


def hex_readings(scan, limit=16):
    """Every way the scanned object field reads as hex, commonest first.  That
    field's alphabet is sixteen characters wide, so a shape that could be two
    of them leaves two readings, and the other two columns choose between
    them.  One character is read differently at a time: two slips in one field
    is past what the other columns can settle."""
    first = as_hex(scan)
    if first is None:
        return []
    out = [first]
    for i, ch in enumerate(scan):
        for alt in AMBIGUOUS.get(ch, '') + AMBIGUOUS.get(ch.upper(), ''):
            if alt in HEXDIGITS and alt != first[i]:
                cand = first[:i] + alt + first[i + 1:]
                if cand not in out:
                    out.append(cand)
                if len(out) >= limit:
                    return out
    return out


def as_lineno(tok):
    if not 3 <= len(tok) <= 6:
        return None
    v = fix_field(tok, DIGFIX)
    return int(v) if v and v.isdigit() else None


def lineno_token(tok):
    """The line number a token holds, allowing for the column rule the scan
    stuck to it (00210», —-00220«S, 00240.): read as printed first, and only
    if that fails with the marks stripped off the ends."""
    v = as_lineno(tok)
    if v is None:
        # Only a MARK may be cut off: the digits up to the first character
        # that is neither letter nor digit.  A hex field's last letter is
        # not a mark (1403C is not line 1403).
        m = re.match(r'^[^0-9A-Za-z]*([^\W_]{4,}?)[^0-9A-Za-z]+[^\W_]?$', tok)
        if m:                           # and past the mark at most one stray letter («S), not 32703,62
            v = as_lineno(m.group(1))
    return v


def is_data_word(tok):
    """Is this token the BASIC keyword DATA, allowing the scan one slip of
    shape (OATA, DA7A)?  Nothing an assembler prints is four letters from it."""
    return len(tok) == 4 and ocr_distance(tok.upper(), 'DATA') <= 0.5


def dec_readings(tok):
    """Every byte value a scanned DATA token can be, commonest reading
    first.  An empty set means the token is not readable as a byte at all:
    a character outside the alphabet, or a value past 255 (a comma the scan
    lost welds two values into one token, which the alignment then steps
    over)."""
    first = fix_field(tok, DECFIX)
    if first is None:
        return []
    outs = [first]
    for i, ch in enumerate(tok):
        alt = DECALT.get(ch)
        if alt and alt != first[i]:
            outs.append(first[:i] + alt + first[i + 1:])
    seen = []
    for v in outs:
        if v.isdigit() and int(v) <= 255 and int(v) not in seen:
            seen.append(int(v))
    return seen


class Tok:
    """One value of a DATA statement, as scanned."""

    def __init__(self, n, k, text):
        self.n, self.k, self.text = n, k, text        # file line, position in it
        self.cands = dec_readings(text)
        self.hex = False                              # printed as a hex pair

    def reread_hex(self):
        """A printed hex digit reads as ITSELF, as a printed decimal digit
        does: the alphabet's shapes (O for 0, £ for E) resolve, but no
        second reading (D as 0) -- the object column is read in the same
        alphabet with the same second readings, and two columns agreeing
        on the same wrong one is not two witnesses."""
        self.hex = True
        h = as_hex(self.text)
        self.cands = [int(h, 16)] if h and len(h) == 2 else []

    def lit(self, v):
        """The value as this loader prints it, for naming a correction."""
        return '%02X' % v if self.hex else str(v)


def hex_pairs(toks):
    """Is this loader printed in hex pairs rather than decimal?  Every value
    is then two characters wide, and a third of the hex digits are letters,
    where a decimal loader has none but the scan's shapes."""
    if len(toks) < 8:
        return False
    short = sum(1 for t in toks if len(t.text) <= 2)
    letters = sum(1 for t in toks if re.search(r'[A-Fa-f£]', t.text))
    return short >= 0.9 * len(toks) and letters >= 0.25 * len(toks)


DATA_SEP = re.compile(r"[\s,.;:+/]+")


def find_data(text, gap_lines=8):
    """The DATA statements in a file, as streams of scanned byte tokens.  A
    stream is a run of DATA lines in line-number order; a page break may
    fall inside it, so up to `gap_lines` other lines are allowed between
    two of its statements, but a line number that goes backwards starts
    another loader and another stream."""
    streams, cur, last_ln, gap, wrap = [], [], None, 0, False
    for n, raw in enumerate(text.splitlines(), 1):
        toks = raw.split()
        if not toks:
            gap += 1
            wrap = False
            continue
        word = None
        if is_data_word(toks[0]):
            word, lineno = 0, None
        elif len(toks) > 1 and len(toks[0]) <= 5 and is_data_word(toks[1]):
            word = 1
            v = fix_field(toks[0], DIGFIX)
            lineno = int(v) if v and v.isdigit() else None
        elif wrap and re.search(r'[,.;:]', raw) and re.match(r'^[\s\d,.;:+/A-Za-z@|!$?-]+$', raw) \
                and len(DATA_SEP.split(raw.strip())) >= 2 \
                and all(dec_readings(t) for t in DATA_SEP.split(raw.strip()) if t):
            # A DATA statement too long for the page wraps, and the wrapped
            # part has no line number and no keyword: values under values.
            word, lineno = -1, None
        if word is None:
            gap += 1
            wrap = False
            continue
        payload = raw if word < 0 else \
            (raw.split(None, word + 1)[word + 1] if len(toks) > word + 1 else '')
        payload = payload.split("'")[0]
        vals = [t for t in DATA_SEP.split(payload) if t]
        # A run of words at the end is the prose that followed on the page.
        while vals and not any(c.isdigit() or c in DECFIX or c in 'CEFcef£' for c in vals[-1]):
            vals.pop()
        if not vals:
            gap += 1
            wrap = False
            continue
        if cur and (gap > gap_lines
                    or (lineno is not None and last_ln is not None and lineno <= last_ln)):
            streams.append(cur)
            cur = []
        cur += [Tok(n, k, t) for k, t in enumerate(vals)]
        if lineno is not None:
            last_ln = lineno
        gap, wrap = 0, True
    if cur:
        streams.append(cur)
    streams = [s for s in streams if len(s) >= 4]
    for s in streams:
        if hex_pairs(s):
            # A loader printed in hex pairs (DATA 99,AD,B5,...), for a BASIC
            # program that reads them back with VAL("&H"+X$): the same bytes
            # in the hex alphabet, so the object column's readings apply.
            for t in s:
                t.reread_hex()
    return streams


# ---- one line of a listing ---------------------------------------------------
class Rec:
    """One scanned listing line, and what the three columns make of it."""

    def __init__(self, n, raw):
        self.n = n                  # 1-based line number in the input file
        self.raw = raw.rstrip('\n')
        self.addr = None            # as scanned, repaired later
        self.rawhex = ''            # the object field exactly as scanned
        self.hexs = ''              # hex digits as scanned, alphabet-repaired
        self.dirty = False          # the hex field held characters that are not hex
        self.lineno = None
        self.src = ''
        self.label = self.op = self.args = self.comment = None
        self.fop = self.fargs = None     # the statement as reconciled
        self.bytes = None           # the reconciled bytes
        self.status = 'unparsed'
        self.anote = ''             # what the address chain did
        self.note = ''              # what reconciling did, this round
        self.fixed = ''             # the recovered source line
        self.data = []              # readings of this line from the DATA statements
        self.dpos = None            # where in the DATA stream those start
        self.conflict = False       # settled on two witnesses, and the DATA disagrees
        self.lost = 0               # lines of the page before this one that would not parse
        self.col0 = None            # the first column as scanned, before the chain touched it
        self.reserve = None         # a DEFS line with no object bytes: how many it reserves


HEXRUN = re.compile(r'^[0-9A-Fa-f%s]{1,4}$' % re.escape(''.join(HEXFIX)))
HEXLIT = re.compile(r'^[0-9A-Fa-f%s]{1,4}[Hh]$' % re.escape(''.join(HEXFIX)))


def split_operand(text):
    """(operand, comment) -- the operand field ends at the first token that
    cannot continue an expression.  OCR loses the ';' more often than not."""
    i = text.find(';')
    if i >= 0 and text[:i].count("'") % 2 == 0:
        return text[:i].strip(), text[i:]
    out, depth, quote = [], 0, False
    for tok in text.split(' '):
        if not tok:
            continue
        if out and depth == 0 and not quote and not re.search(
                r'([,+\-*/(]|\.[A-Z]+\.)$', out[-1]) \
                and not (HEXRUN.match(out[-1]) and HEXLIT.match(tok)):
            break                       # (6 A59H is one literal the scan parted)
        for ch in tok:
            if quote:
                quote = ch != "'"
            elif ch == "'":
                quote = True
            elif ch == '(':
                depth += 1
            elif ch == ')':
                depth = max(0, depth - 1)
        out.append(tok)
    used = 0
    for tok in out:
        used = text.index(tok, used) + len(tok)
    return text[:used], text[used:]         # the span, so a quoted space lives


def parse_line(raw, prev_lineno, prev_addr):
    """Split one scanned line into (addr, hexdigits, dirty, lineno, source).

    The editor's line number is the LAST field before the source, and it is
    the only one of the three whose alphabet is decimal, so the last token of
    the leading run that is four to six decimal characters ends the columns:
    what precedes it is the address and the object bytes, what follows is the
    source.  A line with no line number (a continuation of the bytes above it)
    leaves the address and the hex behind."""
    toks = raw.split()
    if not toks:
        return None
    if any(is_data_word(t) for t in toks[:2]):
        return None                     # a BASIC DATA statement, not a listing line
    last = None
    for i, t in enumerate(toks[:4]):
        if 4 <= len(t) <= 10 and lineno_token(t) is not None:
            last = i
    if last == 0:
        # Nothing before it: a line number only when the line reads as one.
        ln = lineno_token(toks[0])
        if not ((len(toks) > 1 and toks[1][:1] in ';*')
                or (prev_lineno is not None and 0 < ln - prev_lineno <= 20)):
            last = None
    lineno = lineno_token(toks[last]) if last is not None else None
    if last is None:
        # No line number: the columns run while the tokens are hex, and what
        # is left must be a statement or nothing, or this is not a listing.
        k = 0
        while k < min(5, len(toks)) and as_hex(toks[k]) is not None:
            k += 1
        cols, rest = toks[:k], toks[k:]
        if rest and rest[0].upper().rstrip(':,.') not in asm.MNEMONICS | asm.DIRECTIVES:
            return None
        src = ' '.join(rest)
    else:
        # A column rule the scan read as a mark of its own ('=', '»') is not
        # a column.
        cols = [t for t in toks[:last] if any(c.isalnum() for c in t)]
        src = ' '.join(toks[last + 1:])
    addr = None
    if cols and 3 <= len(cols[0]) <= 5 and as_hex(cols[0]) is not None:
        a = as_hex(cols[0])
        addr = a if len(a) == 4 else None   # a digit lost or gained: ask the chain
        cols = cols[1:]
    hexs, dirty = [], False
    for t in cols:
        h = as_hex(t)
        if h is None:
            return None
        dirty = dirty or h != t.upper()
        hexs.append(h)
    if addr is None and lineno is None:
        return None
    if lineno is None and not hexs:
        return None
    return addr, ''.join(hexs), ''.join(cols), dirty, lineno, src


# ---- blocks ------------------------------------------------------------------
def find_blocks(text, min_lines=4):
    """Runs of listing-shaped lines in a file that may be mostly prose.  A run
    ends at two lines that are not listing-shaped, or at an END statement; the
    line-number column is too badly scanned to mark a boundary with."""
    lines = text.splitlines()
    blocks, cur, prev_ln, prev_addr, gap, lost = [], [], None, None, 0, 0
    for n, raw in enumerate(lines, 1):
        p = parse_line(raw, prev_ln, prev_addr)
        if p is None:
            gap += 1
            lost += bool(raw.strip())
            if gap > 1 and cur:
                blocks.append(cur)
                cur, prev_ln, prev_addr = [], None, None
            continue
        gap = 0
        addr, hexs, rawhex, dirty, lineno, src = p
        r = Rec(n, raw)
        r.addr = int(addr, 16) if addr else None
        r.hexs, r.rawhex, r.dirty, r.lineno, r.src = hexs, rawhex, dirty, lineno, src
        if not cur and blocks and continues(blocks[-1], r, lines[blocks[-1][-1].n:n - 1]):
            cur = blocks.pop()           # the same listing, across a page break
        r.lost = lost if cur else 0
        lost = 0
        cur.append(r)
        if lineno is not None:
            prev_ln = lineno
        if addr:
            prev_addr = int(addr, 16)
        if re.match(r'^\s*(END|ENO|EMD)\b', src.upper()):
            blocks.append(cur)
            cur, prev_ln, prev_addr = [], None, None
    if cur:
        blocks.append(cur)
    return [b for b in blocks if len(b) >= min_lines and sum(1 for r in b if r.hexs) >= 2]


def is_defs(op):
    """DEFS or DS, under the marks a scan leaves on a word (`DEFS)`)."""
    return re.sub(r'[^A-Z]', '', (op or '').upper()) in ('DEFS', 'DS')


def continues(block, r, skipped, page_lines=12, reach=64):
    """Does this line carry on the listing that ended a page break ago?  The
    page number, the running head and the 'Program continued' are what part
    a listing, and the address column joins it back: the line's address lies
    just past the last address of the block, or its editor line number just
    past the block's last, and the block did not END.  What was skipped must
    be a page break -- the page marker among a dozen lines at most -- or a
    line or three the scan ruined; paragraphs of commentary between two
    fragments of a disassembly are not a break in one listing."""
    last = block[-1]
    if len(skipped) > page_lines or re.match(r'^\s*(END|ENO|EMD)\b', last.src.upper()):
        return False
    if sum(1 for l in skipped if l.strip()) > 3 \
            and not any(re.match(r'^## Page\b', l) for l in skipped):
        return False
    addr = r.addr
    if not r.hexs and is_defs(split_source(r.src)[1]):
        addr = None                     # that first column is a size (Block.reserves), not a place
    tail = [x for x in block if x.addr is not None]
    if addr is not None and tail and 0 < addr - tail[-1].addr <= reach:
        return True
    lns = [x.lineno for x in block if x.lineno is not None]
    return r.lineno is not None and lns and 0 < r.lineno - lns[-1] <= 100 and addr is None


# ---- the check ---------------------------------------------------------------
CONFIDENT = ('clean', 'hex', 'source', 'data')     # the bytes rest on two witnesses


class Block:
    def __init__(self, recs, source_name='listing', streams=None):
        self.recs = recs
        self.name = source_name
        self.streams = streams or []    # the file's DATA statements, find_data()
        self.stream = None              # the one this block aligned with
        self.doff = None                # its offset: token = doff + (addr - dbase)
        self.dbase = None
        self.symbols = {}
        self.inferred = {}          # names the object code gave a value to
        self.disputed = {}          # equates whose value column and operand disagree by a slip
        self.org = None
        self.tally = {}
        self.first_fixed = 0            # the block's first address was chained backward

    def run(self, rounds=5):
        """Settle the block.  A line reconciled in one round gives the address
        chain its true length, which can resolve a neighbour in the next; and
        the lines settled on two witnesses are what the DATA statements are
        aligned against, so their bytes reach the other lines a round later."""
        self.parse_sources()

        def state():
            return [(r.addr, r.bytes, r.status, getattr(r, 'equ_value', None)) for r in self.recs]
        for _ in range(rounds):
            before = state()
            self.chain_addresses()
            self.collect_symbols()
            self.align_data()
            self.reconcile()
            self.settle_equates()
            if before == state():
                break
        return self

    # -- 6. the DATA statements ---------------------------------------------
    def align_data(self):
        """Give every line its reading from the DATA statements, if the
        stream can be placed against this block.  The lines already settled
        on two witnesses are the anchors: the stream is placed where the most
        of them match (three lines and six bytes at least), and each other
        line takes its bytes from the offset its settled neighbours on both
        sides agree on -- which is the global one, or, past a comma the scan
        lost, the one both neighbours moved to.  A line with a disagreeing
        neighbour gets nothing: a shifted stream is not a witness."""
        for r in self.recs:
            r.data, r.dpos = [], None
        self.stream = self.doff = self.dbase = None
        anchors = [r for r in self.recs
                   if r.status in CONFIDENT and r.bytes and r.addr is not None]
        if len(anchors) < 3 or not self.streams:
            return
        base = anchors[0].addr
        best = None
        for s in self.streams:
            cands = [t.cands for t in s]
            offs, count, nbytes = {}, {}, {}
            for r in anchors:
                offs[id(r)] = set()
                for p in range(len(s) - len(r.bytes) + 1):
                    if all(r.bytes[k] in cands[p + k] for k in range(len(r.bytes))):
                        o = p - (r.addr - base)
                        offs[id(r)].add(o)
                        count[o] = count.get(o, 0) + 1
                        nbytes[o] = nbytes.get(o, 0) + len(r.bytes)
            # Scored by bytes, not lines: a listing of one-byte lines matches
            # a stream in many places, and a three-byte line is worth three.
            for o, c in count.items():
                if c >= 3 and nbytes[o] >= 6 and (best is None or (nbytes[o], c) > best[:2]):
                    best = (nbytes[o], c, s, o, offs)
        if best is None:
            return
        _, _, s, off, offs = best
        self.stream, self.doff, self.dbase = s, off, base
        cands = [t.cands for t in s]
        pos = {id(r): i for i, r in enumerate(self.recs)}
        order = sorted(anchors, key=lambda r: pos[id(r)])
        witnessed = 0
        for i, r in enumerate(self.recs):
            if r.addr is None:
                continue
            n = self.length_of(r) or self.chain_length(r)
            if not n:
                continue
            prev = [a for a in order if pos[id(a)] < i]
            nxt = [a for a in order if pos[id(a)] > i]
            if prev and nxt:
                cand = offs[id(prev[-1])] & offs[id(nxt[0])]
                weight = len(prev[-1].bytes) + len(nxt[0].bytes)
            elif prev or nxt:
                cand = offs[id((prev or nxt)[-1 if prev else 0])] & {off}
                weight = 0
            else:
                continue
            # A comma the scan lost, or a mark it invented, moves the stream
            # by a value or two; anything further is a repeat of the same
            # bytes elsewhere in the loader, which is not a shift at all.
            if off in cand:
                o = off
            elif len(cand) == 1 and weight >= 4 and abs(min(cand) - off) <= 2:
                o = cand.pop()
            else:
                continue
            p = o + (r.addr - base)
            if p < 0 or p + n > len(s):
                continue
            # The position comes from this line's own address, which may be
            # the one thing about it the chain could not repair: it has to
            # fall between the neighbours that placed it.
            if prev and p < o + (prev[-1].addr - base) + len(prev[-1].bytes):
                continue
            if nxt and p + n > o + (nxt[0].addr - base):
                continue
            r.dpos = p                  # known even where a token is unreadable
            if all(cands[p + k] for k in range(n)):
                r.data = [bytes(t) for t in itertools.islice(
                    itertools.product(*[cands[p + k] for k in range(n)]), 8)]
                witnessed += 1
        self.tally['lines the DATA statements witness'] = witnessed

    def near_dec(self, r, b, loose=False):
        """Are the DATA tokens under this line these bytes, scanned badly?
        For one object column to vouch for the other the allowance is
        strict: a token may differ from the value only by shapes (S for 5),
        two of them across the line at most.  A digit for another digit is
        not a slip the scan makes, and a token that lost a digit (12 for 125)
        is a plausible scan of twenty values, which is to say it vouches for
        none of them -- though `loose` counts that lost digit, for asking
        whether the DATA can be read as these bytes at all."""
        if r.dpos is None or not b or self.stream is None:
            return False
        cost = 0.0
        for k, v in enumerate(b):
            t = self.stream[r.dpos + k]
            if v in t.cands:
                continue
            if t.hex:
                return False            # a hex pair reads as itself or not at all
            cost += min(shape_cost(t.text, str(v)),
                        ocr_distance(t.text, str(v)) if loose else 9.0)
        return cost <= 1.0

    @staticmethod
    def lost_digit(t, v):
        """Is this decimal token the value with one digit dropped (20 for
        201)?  Such a token is a plausible scan of the value, so it neither
        vouches for it nor contradicts it."""
        if t.hex:
            return False
        d = fix_field(t.text, DECFIX)
        s = str(v)
        return d is not None and len(d) == len(s) - 1 \
            and any(s[:i] + s[i + 1:] == d for i in range(len(s)))

    def data_damage(self):
        """What the listing says about the DATA statements: every token that
        an accepted line's bytes contradict or that cannot be read as a byte,
        with the value it should be.  (text, corrected) pairs."""
        out = []
        if self.stream is None:
            return out
        last = None
        for r in self.recs:
            if r.dpos is None or not r.bytes or r.status not in CONFIDENT:
                continue
            if last is not None and r.dpos - last.dpos != r.addr - last.addr:
                # The stream shifted between two witnessed lines: a comma the
                # scan lost welded two values, or a stray mark became one.
                toks = self.stream[last.dpos + len(last.bytes):r.dpos]
                between = [x for x in self.recs if x.addr is not None and x.bytes
                           and last.addr < x.addr < r.addr]
                want = r.addr - last.addr - len(last.bytes)
                says = b''.join(x.bytes for x in between)
                at, to = (toks[0], toks[-1]) if toks else (self.stream[last.dpos],) * 2
                where = 'line %d value %d' % (at.n, at.k + 1)
                if to.n != at.n:
                    where += ' to line %d value %d' % (to.n, to.k + 1)
                elif to.k != at.k:
                    where += '-%d' % (to.k + 1)
                out.append(('DATA %s %s: %d values for %d bytes; the listing says %s'
                            % (where, ' '.join(repr(t.text) for t in toks) or '(none)',
                               len(toks), want,
                               ','.join(at.lit(b) for b in says) if len(says) == want
                               else '%d bytes, not all settled' % want), True))
            last = r
            for k, b in enumerate(r.bytes):
                t = self.stream[r.dpos + k]
                if not t.cands:
                    out.append(('DATA line %d value %d %r cannot be read: the listing says %s'
                                % (t.n, t.k + 1, t.text, t.lit(b)), True))
                elif b not in t.cands:
                    out.append(('DATA line %d value %d %r: the listing says %s'
                                % (t.n, t.k + 1, t.text, t.lit(b)), True))
                elif t.text.upper() != t.lit(b):
                    out.append(('DATA line %d value %d %r read as %s'
                                % (t.n, t.k + 1, t.text, t.lit(b)), False))
        return out

    # -- 1. the address chain ---------------------------------------------
    def chain_addresses(self):
        """Each address is the one before it plus that line's bytes, so the
        chain repairs a scanned address and, where the hex field lost a
        character, says independently how long the line must be."""
        recs = self.recs
        lens = [self.length_of(r) for r in recs]
        step = self.lineno_step()
        fixed, pc = 0, None
        for i, r in enumerate(recs):
            r.gap = False
            if r.op in ('EQU', 'DEFL'):
                continue                # the value column, not a place: the counter stands
            if self.reserves(r, pc, self.lost_before(recs, i, step)):
                lens[i] = r.reserve
                pc = (r.addr + r.reserve) & 0xFFFF if r.addr is not None else None
                continue
            if r.addr is None:
                if r.hexs and pc is not None:
                    r.addr, r.anote = pc, 'address %04X from the chain' % pc
            elif pc is not None and r.addr != pc \
                    and not self.fits_forward(recs, lens, i) \
                    and ocr_distance('%04X' % r.addr, '%04X' % pc) <= 1.5:
                # A scanned address ahead of the chain, where the page has
                # lines that would not parse or the editor's line numbers
                # skip, is the address of a line after ones the scan lost:
                # the chain closes a gap the page made, and must not.
                # At most eight bytes a lost line: further ahead than that,
                # the scanned address is the damage (a 3 read as a 5 in the
                # address column reads the same way in the hex column, and
                # the chain is what breaks the two columns' agreement).
                lost = self.lost_before(recs, i, step)
                ahead = (r.addr - pc) & 0xFFFF
                if lost and 0 < ahead <= 8 * lost:
                    r.anote = ('address %04X kept: %d line%s lost before it'
                               % (r.addr, lost, '' if lost == 1 else 's'))
                    r.gap = True        # the chain's length claim does not cross this
                else:
                    r.anote = 'address %04X->%04X' % (r.addr, pc)
                    r.addr = pc
                    fixed += 1
            if r.addr is None and not r.hexs:
                continue                # a comment, or a line number alone: no bytes, no address
            if r.addr is None:
                pc = None
            elif lens[i] is not None:
                pc = (r.addr + lens[i]) & 0xFFFF
            elif not r.hexs:
                pc = r.addr             # an ORG line moves the counter
            else:
                pc = None               # a damaged object field breaks the chain
        if self.first_address(recs, lens, step):
            return self.chain_addresses()       # the lines under it take their place again
        self.tally['addresses repaired'] = fixed + self.first_fixed

    def first_address(self, recs, lens, step):
        """The chain runs forward, so nothing has vouched for the FIRST
        address: a 7 scanned as a 1 there was 'clean', and the block then
        began at 1D00H (the ROM-call tally counts a branch into the block's
        own span as a call to itself, and that span reached down into the
        ROM).  So the first address is chained BACKWARD from the next
        addressed line -- one whose own scan stands, because the line after
        IT agrees with it -- less the bytes between.  Not where the page
        lost lines in between, and not against an ORG whose operand and
        address column agree: those are two witnesses already."""
        chained = [i for i, r in enumerate(recs)
                   if r.addr is not None and r.reserve is None and r.op not in ('EQU', 'DEFL')]
        if len(chained) < 2:
            return False
        i, j = chained[0], chained[1]
        a, b = recs[i], recs[j]
        if b.addr != b.col0 or not self.fits_forward(recs, lens, j):
            return False
        if any(lens[k] is None for k in range(i, j)) or self.lost_before(recs, j, step):
            return False
        want = (b.addr - sum(lens[k] or 0 for k in range(i, j)
                             if recs[k].op not in ('EQU', 'DEFL'))) & 0xFFFF
        if want == a.addr:
            return False
        if a.op == 'ORG':
            for args in mechanical(a.args or ''):
                try:
                    if asm.Expr(args, a.n).eval(self.symbols, 0) == a.addr:
                        return False
                except (asm.AsmError, asm.Undefined):
                    pass
        a.anote = 'address %04X->%04X: the lines after it agree' % (a.addr, want)
        a.addr = want
        self.first_fixed = 1
        return True

    def reserves(self, r, pc, lost=0):
        """EDTASM prints the SIZE of a DEFS in the first column, where every
        other line has its address, and no object bytes beside it:

            805C 16F6    00630        ...
            0002         00640 AI     DEFS 2
            0002         00650 LO     DEFS 2

        (as it prints an EQU's value there).  Read as an address the 0002
        breaks the chain on an undamaged page, and the chain then "repairs"
        the address of the line after.  So on a DEFS line with an empty
        object column the first column is checked against the OPERAND, the
        other place the size is printed: when the two agree the line
        reserves that many bytes at the chain's address.  A first column
        that IS the chain's address is an assembler that prints the address
        there, and the operand alone gives the size.  Anything else is left
        to the ordinary rules, which will not accept it.  The line has no
        scanned address to stop the chain at, so where the page lost lines
        just before it the chain's address is not believed: the size stands
        and the address is unknown until a scanned one takes the chain up."""
        r.reserve = None
        if not is_defs(r.op) or r.hexs or r.col0 is None:
            return False
        if lost and r.col0 != pc:
            pc = None
        size = None
        for args in mechanical(r.args or ''):
            try:
                size = asm.Expr(asm.split_operands(args, r.n)[0], r.n).eval(self.symbols, pc or 0)
                break
            except (asm.AsmError, asm.Undefined, IndexError):
                continue
        if size is None or not 0 <= size <= 0xFFFF:
            return False
        if r.col0 == size and r.col0 != pc:
            r.addr = pc
            r.anote = ('the first column is the size, %d; %s' % (
                size, 'address %04X from the chain' % pc if pc is not None
                else 'its address is not known here'))
        elif r.col0 != pc:
            return False
        r.reserve = size
        return True

    def lineno_step(self):
        """The editor's usual increment between consecutive line numbers."""
        steps = {}
        lns = [r.lineno for r in self.recs if r.lineno is not None]
        for a, b in zip(lns, lns[1:]):
            if 0 < b - a <= 100:
                steps[b - a] = steps.get(b - a, 0) + 1
        return max(steps, key=steps.get) if steps else None

    def lost_before(self, recs, i, step):
        """How many lines the page lost before this one, on two signals: the
        lines between it and the one before that would not parse at all,
        and the editor's line numbers skipping more than their step."""
        lost = recs[i].lost
        prev = [x.lineno for x in recs[:i] if x.lineno is not None]
        if step and recs[i].lineno is not None and prev:
            # Against the highest number so far: line numbers only rise, so
            # a scanned one that fell (390 read as 30) is the damage, not a
            # gap of thirty-six lines before the next.
            skipped = (recs[i].lineno - max(prev)) // step - 1
            if 0 < skipped <= 10:       # past ten it is the line number that is wrong (92690 for 02690)
                lost = max(lost, skipped)
        return lost

    def length_of(self, r):
        """How many bytes this line holds, as well as it is known."""
        if r.reserve is not None:
            return r.reserve
        if r.bytes is not None and r.status not in ('unresolved', 'text'):
            return len(r.bytes)
        if r.op in ('DEFM', 'DM') and r.hexs and defm_len(r.args) > len(r.hexs) // 2:
            return None                 # the object column printed the string's first bytes only
        if r.hexs and len(r.hexs) % 2 == 0:
            return len(r.hexs) // 2
        if not r.hexs and r.addr is not None:
            return 0                    # ORG, EQU, END or a comment
        return None

    @staticmethod
    def fits_forward(recs, lens, i):
        """Does the next addressed line agree with this one's address plus its
        length?  When it does, the scan of this address is right and it is the
        run before it that is broken."""
        if recs[i].addr is None or lens[i] is None:
            return False
        run = 0
        for j in range(i, len(recs)):
            if lens[j] is None:
                return False
            if j > i and recs[j].addr is not None:
                return recs[j].addr == (recs[i].addr + run) & 0xFFFF
            run += lens[j]
        return False

    # -- 2. the listing's own symbols --------------------------------------
    def parse_sources(self):
        for r in self.recs:
            r.label, r.op, r.args, r.comment = split_source(r.src)
            r.col0 = r.addr

    def collect_symbols(self):
        """A label's value is its own line's address -- the listing defines its
        own symbol table, in the column that is hardest to misread.  It is
        rebuilt from scratch each round, because the addresses move."""
        self.symbols, self.inferred, self.disputed = {}, {}, {}
        for r in self.recs:
            if r.label and r.addr is not None and r.label not in self.symbols:
                self.symbols[r.label] = r.addr
        # An EQU names a value, not a place, and the listing prints that value
        # in the address column: two witnesses to the same number.
        for r in self.recs:
            if r.op not in ('EQU', 'DEFL') or not r.label:
                continue
            if getattr(r, 'equ_value', None) is not None:
                self.symbols[r.label] = r.equ_value    # settled by a use, an earlier round
                r.fargs = hexlit(r.equ_value)
                continue
            vals = []
            for args in mechanical(r.args):
                try:
                    v = asm.Expr(args, r.n).eval(self.symbols, r.addr or 0)
                except Exception:
                    continue
                if r.addr is None or v & 0xFFFF == r.addr:
                    self.symbols[r.label] = v
                    r.fargs = args
                    break
                vals.append(v & 0xFFFF)
            else:
                v = self.symbols.get(r.label)
                r.fargs = hexlit(v) if v is not None else r.args
                if v is not None and r.args != r.fargs:
                    r.note = join(r.note, 'equate %r->%s from the value column'
                                  % (r.args, r.fargs))
                near = [p for p in vals if v is not None
                        and ocr_distance('%04X' % p, '%04X' % v) <= 1.0]
                if near:
                    # The value column says 0A7EH, the operand 0A7FH: one
                    # witness each.  The value column stands for now, but
                    # DISPUTED: a source line that assembles only through
                    # this name cannot repair the hex with it, and a use in
                    # the code whose bytes hold the operand's value settles
                    # the equate that way (settle_equates).
                    self.disputed[r.label] = (r, near[0])
                    r.note = join(r.note, 'disputed: the operand reads %s' % hexlit(near[0]))

    def uses_disputed(self, args):
        return any(re.search(r'(?<![A-Z0-9_])%s(?![A-Z0-9_])' % re.escape(n), (args or '').upper())
                   for n in self.disputed)

    def settle_equates(self):
        """A disputed equate is settled by a line that names it and whose
        bytes, settled on the object column, hold the operand's value."""
        for r in self.recs:
            if getattr(r, 'equ_value', None) is not None:     # reconcile() wiped this round's notes
                r.note = join(r.note, 'equate settled as %s by its use in the code, against the value column'
                              % hexlit(r.equ_value))
        for name, (r, p) in list(self.disputed.items()):
            word = bytes((p & 0xFF, p >> 8))
            for x in self.recs:
                if x is r or not x.bytes or x.status not in CONFIDENT + ('hexonly',):
                    continue
                if word in x.bytes and any(close_enough(tok, name, 0.35) for tok in
                                           re.findall(r'[A-Z_@?][A-Z0-9_@?$]*', (x.args or '').upper())):
                    r.equ_value = p
                    r.note = join(r.note, 'settled as %s by its use at %04X' % (hexlit(p), x.addr))
                    del self.disputed[name]
                    break

    # -- 3/4. reconcile every line -----------------------------------------
    def reconcile(self):
        """No line is accepted on one witness.  The source column counts as a
        witness while it is read as printed (its hex literals put back into the
        hex alphabet is still as printed); once a word has to be replaced the
        repair is the hex column speaking, and the source is only a check on
        it."""
        for k in ('DATA statements agree', 'DATA statements disagree'):
            self.tally.pop(k, None)     # this round's count, not a running one
        for r in self.recs:
            r.note = ''
            # A line is text when it holds no object bytes: an equate, a
            # comment, a mnemonic the scan began with a mark or a digit
            # (`(ALL 0033H`, `1D HL,VIDEO`) on a line with none.  With
            # bytes in the object column it is a line of the program, and
            # goes on to be repaired or reported: called text, its bytes
            # vanished from the recovered source and the ROM-call tally,
            # and nothing said so (the 2026-09-19 audit, H-20).
            if r.op in ('EQU', 'DEFL') or (not r.hexs and (
                    (r.op is None and r.label is None)
                    or not re.match(r'^[A-Z]', r.op or ''))):
                r.status, r.bytes = 'text', b''
                continue
            if self.structural(r):
                continue
            self.reconcile_one(r, self.chain_length(r))

    def structural(self, r):
        """A line that emits no object bytes says so by leaving the hex column
        empty, and an ORG's operand is the address column itself -- so these
        need no third witness, only the shape of the line."""
        if r.hexs or not r.op:
            return False
        if r.reserve is not None:
            # a DEFS whose size two places on the line agree on (reserves):
            # it emits no object bytes to check, only moves the counter
            fill = asm.split_operands(mechanical(r.args or '')[-1], r.n)[1:]
            r.status, r.fop = 'clean', 'DEFS'
            r.fargs = ','.join([str(r.reserve)] + fill)
            r.bytes = b''
            return True
        if r.addr is None:
            # An END the assembler printed without an address (2990 END).
            if r.op == 'END' or (ocr_distance(r.op, 'END') <= 1.0 and not r.args):
                r.status, r.bytes, r.fop, r.fargs = 'clean', b'', 'END', ''
                return True
            return False
        if r.op in ('ORG', 'END'):
            r.status, r.bytes = 'clean', b''
            r.fop = r.op
            r.fargs = hexlit(r.addr) if r.op == 'ORG' else ''
            return True
        for word in ('ORG', 'END'):
            if ocr_distance(r.op, word) <= 1.5:
                args = hexlit(r.addr) if word == 'ORG' else ''
                if r.op != word:
                    r.note = join(r.note, 'source %r->%r' % (fieldtext(r.op, r.args),
                                                             fieldtext(word, args)))
                r.status = 'clean' if r.op == word else 'source'
                r.bytes, r.fop, r.fargs = b'', word, args
                return True
        # END with its entry label, the space between them lost: ENDZAP.
        if r.op.startswith('END') and not r.args and r.op[3:] in self.symbols:
            r.note = join(r.note, 'source %r->%r' % (r.op, 'END ' + r.op[3:]))
            r.status, r.bytes, r.fop, r.fargs = 'source', b'', 'END', r.op[3:]
            return True
        return False

    def reconcile_one(self, r, clen):
        reads = [h for h in hex_readings(r.rawhex) if len(h) % 2 == 0]
        hwants = [bytes.fromhex(h) for h in reads]
        # The DATA statements are one more reading of the object field, from
        # a column the scan damaged independently.  But a decimal token that
        # lost a digit is still a valid number, where a hex field that lost
        # one is not, so the DATA may speak for the object side only where the
        # hex column is unreadable or is these bytes scanned badly: a hex
        # field that reads cleanly as something else is not outvoted.  The
        # readings are tried best-supported first: what both columns say,
        # then what one says exactly and the other is a bad scan of, then
        # what the hex says against the DATA.
        dwants = [d for d in r.data if clen is None or clen == len(d)]
        both = [h for h in hwants if h in dwants]
        # The DATA may speak against a readable hex field only where it
        # cannot be read as what that field says, even allowing a digit lost
        # (a 6 where 64 is printed does not contradict 64), and where the
        # hex field is a bad scan of what the DATA says.
        consistent = both or any(self.near_dec(r, h, loose=True) for h in hwants)
        dnear = [] if hwants and consistent else \
            [d for d in dwants if d not in hwants and (not hwants or near_hex(r.rawhex, d))]
        hnear = [h for h in hwants if h not in dwants and (not dwants or self.near_dec(r, h))]
        wants = both + dnear + hnear + [h for h in hwants if h not in both and h not in hnear]
        if both:
            # Two object columns, scanned apart, agreeing exactly: no second
            # reading of the hex and no near-miss of the source outranks
            # that (SESBH for 5E58H, the hex 585E read as 5B5E to suit it).
            wants = both
        want = hwants[0] if hwants else (dwants[0] if dwants else None)
        plain = {w for w in (wants[:1] + hwants[:1] + dwants[:1]) if w in wants}
        r.conflict = False

        # (a) the source as printed.  It is a witness in its own right, so one
        # other column agreeing with it is enough: a reading of the object
        # field that IS these bytes, or one that is these bytes scanned badly,
        # or the DATA statements.  The address chain agrees only about the
        # LENGTH, which says nothing about the content, so it carries a line
        # only where the object field is unreadable and says nothing either.
        why, printed = None, None
        for op, args, tier in self.relabeled(source_candidates(r.op, r.args)):
            if tier:
                break
            b, err, missing = assemble_one(op, args, r.addr, self.symbols)
            if b is None and missing:
                args, b = self.resolve_name(r, op, args, missing[0], wants, clen)
            if b is None:
                why = why or err
                continue
            printed = printed or b
            if self.uses_disputed(args) and b not in (both or [want]):
                continue        # a disputed equate is no witness against the object column's first reading
            if re.fullmatch(r"'.'", args or '') and norm(args) != norm(unquote(r.args or '')):
                # The operand is a garbled token read as a quoted character
                # (‘Et, wT): the object column has to meet it exactly or by
                # shape, or the line is that column's reading alone.
                if not (b in wants or (not both and plausible_hex(r.rawhex, b))):
                    continue
            elif not (b in wants or (not both and near_hex(r.rawhex, b))
                      or (not wants and clen == len(b))):
                continue
            self.accept(r, op, args, b, 'clean' if b == want else 'hex')
            self.settle_data(r, hwants, dwants)
            return
        # (b) the object column speaks, one reading at a time and the plainest
        # first.  A repair that keeps the operand the page printed has to make
        # exactly those bytes, which is a real check on both columns at once; a
        # repair that takes the operand from the object column has no such
        # check, so the scanned line must still read as what it decodes to.
        for tier in (1, 2):
            for want in wants:
                if clen is not None and clen != len(want):
                    continue
                if tier == 2 and want not in plain:
                    continue        # one reading a column: nothing else vouches for it
                hint = def_hint(r.op, r.args, want) or from_hex(want, r.addr, self.symbols)
                for op, args, t in self.relabeled(source_candidates(r.op, r.args, hint)):
                    if t != tier:
                        continue
                    if tier == 2 and not supported(r, op, args):
                        continue
                    if tier == 1 and not carries_bytes(args) \
                            and ocr_distance(r.op or '', op) > 1.0:
                        continue    # the operand puts nothing of its own in
                    b, _, _ = assemble_one(op, args, r.addr, self.symbols)
                    if b != want:
                        continue
                    self.accept(r, op, args, b, 'source' if tier == 1 else 'hexonly')
                    if want not in hwants:
                        r.note = join(r.note, 'the bytes are the DATA statements\' reading'
                                      + ('' if not hwants else
                                         ', the hex %s scanned badly' % r.rawhex))
                    elif want != hwants[0]:
                        r.note = join(r.note, 'object field read as %s'
                                      % want.hex().upper())
                    self.settle_data(r, hwants, dwants)
                    return
        r.status, r.bytes = 'unresolved', None
        r.note = join(r.note, why or 'the source and the hex column disagree')
        for name, ws in (('the hex reads', hwants), ('the DATA statements read', dwants)):
            if ws:
                hint = from_hex(ws[0], r.addr, self.symbols)
                r.note = join(r.note, '%s %s%s' % (name, ws[0].hex().upper(),
                                                  (' = %r' % fieldtext(*hint)) if hint else ''))

    def settle_data(self, r, hwants, dwants):
        """The line is accepted; what do the DATA statements say about it?
        Agreeing with the hex column, they are the second witness to a line
        the object column alone had carried.  Disagreeing with a one-witness
        line they unsettle it -- one column against another, and the source
        says nothing.  Disagreeing with a two-witness line they cannot
        overturn it, but a human has to look: the loader was scanned wrong,
        or the book printed two versions."""
        if not dwants:
            return
        if r.bytes in dwants or self.near_dec(r, r.bytes):
            self.tally['DATA statements agree'] = self.tally.get('DATA statements agree', 0) + 1
            # Both object columns say so, one of them perhaps scanned badly:
            # that is two witnesses, as a hex field the source confirms is.
            if r.status == 'hexonly' and hwants \
                    and (r.bytes in hwants or plausible_hex(r.rawhex, r.bytes)):
                r.status = 'data'
                r.note = join(r.note, 'the DATA statements agree')
            return
        if r.dpos is not None and all(
                v in self.stream[r.dpos + k].cands or self.lost_digit(self.stream[r.dpos + k], v)
                for k, v in enumerate(r.bytes)):
            return          # a token that lost a digit (20 for 201) contradicts nothing; data_damage names it
        self.tally['DATA statements disagree'] = self.tally.get('DATA statements disagree', 0) + 1
        said = dwants[0].hex().upper()
        if r.status == 'hexonly':
            r.note = join(r.note, 'the object column reads %s but the DATA statements read %s'
                          % (r.bytes.hex().upper(), said))
            r.status, r.bytes = 'unresolved', None
            return
        r.conflict = True
        r.note = join(r.note, 'settled as %s but the DATA statements read %s'
                      % (r.bytes.hex().upper(), said))

    def accept(self, r, op, args, b, status):
        """Record the reading.  The SCANNED fields are never overwritten: a
        later round re-reads the page, not this round's repair of it, or a
        repair taken on two witnesses would come back as a clean line."""
        r.bytes, r.status, r.fop, r.fargs = b, status, op, args
        if status == 'hex':
            r.note = join(r.note, 'hex %s->%s' % (r.rawhex or '-', b.hex().upper()))
        if (op, args) != (r.op, r.args):
            r.note = join(r.note, '%s %r->%r'
                          % ('source' if status == 'source' else 'read',
                             fieldtext(r.op, r.args), fieldtext(op, args)))

    DIGITLED = re.compile(r'(?<![A-Z0-9])[0-9][A-Z0-9_@?$]*[A-Z_@?][A-Z0-9_@?$]*')

    def relabeled(self, cands):
        """The candidates, and after each one the same with an operand token
        that begins with a digit yet is no number read as the listing's label
        it is one slip from: 8UFFER is BUFFER.  A name whose first letter the
        scan turned into a digit is invisible to the symbol reader, which
        wants a letter first; this is resolve_name's rule (a scanned name
        close to exactly one label the listing defines is that label) for
        the tokens resolve_name never sees."""
        for op, args, tier in cands:
            yield op, args, tier
            if not args:
                continue
            fixed = args
            for m in self.DIGITLED.finditer(args.upper()):
                tok = m.group(0)
                if asm.number(tok) is not None or (tok.endswith('H') and as_hex(tok[:-1])):
                    continue
                near = sorted((ocr_distance(tok, n), n) for n in self.symbols
                              if n not in self.inferred and close_enough(tok, n, 0.35))
                if len(near) == 1 or (len(near) > 1 and near[0][0] < near[1][0]):
                    fixed = re.sub(r'(?<![A-Z0-9])%s(?![A-Z0-9])' % re.escape(tok),
                                   near[0][1], fixed, flags=re.I)
            if fixed != args:
                yield op, fixed, tier

    def resolve_name(self, r, op, args, name, wants, clen):
        """A name the line uses that nothing defines.  It is first read against
        the listing's own labels -- a scanned name close to a label the listing
        defines is that label, and the address the label sits at is a fact the
        source column never printed.  Only if no label is near it does the
        value come out of the object code."""
        near = sorted((ocr_distance(name, n), n) for n in self.symbols
                      if n != name and n not in self.inferred
                      and close_enough(name, n, 0.35))
        if len(near) == 1 or (len(near) > 1 and near[0][0] < near[1][0]):
            n = near[0][1]
            if not wants and near[0][0] > 1.0:
                return args, None   # nothing would check the substitution
            fixed = re.sub(r'(?<![A-Z0-9])%s(?![A-Z0-9])' % re.escape(name), n, args)
            b, _, _ = assemble_one(op, fixed, r.addr, self.symbols)
            if b is not None and (b in wants or near_hex(r.rawhex, b)
                                  or (not wants and clen == len(b))):
                r.note = join(r.note, '%s is the listing\'s %s' % (name, n))
                return fixed, b
        # No label is near it, so the object code has to say what it is worth.
        # A fitted value proves nothing by itself -- give it a free number and
        # any reading of the field can be made to work -- so the value has to
        # land somewhere the listing accounts for: a line of this very block,
        # or clear of the block altogether, where an outside routine or buffer
        # would be.  A reading that lands mid-instruction is the signature of
        # having fitted the damage, and is refused.
        for strict in (True, False):
            for want in wants:
                if clen is not None and clen != len(want):
                    continue
                b = self.infer(r, op, args, name, want, strict)
                if b is not None:
                    return args, b
        return args, None

    def plausible(self, v, target):
        """Is this a value the listing accounts for?  A branch or call must
        land on a line this listing prints -- the source named it, so the
        listing has to define it somewhere.  Anything else may point outside
        the listing, at a routine or a buffer, but not into the middle of an
        instruction of its own."""
        here = [x.addr for x in self.recs if x.addr is not None]
        if v in here:
            return True
        if target:
            return False
        spans = [x.addr for x in self.recs if x.addr is not None and x.bytes]
        return not spans or not (min(spans) <= v <= max(spans))

    def infer(self, r, op, args, name, want, strict=True):
        """A symbol the listing uses but does not define here has its value in
        the object code: assemble the line twice and read the field out of the
        hex.  The source still says what instruction this is; only the number
        comes from the object column, where the source never printed one."""
        a, _, _ = assemble_one(op, args, r.addr, dict(self.symbols, **{name: 0}))
        b, _, _ = assemble_one(op, args, r.addr, dict(self.symbols, **{name: 1}))
        if a is None or b is None or len(a) != len(want) or len(b) != len(a):
            return None
        pos = [i for i in range(len(a)) if a[i] != b[i]]
        if not pos or len(pos) > 2 or pos != list(range(pos[0], pos[0] + len(pos))):
            return None
        if len(pos) == len(a):
            # DEFB NAME, DEFW NAME: the name IS the whole encoding, so the
            # source witnessed nothing but the length, and the bytes would be
            # the object column's alone under a symbol the scan may well have
            # invented (DEFB wT).  One object column is what such a line is,
            # and the DEF hint reads it as that.
            return None
        base = int.from_bytes(bytes(a[i] for i in pos), 'little')
        got = int.from_bytes(bytes(want[i] for i in pos), 'little')
        v = (got - base) & ((1 << (8 * len(pos))) - 1)
        out, _, _ = assemble_one(op, args, r.addr, dict(self.symbols, **{name: v}))
        if out != want:
            return None
        ins = disasm.disassemble(want, r.addr)
        branch = len(ins) == 1 and ins[0].op is not None \
            and ins[0].op.kind in ('jump', 'call') and ins[0].target == v
        if not self.plausible(v, branch and strict):
            return None
        if self.inferred.get(name, v) != v:
            r.note = join(r.note, '%s reads %04XH here and %04XH earlier'
                          % (name, v, self.inferred[name]))
            return None
        self.inferred[name] = v
        self.symbols[name] = v
        r.note = join(r.note, '%s = %s from the object code' % (name, hexlit(v)))
        return out

    def chain_length(self, r):
        """The length the address column claims for this line, or None."""
        recs = [x for x in self.recs if x.addr is not None and (x.hexs or x.op == 'ORG')]
        for i, x in enumerate(recs):
            if x is r and i + 1 < len(recs):
                if getattr(recs[i + 1], 'gap', False):
                    return None         # lines the page lost lie between
                d = (recs[i + 1].addr - r.addr) & 0xFFFF
                return d if 0 < d <= 8 else None
        return None

    # -- 5. the recovered source, and the proof ----------------------------
    def recovered(self):
        out = ['; recovered by hexcheck from %s' % self.name]

        def stmt(label, op, args='', comment=''):
            """A source line; a label eight characters long still gets its space."""
            head = (label or '').ljust(8) if len(label or '') < 8 else label + ' '
            return (head + '%-8s%-16s%s' % (op, args, comment)).rstrip()

        # an EQU line is written out below whatever its status says, so its
        # label is defined here; counted as free as well it was defined
        # twice, which the assembler let pass until it checked EQU labels
        defined = {r.label for r in self.recs
                   if r.label and r.status != 'unresolved'
                   and (r.status != 'text' or r.op in ('EQU', 'DEFL'))}
        free = sorted(n for n in referenced(self.recs) if n not in defined)
        pc = None
        for r in self.recs:
            if r.status == 'unresolved':
                out.append('; UNRESOLVED %s' % r.raw.strip())
                continue
            if r.op in ('EQU', 'DEFL') and r.label:
                out.append(stmt(r.label, 'EQU', r.fargs or r.args))
                continue
            if r.status == 'text':
                if r.src.strip():
                    out.append(';%s' % r.src.strip().lstrip(';*').rstrip())
                continue
            if r.fop == 'END':
                continue
            if r.addr is not None and r.addr != pc and r.fop != 'ORG':
                out.append(stmt('', 'ORG', hexlit(r.addr)))
                pc = r.addr
            if r.fop == 'ORG':
                pc = r.addr
                out.append(stmt(r.label, 'ORG', hexlit(r.addr)))
                continue
            c = comment_of(r)
            if r.status == 'hexonly':
                c = (c + '  ' if c else ';') + '?? one object column alone'
            out.append(stmt(r.label, r.fop, r.fargs, c))
            pc = (pc or 0) + len(r.bytes or b'') + (r.reserve or 0)
        if free:
            out[1:1] = [stmt(n, 'EQU', hexlit(self.symbols[n]) if n in self.symbols else '0',
                             ';from the object code' if n in self.inferred else
                             ';defined where this listing does not' if n in self.symbols
                             else ';UNKNOWN -- the listing never says')
                        for n in free]
        out.append(stmt('', 'END'))
        return '\n'.join(out) + '\n'

    def verify(self):
        """Assemble what we recovered and require the reconciled bytes back."""
        res = asm.assemble(self.recovered())
        if res.errors:
            return ['%d: %s' % e for e in res.errors[:5]]
        image = {}
        for org, data in res.segments:
            for k, b in enumerate(data):
                image[org + k] = b
        bad = []
        for r in self.recs:
            if not r.bytes or r.addr is None:
                continue
            got = bytes(image.get(r.addr + k, 256) for k in range(len(r.bytes)))
            if got != r.bytes:
                bad.append('%04X: recovered %s, reconciled %s'
                           % (r.addr, got.hex().upper(), r.bytes.hex().upper()))
        return bad


def comment_of(r):
    """The scanned comment, with whatever the ';' was read as taken off it.
    Nothing checks a comment -- it carries no bytes -- so it is passed through
    otherwise untouched."""
    c = re.sub(r'^[^A-Za-z0-9\s]+', '', (r.comment or '').strip())
    c = re.sub(r'^[a-z](?=[A-Z])', '', c).strip()
    return (';' + c) if c else ''


def fieldtext(op, args):
    return ('%s %s' % (op or '?', args or '')).strip()


SYMBOL = re.compile(r"(?<![A-Z0-9])[A-Z_@?][A-Z0-9_@?$]*")


def referenced(recs):
    """The names an operand field uses.  The look-behind keeps the tail of a
    hex literal (the C00H of 3C00H) from reading as a symbol."""
    names = set()
    for r in recs:
        if getattr(r, 'status', None) in ('unresolved', 'text'):
            continue                    # a comment's words are not symbols
        text = r.fargs if getattr(r, 'fargs', None) is not None else r.args
        for m in SYMBOL.finditer((text or '').upper()):
            n = m.group(0)
            if n not in asm.REGS and n not in asm.CONDS and asm.number(n) is None:
                names.add(n)
    return names


# A token that is nothing but marks -- the column rule or a tab stop the scan
# read as '=', '©', '—', '«', '~=—' -- between two fields of the source.  What
# can begin an operand (a letter, a digit, a quote, a parenthesis, a sign, $)
# is never a mark.
MARKTOK = re.compile(r"""^[^\w'"‘’“”`´(+$-]+$""")


def unmarked(text):
    """The text with the mark tokens at its front taken off."""
    toks = text.split(None, 1)
    while toks and MARKTOK.match(toks[0]):
        text = toks[1] if len(toks) > 1 else ''
        toks = text.split(None, 1)
    return text


def as_op(tok, labelled=False):
    """The mnemonic a scanned field token is, or None.  Marks stuck to its
    front (—-EQu) come off.  After a label the token has no other place to
    be a mnemonic in, so one slip from a directive is taken as printed for
    the check to repair (t44 DEF 0846H), and one slip from EQU is EQU,
    because the address column holds the equate's value and checks it."""
    t = re.sub(r"^[^\w]+", '', tok).upper().rstrip(':,.')
    if t in asm.MNEMONICS or t in asm.DIRECTIVES:
        return t
    if labelled and t:
        if ocr_distance(t, 'EQU') <= 1.0:
            return 'EQU'
        if any(ocr_distance(t, d) <= 1.0 for d in ('DEFB', 'DEFW', 'DEFM', 'DEFS')):
            return t
    return None


def split_source(src):
    """(label, op, operand, comment) from a scanned source column."""
    s = src.strip()
    if not s or s[0] in ';*':
        return None, None, None, s
    parts = s.split(None, 1)
    first, rest = parts[0], (parts[1] if len(parts) > 1 else '')
    label = None
    if as_op(first) is None and rest:
        label = re.sub(r'[^A-Z0-9_@?$]', '', first.upper().rstrip(':'))
        nxt = unmarked(rest).split(None, 1)
        if nxt and as_op(nxt[0], labelled=True) is not None:
            first, rest = nxt[0], (nxt[1] if len(nxt) > 1 else '')
            op = as_op(first, labelled=True)
        else:
            label = None
            first, rest = parts[0], (parts[1] if len(parts) > 1 else '')
            op = first.upper().rstrip(':,.')
    else:
        op = as_op(first) or first.upper().rstrip(':,.')
    rest = unmarked(rest.lstrip())
    # The column rule glued to the operand ('=OATFH', '«=OATFH'): marks that
    # cannot begin an operand come off its front.
    rest = re.sub(r"""^[^\w'"‘’“”`´(+$-]+""", '', rest)
    args, comment = split_operand(rest)
    args = args.strip()
    if not re.fullmatch(r'''['"‘’`][,.]['"‘’`!t]?''', args):
        args = args.rstrip(',.')            # a quoted comma is the operand, not a stray mark
    return label, op, args, comment


def assemble_one(op, args, pc, symbols):
    """The bytes of one statement at pc: (bytes, error, names it needed and
    did not have).  The listing's own labels go in front of it as EQUs, so
    every line is assembled on its own and one bad line poisons no other."""
    if op is None or pc is None:
        return None, 'no instruction', []
    if op not in asm.MNEMONICS and op not in asm.DIRECTIVES:
        return None, 'not an instruction: %r' % op, []
    pre, missing = [], []
    for n in sorted(referenced([_Args(args)])):
        if n in symbols:
            pre.append('%s EQU %d' % (n, symbols[n]))
        else:
            missing.append(n)
    text = '\n'.join(pre) + '\n ORG %d\n %s %s\n' % (pc, op, args or '')
    res = asm.assemble(text)
    if res.errors:
        return None, res.errors[0][1], missing
    if not res.segments:
        return b'', None, missing
    org, data = res.segments[0]
    return (data, None, missing) if org == pc else (None, 'ORG moved', missing)


class _Args:
    def __init__(self, args):
        self.args = args


def quoted_len(args):
    """How many characters the string a DEFM operand holds runs to, as
    scanned -- to the closing quote, or to the end where the scan lost it."""
    m = re.search(r'''['"‘’`](.*?)(?:['"‘’`]|$)''', unquote(args or ''))
    return len(m.group(1)) if m else 0


def defm_len(args):
    """The fewest bytes a DEFM's printed operand claims: the quoted string's
    length, or, where the scan lost the opening quote (= INSERT '), the
    letters and digits it holds."""
    return max(quoted_len(args), len(re.findall(r'[A-Za-z0-9]', args or '')))


def byte_lit(c):
    """A byte as a DEFB operand: the character when it prints, else hex."""
    if 0x20 <= c < 0x7F and c != 0x27:
        return "'%s'" % chr(c)
    return '%s%02XH' % ('0' if c >= 0xA0 else '', c)


def def_hint(op, args, want):
    """(op, operand) for the bytes of a line whose printed mnemonic is a DEF
    directive or one slip from it (DEFH, DEFS for DEFB, DEF, OEFW): the
    directive that emits this many bytes, with the value read off the object
    column.  A disassembly says nothing useful about a table entry -- 8FA1
    is not ADC A,A then POP AF -- but the printed directive does.  Not for
    a DEFM whose printed string runs past the bytes the object column
    shows: the assembler printed a string's first bytes only, and nothing
    checks the rest."""
    if not op or not want:
        return None
    near = {d for d in ('DEFB', 'DEFW', 'DEFM', 'DEFS') if ocr_distance(op, d) <= 1.0}
    if not near:
        return None
    exact = op if op in near else None
    claimed = defm_len(args)
    if (exact == 'DEFM' and claimed > len(want)) or \
            (exact is None and re.search(r'''['"‘’`]''', args or '') and claimed > max(len(want), 3)):
        return None                     # a string longer than the bytes shown: a prefix

    prints = all(0x20 <= c < 0x7F and c != 0x27 for c in want)
    if len(want) == 1:
        return (exact if exact in ('DEFB', 'DEFM') else 'DEFB'), byte_lit(want[0])
    if exact == 'DEFM':
        # The page says a string; bytes that do not print as one are the
        # object column's damage, not a string of control codes.
        return ('DEFM', "'%s'" % want.decode('ascii')) if prints else None
    if len(want) == 2 and 'DEFW' in near:
        return 'DEFW', hexlit(int.from_bytes(want, 'little'))
    if 'DEFM' in near and prints:
        return 'DEFM', "'%s'" % want.decode('ascii')
    if 'DEFB' in near or 'DEFS' in near:
        return 'DEFB', ','.join(byte_lit(c) for c in want)
    return None


def from_hex(want, addr, symbols):
    """(op, operand) for bytes that decode as exactly one instruction, with a
    label put back where the listing names that address."""
    ins = disasm.disassemble(want, addr or 0)
    if len(ins) != 1 or ins[0].invalid or ins[0].length != len(want):
        return None
    op, _, args = ins[0].text.partition(' ')
    args = args.strip()
    if ins[0].target is not None:
        for name, v in sorted(symbols.items()):
            if v == ins[0].target:
                args = re.sub(r'(^|,)\(?[0-9][0-9A-F]*H\)?$',
                              lambda m: m.group(0).replace(
                                  re.sub(r'[()]', '', m.group(0).lstrip(',')), name), args)
                break
    return op, args


HEXTOKEN = re.compile(r'(?<![A-Z0-9])([0-9A-F%s][0-9A-F%s]*)H\b'
                      % (''.join(HEXFIX), ''.join(HEXFIX)), re.I)


NAMED = sorted(asm.REGS | asm.CONDS, key=len)


DEFDIRS = ('DEFB', 'DB', 'DEFM', 'DM', 'DEFW', 'DW', 'DEFS', 'DS')
# What the scan makes of a quote mark: the typographic quotes the OCR prefers,
# and the shapes an apostrophe takes on a poor page -- a '!' or a 't' after
# the character (‘Et, Nt, ‘s!), a 'w' before it (wT).
OPENQ = "'\"‘’`´w"
CLOSEQ = "'\"‘’`´!t"
QUOTED = re.compile(r'^[%s]?(.)[%s]?$' % (re.escape(OPENQ), re.escape(CLOSEQ)))


def unquote(a):
    """Typographic quotes back to the ones an assembler reads."""
    return a.replace('‘', "'").replace('’', "'").replace('`', "'").replace('´', "'") \
            .replace('“', '"').replace('”', '"')


def mechanical(args, op=None):
    """The operand field read again in the alphabets it is printed in: a hex
    literal holds hex digits, a register field holds a register name, a dash
    is a dash, a quote is a quote, and an instruction that takes no operand
    never had one -- the scan swallowed the comment's semicolon.  Each of
    these alphabets is a handful of symbols wide, so reading the scan back
    into one of them is still the source column as printed, not a guess
    about what it meant."""
    out = [args]
    if op is not None and () in asm.BY_MNEMONIC.get(op, []) and args:
        out.append('')
    if not args:
        return out
    q = unquote(args)
    if q != args:
        out.append(q)
    a = q.replace('~', '-').replace('—', '-').replace('–', '-')
    a = HEXTOKEN.sub(lambda m: (as_hex(m.group(1)) or m.group(1)) + 'H', a)
    a = re.sub(r'\s+', '', a)
    a = re.sub(r'(?<=[A-Z0-9)])[.;](?=[A-Z0-9(])', ',', a)      # the comma
    if a != args and a not in out:
        out.append(a)
    if len(a) == 1 and a in HEXFIX and HEXFIX[a] in HEXDIGITS:
        out.append(HEXFIX[a])                   # a bit or mode number
    if op in DEFDIRS:
        out += defined(a)
    pieces = a.split(',')
    for i, p in enumerate(pieces):
        for alt in as_named(p):
            out.append(','.join(pieces[:i] + [alt] + pieces[i + 1:]))
    b = out[-1] if len(out) > 1 else a
    if b.startswith('C') and b.endswith(')') and '(' not in b:
        out.append('(' + b[1:])                 # (HL) scanned as CHL)
    return out[:8]


def defined(a):
    """A DEF directive's operand, read again in the alphabets IT is printed
    in.  No register or condition can stand there, so a short token is a
    number or a quoted character: a character between the shapes of two
    quote marks is that character (‘Et is 'E'); a token of digit shapes is
    those digits (OO is 0); a token of hex digits with a letter among them
    and its H lost is that hex literal (OFF is 0FFH); a mark stuck to the
    front -- a paren that never closes, a dash where the column rule was --
    comes off.  The object column has to agree with the reading, as with
    every other, so a quote that was really a letter costs nothing but a
    line left to the one-column rule."""
    out = []
    m = QUOTED.match(a)
    if m and len(a) >= 2 and m.group(1) not in OPENQ + CLOSEQ:
        out.append("'%s'" % m.group(1))
    if a and not a.startswith("'"):
        d = fix_field(a, DIGFIX)
        if d and d.isdigit() and d != a:
            out.append(d)
        if re.fullmatch(r'[A-F][0-9A-F]{1,3}H', a):
            out.append('0' + a)         # BEB8H: the leading zero the scan lost
        # NOT a hex literal that lost its H: `ao` for a garbled ' ' reads as
        # 0A0H that way, and the object column's 20 is one slip from A0.
    if a[:1] in '(-' and a[1:] and (a[0] == '-' or ')' not in a):
        out += [a[1:]] + defined(a[1:])
    return out


def as_named(piece):
    """A one- or two-character operand read as the register or condition it
    looks like.  That alphabet is two dozen names wide, so a shape that is not
    one of them and is one slip from exactly one of them is that one."""
    inner = piece[1:-1] if piece.startswith('(') and piece.endswith(')') else piece
    if len(inner) > 2 or inner in asm.REGS or inner in asm.CONDS:
        return []
    if inner.upper() in asm.REGS or inner.upper() in asm.CONDS:
        return [piece.replace(inner, inner.upper())]
    if len(inner) == 1 and HEXFIX.get(inner, '') in HEXDIGITS:
        return [piece.replace(inner, HEXFIX[inner])]    # a bit or mode number
    near = [n for n in NAMED
            if len(n) == len(inner) and ocr_distance(inner, n) <= 1.0]
    return [piece.replace(inner, near[0])] if len(near) == 1 else []


def source_candidates(op, args, hint=None):
    """(op, operand, tier) worth assembling, keeping the most of what the page
    says first.  The tier says how much of the reading is still the source's:

        0  both fields as printed, read back into their own alphabets
        1  the OPERAND as printed, the mnemonic from the object column
        2  the operand from the object column -- the source only vouches
           for it, because bytes that came out of the hex must match it
    """
    seen = set()

    def give(o, a, tier):
        if o and (o, a) not in seen:
            seen.add((o, a))
            return [(o, a, tier)]
        return []

    out = []
    for a in mechanical(args, op):
        out += give(op, a, 0)
    if hint is not None:
        hop, hargs = hint
        for a in mechanical(args, hop):
            out += give(hop, a, 1)
    if op:
        # A mnemonic one slip from the printed one, with the operand as
        # printed.  The bytes it makes are checked against the object
        # column whether or not those bytes decode as an instruction: a
        # DEFW table's entries do not, and DEFH for DEFW is the commonest
        # slip on such a page.
        for m in MNEMONICS:
            if m != op and ocr_distance(op, m) <= 1.0:
                for a in mechanical(args, m):
                    out += give(m, a, 1)
    if hint is not None:
        out += give(op, hargs, 2)
        out += give(hop, hargs, 2)
    return out


def norm(s):
    return re.sub(r'\s+', '', (s or '').upper())


def supported(r, op, args):
    """Does the scanned source still say this, allowing for the scan?  One of
    its two fields must survive the repair unchanged, or the whole line must
    still read as a damaged copy of it."""
    if r.args and norm(args) in {norm(a) for a in mechanical(r.args, op)}:
        return True                 # the operand is as printed; the hex names the instruction
    if r.op and norm(op) == norm(r.op):
        return True                 # the mnemonic is as printed; the hex holds the value
    return close_enough(fieldtext(r.op, r.args), fieldtext(op, args))


def join(note, more):
    return (note + '; ' + more).strip('; ') if note else more


# ---- report ------------------------------------------------------------------
ORDER = ['clean', 'hex', 'source', 'data', 'hexonly', 'text', 'unresolved']
LABEL = {'clean': 'clean',
         'hex': 'repaired the hex from the source',
         'source': 'repaired the source from the hex',
         'data': 'object column, and the DATA agrees',
         'hexonly': 'READ FROM ONE OBJECT COLUMN ALONE',
         'text': 'no object bytes',
         'unresolved': 'UNRESOLVED'}
MARK = {'unresolved': '!', 'hexonly': '?'}


def report(block, verbose, out=sys.stdout):
    """Write the block's report; returns (counts by status, problems), where
    the problems are what a human must look at beyond the unresolved lines:
    two-witness lines the DATA contradicts."""
    counts = {k: 0 for k in ORDER}
    for r in block.recs:
        counts[r.status] = counts.get(r.status, 0) + 1
    out.write('%s: %d lines, %d bytes\n'
              % (block.name, len(block.recs),
                 sum(len(r.bytes or b'') for r in block.recs)))
    for k in ORDER:
        if counts[k]:
            out.write('  %-34s %4d\n' % (LABEL[k], counts[k]))
    for k, v in sorted(block.tally.items()):
        if v:
            out.write('  %-34s %4d\n' % (k, v))
    if block.stream is not None:
        out.write('  DATA statements at lines %d-%d%s; their first value is address %04X\n'
                  % (block.stream[0].n, block.stream[-1].n,
                     ' (hex pairs)' if block.stream[0].hex else '',
                     (block.dbase - block.doff) & 0xFFFF))
    conflicts = 0
    for r in block.recs:
        note = join(r.anote, r.note)
        conflicts += r.conflict
        if r.status in MARK or r.conflict or (verbose and note):
            out.write('  %s %-5s %s\n' % ('#' if r.conflict else MARK.get(r.status, ' '),
                                          '%04X' % r.addr if r.addr is not None else '----',
                                          note or r.raw.strip()))
            if r.status == 'unresolved':
                out.write('        scanned: %s\n' % r.raw.strip())
    for text, matters in block.data_damage():
        if matters or verbose:
            out.write('  %s %s\n' % ('#' if matters else ' ', text))
    return counts, conflicts


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog='python3 tools/hexcheck.py',
        description='Check and repair a scanned assembly listing against its own hex column.')
    ap.add_argument('file', help='the text holding the listing (prose around it is skipped)')
    ap.add_argument('--out', metavar='DIR', help='write each block\'s recovered source here')
    ap.add_argument('--block', type=int, metavar='N', help='check only block N (1-based)')
    ap.add_argument('--min-lines', type=int, default=4, metavar='N',
                    help='the shortest run of listing lines taken for a block (default 4)')
    ap.add_argument('-v', '--verbose', action='store_true', help='name every repair')
    a = ap.parse_args(argv)

    with open(a.file, 'rb') as f:
        text = f.read().decode('utf-8', 'replace')
    blocks = find_blocks(text, a.min_lines)
    if not blocks:
        sys.stderr.write('%s: no listing found\n' % a.file)
        return 2
    streams = find_data(text)
    if a.out:
        os.makedirs(a.out, exist_ok=True)
    # --block past the end skipped every block and reported "0 lines: 0
    # clean, 0 repaired, 0 unresolved", exit 0 -- a silent pass for a
    # block that is not there, which is the wrong answer to a typo (the
    # 2026-09-19 audit, L-68).  `a.block and` also let --block 0 through
    # to check everything, since 0 is falsy and the numbering is 1-based.
    if a.block is not None and not 1 <= a.block <= len(blocks):
        sys.stderr.write('%s: --block %d: the file has %d block(s)\n'
                         % (a.file, a.block, len(blocks)))
        return 2
    total = {k: 0 for k in ORDER}
    bad = 0
    for i, recs in enumerate(blocks, 1):
        if a.block is not None and i != a.block:
            continue
        b = Block(recs, '%s block %d (lines %d-%d)'
                  % (os.path.basename(a.file), i, recs[0].n, recs[-1].n), streams)
        b.run()
        counts, conflicts = report(b, a.verbose, sys.stdout)
        for k in ORDER:
            total[k] += counts.get(k, 0)
        bad += counts.get('unresolved', 0) + conflicts
        problems = b.verify()
        for p in problems:
            sys.stdout.write('  ! re-assembly: %s\n' % p)
        bad += len(problems)
        if a.out:
            path = os.path.join(a.out, 'block%02d.asm' % i)
            with open(path, 'w') as f:
                f.write(b.recovered())
            sys.stdout.write('  -> %s\n' % path)
    seen = sum(total.values())
    sys.stdout.write('%d lines: %d clean, %d repaired, %d unresolved\n'
                     % (seen, total['clean'],
                        total['hex'] + total['source'] + total['data'],
                        total['unresolved']))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
