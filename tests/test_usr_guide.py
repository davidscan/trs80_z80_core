"""WRITING_USR.md's examples, assembled and run, and tools/usr_speed.py's programs.

Every `<!-- example: NAME.asm -->` block in the guide is assembled; its
`NAME.bas` block's DATA lines must be exactly those bytes, POKEd at the
source's ORG and with the USR vector set to it; the listing is run by
the interpreter with this core and TRS80_USR=strict, and its stdout must
be the `<!-- expect: NAME -->` block. The tone example is measured in
the WAV it writes. usr_speed.py's routines are assembled from source
here, so a hand-counted byte there fails too.

Needs trs80basic beside this repo; Z80_INTERP_REQUIRE=1 (CI) makes its
absence a failure instead of a skip.
"""
import os
import re
import statistics
import struct
import subprocess
import sys
import tempfile
import unittest
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE = os.path.join(ROOT, 'WRITING_USR.md')
BASIC = os.path.join(os.path.dirname(ROOT), 'trs80basic', 'basic')
REQUIRE = os.environ.get('Z80_INTERP_REQUIRE') == '1'
CLOCK = 1774080

sys.path.insert(0, os.path.join(ROOT, 'tools'))
import usr_speed                                          # noqa: E402


def blocks():
    with open(GUIDE) as fh:
        text = fh.read()
    out = {}
    for kind, name, body in re.findall(r'<!-- (example|expect): (\S+) -->\n```[a-z]*\n(.*?)```',
                                       text, re.S):
        out[name if kind == 'example' else name + '.out'] = body
    return out


def assemble(source, tmp):
    src, obj = os.path.join(tmp, 'r.asm'), os.path.join(tmp, 'r.bin')
    with open(src, 'w') as fh:
        fh.write(source)
    r = subprocess.run([sys.executable, '-m', 'z80.asm', src, '-o', obj], cwd=ROOT,
                       capture_output=True, text=True)
    if r.returncode:
        raise AssertionError('does not assemble: ' + r.stderr)
    with open(obj, 'rb') as fh:
        return list(fh.read())


def run_basic(listing, tmp, env_extra=None):
    path = os.path.join(tmp, 'prog.bas')
    with open(path, 'w') as fh:
        fh.write(listing)
    env = {k: v for k, v in os.environ.items() if not k.startswith('TRS80_')}
    env.update(TRS80_Z80='%s %s' % (sys.executable, os.path.join(ROOT, 'core.py')),
               TRS80_USR='strict', TRS80_DUMB='1')
    env.update(env_extra or {})
    return subprocess.run([BASIC, path], stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, env=env, cwd=tmp, timeout=120)


class Guide(unittest.TestCase):
    def setUp(self):
        if not os.path.isfile(BASIC):
            if REQUIRE:
                self.fail('Z80_INTERP_REQUIRE=1 and no trs80basic at %s' % BASIC)
            self.skipTest('no trs80basic beside this repo')

    def test_every_example_is_assembled_loaded_and_run(self):
        b = blocks()
        names = sorted(n[:-4] for n in b if n.endswith('.asm'))
        self.assertEqual(names, ['fill', 'sum', 'tone', 'upper'], 'the guide lost or gained an example')
        for name in names:
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                src, bas = b[name + '.asm'], b[name + '.bas']
                org = int(re.search(r'ORG\s+([0-9A-F]+)H', src).group(1), 16)
                data = [int(x) for line in re.findall(r'DATA (.*)', bas) for x in line.split(',')]
                self.assertEqual(data, assemble(src, tmp), 'DATA is not the assembled source')
                base = int(re.search(r'POKE (-?\d+)\+I,B', bas).group(1))
                self.assertEqual(base % 65536, org, 'the loader POKEs somewhere else')
                lo, hi = re.search(r'POKE 16526,(\d+): POKE 16527,(\d+)', bas).groups()
                self.assertEqual(int(lo) + 256 * int(hi), org, 'the USR vector is not the entry')
                wav = os.path.join(tmp, 'out.wav')
                r = run_basic(bas, tmp, {'TRS80_SOUND_WAV': wav} if name == 'tone' else None)
                self.assertEqual((r.returncode, r.stderr), (0, ''), name)
                if name + '.out' in b:
                    self.assertEqual(r.stdout, b[name + '.out'])
                if name == 'tone':
                    self.check_tone(wav)

    def check_tone(self, path):
        """Two tones, D = 100 then 50, 400 cycles each, at 26*D+60 T-states a cycle."""
        w = wave.open(path)
        rate, n = w.getframerate(), w.getnframes()
        s = struct.unpack('<%dh' % n, w.readframes(n))
        ups = [i for i in range(1, n) if s[i - 1] < 0 <= s[i]]
        periods = [b - a for a, b in zip(ups, ups[1:])]
        self.assertGreater(len(periods), 790, 'fewer cycles than the two tones play')
        for p, d in ((periods[5:390], 100), (periods[410:-5], 50)):
            want = CLOCK / (26 * d + 60)
            got = rate / statistics.mean(p)
            self.assertLess(abs(got - want) / want, 0.001, 'D=%d: %.2f Hz, want %.2f' % (d, got, want))
        self.assertAlmostEqual(n / rate, 400 * (2660 + 1360) / CLOCK, delta=0.02)


class SpeedTool(unittest.TestCase):
    def setUp(self):
        if not os.path.isfile(BASIC):
            if REQUIRE:
                self.fail('Z80_INTERP_REQUIRE=1 and no trs80basic at %s' % BASIC)
            self.skipTest('no trs80basic beside this repo')

    def test_routines_are_the_assembled_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            fill = blocks()['fill.asm'].replace('0F000H', '0F010H')
            self.assertEqual(usr_speed.FILL, assemble(fill, tmp))
            spin = ('        ORG 0F030H\n        CALL 0A7FH\nLOOP    LD B,0\nIN      DJNZ IN\n'
                    '        DEC HL\n        LD A,H\n        OR L\n        JR NZ,LOOP\n        RET\n')
            self.assertEqual(usr_speed.SPIN, assemble(spin, tmp))
            self.assertEqual(usr_speed.RET, [201])

    def test_every_case_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            for case in ('stmt', 'call_base', 'call', 'fill_basic', 'fill_usr', 'spin'):
                with self.subTest(case):
                    dt, steps = usr_speed.run(BASIC, case, 2, tmp)
                    self.assertGreater(steps, 0)


if __name__ == '__main__':
    unittest.main()
