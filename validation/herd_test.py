"""How well does best prediction project a lactation from its early tests? Checked against daily meter weights.

    python validation/herd_test.py daily.csv --end 305 --out results/

`daily.csv` has one row per cow-day: cow, parity, breed, birth_date, fresh_date, dim, milk (lb). Lactations weighed
from the start (first weight by day 5) to `--end`, with most days present, are kept. Their true yield is the sum of
the daily weights to `--end` (missing days interpolated). Monthly test days are drawn from the same weights, as a
DHI tester would see them, and the yield to `--end` is projected from the tests up to 60, 120 and 200 days in milk,
and from all of them. Two simple projections are run beside best prediction for comparison.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from bestpred import Settings, TestDay, age_factors, bestpred

CUTOFFS = (60, 120, 200, None)  # None: every test to the end


def select(daily: pd.DataFrame, end: int, cover: float, max_gap: int) -> pd.DataFrame:
    keep = []
    for (cow, parity), g in daily.groupby(['cow', 'parity']):
        days = g.dim[g.dim <= end].sort_values()
        if days.empty or days.iloc[0] > 5 or g.dim.max() < end:
            continue
        if len(days) / end < cover or np.diff(np.r_[0, days.to_numpy(), end + 1]).max() - 1 > max_gap:
            continue
        keep.append((cow, parity))
    return daily.set_index(['cow', 'parity']).loc[keep].reset_index()


def truth_curve(g: pd.DataFrame, end: int) -> pd.Series:
    s = g.set_index('dim').milk.reindex(range(1, end + 1))
    return s.interpolate(limit_direction='both')


def draw_tests(g: pd.DataFrame, end: int, rng: np.random.Generator) -> list:
    """Monthly test days: the first between 5 and 35 days in milk, then every 30 +/- 4 days, on days weighed."""
    weighed = g.set_index('dim').milk
    tests, day = [], int(rng.integers(5, 36))
    while day <= end:
        for shift in (0, -1, 1, -2, 2):
            if day + shift in weighed.index and 1 <= day + shift <= end:
                tests.append((day + shift, float(weighed[day + shift])))
                break
        day += 30 + int(rng.integers(-4, 5))
    return tests


def age_months(birth, fresh) -> int:
    return int((fresh - birth).days / 30.5) if pd.notna(birth) else 0


def run(tests, herdavg, agefac, parity, length, settings):
    tds = [TestDay(dim=d, milk=m, times_sampled=0) for d, m in tests]
    return bestpred(tds, herdavg=(herdavg, 0, 0, 0), agefac=agefac, cowid='H', parity=int(parity), length=length,
                    settings=settings)


def simple_projections(tests, herd_curve, end):
    """Ratio to the herd curve, and test intervals plus the herd curve after the last test."""
    curve = herd_curve[1:end + 1]
    ratios = [m / curve[d - 1] for d, m in tests]
    ratio = float(np.mean(ratios) * curve.sum())
    (d0, m0), *_ = tests
    total = m0 / curve[d0 - 1] * curve[:d0].sum()  # calving to first test, shaped like the herd curve
    for (a, ma), (b, mb) in zip(tests, tests[1:]):
        total += (ma + mb) / 2 * (b - a)
    dl, ml = tests[-1]
    total += ml / curve[dl - 1] * curve[dl:].sum()
    return ratio, float(total)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('daily')
    ap.add_argument('--end', type=int, default=305)
    ap.add_argument('--cover', type=float, default=0.85, help='share of days 1..end that must be weighed')
    ap.add_argument('--max-gap', type=int, default=7)
    ap.add_argument('--state', type=int, default=93, help='USDA state code for age factors (93 = California)')
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--out', default='results')
    args = ap.parse_args()
    end = args.end
    rng = np.random.default_rng(args.seed)
    daily = pd.read_csv(args.daily, parse_dates=['birth_date', 'fresh_date'])
    daily = select(daily, end, args.cover, args.max_gap)
    settings = Settings(laclen=end, use3X=0)

    lacts = []
    for (cow, parity), g in daily.groupby(['cow', 'parity']):
        first = g.iloc[0]
        tests = draw_tests(g, end, rng)
        if len(tests) < 3:
            continue
        fresh = first.fresh_date
        af = age_factors('H', max(age_months(first.birth_date, fresh), 1), fresh.year, fresh.month, int(parity),
                         args.state, 0)
        lacts.append(dict(cow=cow, parity=int(parity), tests=tests, agefac=af,
                          truth=float(truth_curve(g, end).sum())))

    # Herd average (305-d ME): best prediction of every complete record, starting from the breed mean.
    first_pass = [run(lc['tests'], 0, lc['agefac'], lc['parity'], lc['tests'][-1][0], Settings(use3X=0))
                  for lc in lacts]
    herdavg = float(np.mean([r.yldvec[0, 0] for r in first_pass]))

    rows = []
    for lc in lacts:
        for cut in CUTOFFS:
            tests = [t for t in lc['tests'] if cut is None or t[0] <= cut]
            if not tests:
                continue
            length = tests[-1][0] if cut is None else cut
            res = run(tests, herdavg, lc['agefac'], lc['parity'], length, settings)
            bp = float(res.yields('actual')['milk']['laclen'])
            ratio, intervals = simple_projections(tests, res.daily_herd[1, 0], end)
            label = 'all' if cut is None else str(cut)
            for method, pred in (('best prediction', bp), ('herd-curve ratio', ratio),
                                 ('test intervals + herd curve', intervals)):
                rows.append(dict(cow=lc['cow'], parity=lc['parity'], cutoff=label, tests=len(tests), method=method,
                                 predicted=pred, truth=lc['truth'],
                                 reliability=float(res.rel_yield[0]) if method == 'best prediction' else np.nan))
    df = pd.DataFrame(rows)
    df['error'] = df.predicted - df.truth
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / f'predictions_{end}d.csv', index=False)

    def summarise(g):
        return pd.Series(dict(
            lactations=len(g), tests=g.tests.mean(), bias_lb=g.error.mean(), bias_pct=100 * g.error.mean() / g.truth.mean(),
            rmse_lb=np.sqrt((g.error ** 2).mean()), mape_pct=100 * (g.error.abs() / g.truth).mean(),
            r=np.corrcoef(g.predicted, g.truth)[0, 1], mean_reliability=g.reliability.mean()))
    order = {c: i for i, c in enumerate(['60', '120', '200', 'all'])}
    summary = (df.groupby(['cutoff', 'method']).apply(summarise, include_groups=False).reset_index()
               .sort_values(['cutoff', 'method'], key=lambda s: s.map(order) if s.name == 'cutoff' else s))
    summary.to_csv(out / f'summary_{end}d.csv', index=False)
    meta = dict(end=end, lactations=len(lacts), herd_avg_305me_lb=herdavg, mean_truth_lb=float(np.mean(
        [lc['truth'] for lc in lacts])), parity_mix=pd.Series([lc['parity'] for lc in lacts]).clip(upper=3)
        .value_counts().sort_index().to_dict(), seed=args.seed)
    (out / f'meta_{end}d.json').write_text(json.dumps(meta, indent=1, default=int))
    pd.set_option('display.width', 160)
    print(json.dumps(meta, default=int))
    print(summary.round(3).to_string(index=False))


if __name__ == '__main__':
    main()
