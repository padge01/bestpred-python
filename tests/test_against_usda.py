"""The port against outputs of USDA's own program (tests/data, written by tools/make_fixtures.py)."""

from pathlib import Path
import sys

import numpy as np
import pytest

from bestpred import Format4, aiplage, adjscs, run_format4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import compare  # noqa: E402

DATA = Path(__file__).parent / 'data'
RECORDS = [Format4.parse(line) for line in (DATA / 'records.dat').read_text().splitlines() if line.strip()]
CONFIGS = sorted(p.stem[4:] for p in DATA.glob('ref_*.txt') if p.stem not in ('ref_ages', 'ref_default_daily'))
# Single-precision pow and exp differ in the last bit between platforms (macOS vs Linux, NumPy builds), which moves
# results by up to about 1e-7; on the machine that built the reference they agree to 1e-11.
RTOL = 1e-5


def reference(name):
    return [np.array(line.split(), dtype=float) for line in (DATA / f'ref_{name}.txt').read_text().splitlines()]


@pytest.mark.parametrize('name', CONFIGS)
def test_lactations_match_usda(name):
    settings = compare.settings_for(compare.CONFIGS[name])
    for k, (rec, expected) in enumerate(zip(RECORDS, reference(name))):
        got, _ = compare.python_row(rec, settings)
        ok = compare.close(got, expected, RTOL, 1e-6)
        assert ok.all(), f'record {k}: fields {np.where(~ok)[0].tolist()} got {got[~ok]} want {expected[~ok]}'


def test_daily_curves_match_usda():
    settings = compare.settings_for({})
    lines = (DATA / 'ref_default_daily.txt').read_text().splitlines()
    for k, line in enumerate(lines):
        expected = np.array(line.split(), dtype=float)
        _, got = compare.python_row(RECORDS[k], settings)
        assert compare.close(got, expected, RTOL, 1e-5).all(), f'record {k}'


def test_age_factors_match_usda_exactly():
    for line in (DATA / 'ref_ages.txt').read_text().splitlines():
        b, age, year, month, parity, state, doprev, base, m, f, p, scs = line.split()
        got = aiplage(b, int(age), int(year), int(month), int(parity), int(state), int(doprev), int(base))
        assert got == (float(m), float(f), float(p)), line
        assert adjscs(b, int(parity), int(month), int(state), int(age)) == int(scs), line


def test_usda_example_record():
    """The record shipped with BESTPRED (format4.dat) gives the line USDA's program writes for it."""
    from bestpred.format4 import results_line, with_length_from_tests
    rec = with_length_from_tests(Format4.parse((DATA / 'usda_format4.dat').read_text()))
    line = results_line(rec, run_format4(rec))
    assert line == ('HOUSA00093WNM4798 19940117 192   96.  96.  99. 27817.  1025.  2483.   2.49 32404.  1211.  2923.'
                    '   2.54 27817.  1025.  2483.   2.49 17828.   646.  1568.   2.46  0.20  0.31  2.27 -0.09 0.92 0.93'
                    ' 0.92 0.93 0.66 0.63 0.41 0.49 27843.  1027.  2636.  -0.00 27505.  1004.   656.   3.20  0.0000'
                    ' 0.0000 0.0000     0.66')
