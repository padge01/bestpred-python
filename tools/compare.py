"""Compare the Python port with USDA's Fortran on random lactations.

    python tools/compare.py --driver path/to/driver --n 300

The driver (tools/driver.f90, built against USDA's sources by tools/reference.sh) runs in a temporary folder with a
bestpred.par written for each configuration below. Every output is compared; the run fails if any differs by more
than the tolerance.
"""

import argparse
import random
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from bestpred import Format4, Settings, run_format4  # noqa: E402

# States with a region for every breed in the age-factor tables (USDA state codes).
STATES = [11, 12, 13, 14, 15, 16, 21, 22, 23, 31, 32, 33, 34, 35, 41, 42, 43, 45, 46, 47, 48, 50, 51, 52, 54, 55,
          56, 57, 58, 61, 63, 64, 65, 71, 72, 73, 74, 81, 82, 83, 84, 85, 86, 87, 88, 91, 92, 93, 94, 95, 96]

CONFIGS = {
    'default': {},
    'single-trait': {'mtrait': 1, 'GLOBALmtrait': 1},
    'mt-all-four': {'mtrait': 4, 'GLOBALmtrait': 4},
    'no-3x': {'use3X': 0},
    'old-3x': {'use3X': 1},
    'new-3x': {'use3X': 2},
    'laclen-365': {'laclen': 365},
    'laclen-330': {'laclen': 330},
    'linear-curves': {'INTmethod': "'L'", 'INTmethodSCS': "'L'"},
    'season-curves': {'INTmethod': "'C'", 'INTmethodSCS': "'D'"},
    'region-curves': {'INTmethod': "'R'", 'INTmethodSCS': "'S'"},
    'region-season-curves': {'INTmethod': "'T'", 'INTmethodSCS': "'U'"},
    'kilograms': {'UNITSin': "'K'", 'UNITSout': "'K'"},
}

PAR = """&bestpred
  laclen = {laclen}
  maxlen = 365
  dailyfreq = 1
  plotfreq = 6
  use3X = {use3X}
  mtrait = {mtrait}
  GLOBALmtrait = {GLOBALmtrait}
  GRAFplot(1) = 0
  GRAFplot(2) = 0
  GRAFplot(3) = 0
  GRAFplot(4) = 0
  UNITSin = {UNITSin}
  UNITSout = {UNITSout}
  PERSfloor = -9.99
  PERSceiling = 9.99
  source = 10
  breed11 = 4
  breedUNK = 4
  WRITEcurve = 0
  CURVEfile = 'cowcurve'
  CURVEsmall = 0
  CURVEsingle = 0
  WRITEdata = 0
  DATAfile = 'cowdata'
  INfile = 'pcdart.bpi'
  OUTfile = 'pcdart.bpo'
  maxprnt = 0
  ONscreen = 0
  obs = 99999999
  maxshow = 0
  maxtd = 50
  INTmethod = {INTmethod}
  INTmethodSCS = {INTmethodSCS}
  DEBUGparms = 0
  DEBUGmsgs = 0
  dim0(1) = 115
  dim0(2) = 115
  dim0(3) = 150
  dim0(4) = 155
  dim0(5) = 161
  dim0(6) = 152
  dim0(7) = 159
  dim0(8) = 148
  dim0flag = 0
  LOGon = 0
  LOGfile = 'example'
  LOGfreq = 0
  region = 1
  season = 1
/
"""


def par_text(over: dict) -> str:
    values = {'laclen': 305, 'use3X': 3, 'mtrait': 3, 'GLOBALmtrait': 3, 'UNITSin': "'P'", 'UNITSout': "'P'",
              'INTmethod': "'W'", 'INTmethodSCS': "'G'"}
    values.update(over)
    return PAR.format(**values)


def settings_for(over: dict) -> Settings:
    unq = lambda v: v.strip("'")  # noqa: E731
    return Settings(mtrait=over.get('mtrait', 3), use3X=over.get('use3X', 3), laclen=over.get('laclen', 305),
                    method=unq(over.get('INTmethod', 'W')), method_scs=unq(over.get('INTmethodSCS', 'G')),
                    units_in=unq(over.get('UNITSin', 'P')), units_out=unq(over.get('UNITSout', 'P')))


def random_record(rng: random.Random) -> str:
    breed = rng.choice('ABGHJMHHHHJX')
    cowid = f'{breed}{"OUSA"}{rng.randrange(10 ** 12):012d}'
    parity = rng.choice([1, 1, 2, 2, 3, 4, 5, 6, 7, 9, 0])
    fresh_year = rng.randrange(1980, 2026)
    fresh = f'{fresh_year}{rng.randrange(1, 13):02d}{rng.randrange(1, 29):02d}'
    age_months = rng.randrange(20, 48) + 13 * max(parity - 1, 0)
    birth_year = fresh_year - age_months // 12
    birth = '        ' if rng.random() < 0.05 else f'{birth_year}{rng.randrange(1, 13):02d}{rng.randrange(1, 29):02d}'
    state = rng.choice(STATES)
    herd = f'{state:02d}{rng.randrange(10 ** 6):06d}'
    if rng.random() < 0.15:
        me = (0, 0, 0)
        dev = (0, 0, 0)
    else:
        me = (rng.randrange(14000, 34000), rng.randrange(500, 1300), rng.randrange(450, 1050))
        dev = (rng.randrange(-4000, 4000), rng.randrange(-150, 150), rng.randrange(-120, 120))
    doprev = rng.choice([0, 0, rng.randrange(1, 400)])
    # Test days: about monthly, some gaps, duplicates, out-of-order, LER segments and tests past 365 days.
    ntd = rng.choice([0, 1, 2, 3, 5, 8, 10, 11, 12, 13, 15])
    day = rng.randrange(3, 40)
    segs, dims = [], []
    for _ in range(ntd):
        dim = day
        if rng.random() < 0.05 and dims:
            dim = rng.choice(dims)  # duplicate
        dims.append(dim)
        mrd = 1 if rng.random() < 0.85 else rng.randrange(2, 12)
        xmilk = rng.choice([2, 2, 2, 3, 3, 1, 4])
        weigh = rng.choice([xmilk, xmilk, xmilk, 1, 0]) if xmilk > 1 else xmilk
        sample = rng.choice([xmilk, xmilk, 1, 0, 2])
        sup = rng.choice([1, 1, 1, 1, 2, 2, 3, 6, 7, 8, 0, 4])
        status = rng.choice([0, 0, 0, 0, 0, 0, 2, 3])
        t = max(dim, 1)
        milk = max(5., 70 * t ** 0.2 * np.exp(-0.003 * t) * rng.uniform(0.6, 1.4) - 40)
        milk = min(milk, 999.)
        fat = rng.uniform(2.4, 5.6) if rng.random() < 0.95 else 0.
        prot = rng.uniform(2.4, 4.2) if rng.random() < 0.9 else 0.
        scs = rng.uniform(0., 9.9) if rng.random() < 0.9 else 0.
        segs.append(f'{dim:3d}{sup}{status}{xmilk}{weigh}{sample}{mrd:2d}100{round(milk * 10):04d}'
                    f'{round(fat * 10):02d}{round(prot * 10):02d}{round(scs * 10):02d}')
        day += rng.choice([20, 28, 30, 31, 33, 35, 45, 60])
    if rng.random() < 0.1:
        rng.shuffle(segs)
    last = max(dims, default=0)
    length = last if rng.random() < 0.7 else min(last + rng.randrange(0, 60), 999)
    r = [' '] * 248
    def put(col, text):  # noqa: E306
        r[col - 1:col - 1 + len(text)] = list(text)
    put(3, cowid)
    put(71, birth)
    put(107, herd)
    put(128, fresh)
    put(136, f'{length:3d}')
    put(159, f'{parity:2d}')
    put(188, f'{me[0]:5d}{me[1]:4d}{me[2]:4d}{dev[0]:6d}{dev[1]:5d}{dev[2]:5d}')
    put(246, f'{doprev:3d}')
    return ''.join(r) + f'{ntd:2d}' + ''.join(segs)


def run_fortran(driver: str, records: list, over: dict) -> list:
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, 'bestpred.par').write_text(par_text(over))
        Path(tmp, 'adjust.scs').write_text((Path(__file__).resolve().parents[1] / 'src/bestpred/data/adjust.scs')
                                           .read_text())
        Path(tmp, 'in.dat').write_text('\n'.join(records) + '\n')
        methods = [over.get('INTmethod', "'W'").strip("'"), over.get('INTmethodSCS', "'G'").strip("'")]
        out = subprocess.run([driver, 'in.dat', *methods], cwd=tmp, capture_output=True, text=True,
                             check=True).stdout
    rows = [line.split()[1:] for line in out.splitlines() if line.startswith(('R ', 'D '))]
    return [(np.array(rows[k], dtype=float), np.array(rows[k + 1], dtype=float)) for k in range(0, len(rows), 2)]


def python_row(rec: Format4, settings: Settings):
    r = run_format4(rec, settings)
    main = np.concatenate([[r.dcr_milk, r.dcr_components, r.dcr_scs], r.yldvec[0], r.yldvec[1], r.persistency,
                           r.rel_yield, r.rel_persistency, r.yvec[0], r.yvec[1], r.herdavg, r.bump])
    daily = r.daily_bp[:, :, 1:].transpose(2, 1, 0).reshape(-1)  # (day, trait, me/actual) as Fortran prints it
    return main, daily


def close(a: np.ndarray, b: np.ndarray, rtol: float, atol: float) -> np.ndarray:
    both_nan = np.isnan(a) & np.isnan(b)
    return both_nan | np.isclose(a, b, rtol=rtol, atol=atol)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--driver', required=True)
    ap.add_argument('--n', type=int, default=200)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--config', action='append')
    ap.add_argument('--rtol', type=float, default=2e-5)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    records = [random_record(rng) for _ in range(args.n)]
    failed = 0
    for name in args.config or list(CONFIGS):
        over = CONFIGS[name]
        ref = run_fortran(str(Path(args.driver).resolve()), records, over)
        settings = settings_for(over)
        worst, bad = 0., 0
        for k, (record, (fmain, fdaily)) in enumerate(zip(records, ref)):
            pmain, pdaily = python_row(Format4.parse(record), settings)
            ok_main = close(pmain, fmain, args.rtol, 1e-6)
            ok_daily = close(pdaily, fdaily, args.rtol, 1e-5)
            if not (ok_main.all() and ok_daily.all()):
                bad += 1
                if bad <= 3:
                    idx = np.where(~ok_main)[0]
                    print(f'  {name} record {k}: main fields {idx.tolist()[:12]} py {pmain[idx][:6]} f {fmain[idx][:6]}'
                          f' | daily mismatches {int((~ok_daily).sum())}')
            with np.errstate(divide='ignore', invalid='ignore'):
                rel = np.abs(pmain - fmain) / np.maximum(np.abs(fmain), 1e-6)
            worst = max(worst, float(np.nanmax(np.where(np.isfinite(rel), rel, 0.))))
        print(f'{name:22s} {len(records)} records, {bad} differ, worst relative difference {worst:.2e}')
        failed += bad
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
