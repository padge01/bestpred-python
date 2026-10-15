"""Write the test fixtures in tests/data from a reference build (tools/reference.sh OUTDIR).

    python tools/make_fixtures.py OUTDIR

Saves random Format 4 records, the Fortran's outputs for them under several settings (and the daily curves for a
few), and a sample of the C age factors, so the tests run without a Fortran compiler.
"""

import random
import subprocess
import sys
from pathlib import Path

import compare

CONFIGS = ['default', 'single-trait', 'mt-all-four', 'old-3x', 'laclen-330', 'linear-curves', 'season-curves',
           'region-season-curves', 'kilograms']
N_RECORDS = 40
N_DAILY = 4


def main(refdir: str) -> None:
    data = Path(__file__).resolve().parents[1] / 'tests' / 'data'
    data.mkdir(parents=True, exist_ok=True)
    rng = random.Random(2026)
    records = [compare.random_record(rng) for _ in range(N_RECORDS)]
    (data / 'records.dat').write_text('\n'.join(records) + '\n')
    driver = str(Path(refdir, 'driver').resolve())
    for name in CONFIGS:
        rows = compare.run_fortran(driver, records, compare.CONFIGS[name])
        lines = [' '.join(repr(float(v)) for v in main_row) for main_row, _ in rows]
        (data / f'ref_{name}.txt').write_text('\n'.join(lines) + '\n')
        if name == 'default':
            daily = [' '.join(repr(float(v)) for v in d) for _, d in rows[:N_DAILY]]
            (data / 'ref_default_daily.txt').write_text('\n'.join(daily) + '\n')
    ages = subprocess.run([str(Path(refdir, 'agedriver'))], cwd=refdir, capture_output=True, text=True,
                          check=True).stdout.splitlines()
    (data / 'ref_ages.txt').write_text('\n'.join(ages[::20]) + '\n')
    print(f'fixtures written to {data}')


if __name__ == '__main__':
    main(sys.argv[1])
