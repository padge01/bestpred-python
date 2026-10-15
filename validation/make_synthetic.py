"""Synthetic daily meter weights shaped like a real herd's, with no real cow in them.

    python validation/make_synthetic.py fit real_daily.csv params.json      # summarise a herd (aggregates only)
    python validation/make_synthetic.py make params.json synthetic.csv.gz   # draw lactations from the summary

The summary holds only herd-level aggregates: the parity mix, a smoothed mean curve for each parity group, how cows
spread around it (level and persistency), day-to-day variation, and how often a day goes unweighed. Every synthetic
cow is drawn from those.
"""

import argparse
import json

import numpy as np
import pandas as pd

END = 305
GROUPS = ('1', '2', '3+')


def group(parity: int) -> str:
    return '1' if parity == 1 else '2' if parity == 2 else '3+'


def fit(path: str, out: str) -> None:
    d = pd.read_csv(path)
    d = d[(d.dim >= 1) & (d.dim <= END)]
    span = d.groupby(['cow', 'parity']).dim.agg(['min', 'max', 'size'])
    full = span[(span['min'] <= 5) & (span['max'] >= 270) & (span['size'] / span['max'] >= 0.85)].index
    d = d.set_index(['cow', 'parity']).loc[full].reset_index()
    d['group'] = d.parity.map(group)

    curves, levels, residuals, missing = {}, [], [], []
    for g, gd in d.groupby('group'):
        mean = gd.groupby('dim').milk.mean().reindex(range(1, END + 1)).interpolate(limit_direction='both')
        curves[g] = mean.rolling(15, center=True, min_periods=1).mean().round(1)
    x = (np.arange(1, END + 1) - 150) / 100
    for (cow, parity), g in d.groupby(['cow', 'parity']):
        mean = curves[group(parity)]
        s = g.set_index('dim').milk.reindex(range(1, END + 1))
        observed = s.notna().to_numpy()
        missing.append(1 - observed[:int(g.dim.max())].mean())
        ratio = np.log(s / mean.to_numpy())
        ok = ratio.notna().to_numpy()
        a, b = np.polyfit(x[ok], ratio[ok], 1)[::-1]
        levels.append((a, b))
        resid = (ratio - (a + b * x)).to_numpy()
        residuals.append(resid)
    levels = np.array(levels)
    r = np.concatenate([v[1:] for v in residuals])
    r0 = np.concatenate([v[:-1] for v in residuals])
    ok = ~np.isnan(r) & ~np.isnan(r0)
    phi = float(np.corrcoef(r[ok], r0[ok])[0, 1])
    allr = np.concatenate(residuals)
    allr = allr[~np.isnan(allr)]
    sd = float(1.4826 * np.median(np.abs(allr - np.median(allr))))  # robust: meter outliers don't widen it
    params = dict(
        days=END,
        parity_mix={g: round(float((d.groupby(['cow', 'parity']).group.first() == g).mean()), 2) for g in GROUPS},
        mean_curve_lb={g: curves[g].tolist() for g in GROUPS},
        cow_level_and_persistency=dict(mean=np.round(levels.mean(axis=0), 3).tolist(),
                                       cov=np.round(np.cov(levels.T), 4).tolist()),
        daily_log_sd=round(sd, 3), daily_autocorrelation=round(phi, 2),
        share_of_days_unweighed=round(float(np.median(missing)), 3),
    )
    with open(out, 'w') as f:
        json.dump(params, f, indent=1)
    print(f'summarised {len(levels)} lactations into {out}')


def make(params_path: str, out: str, n: int, seed: int) -> None:
    p = json.load(open(params_path))
    rng = np.random.default_rng(seed)
    days = np.arange(1, p['days'] + 1)
    x = (days - 150) / 100
    mix = p['parity_mix']
    groups = rng.choice(list(mix), size=n, p=np.array(list(mix.values())) / sum(mix.values()))
    lev = p['cow_level_and_persistency']
    ab = rng.multivariate_normal(lev['mean'], lev['cov'], size=n)
    rows = []
    for i in range(n):
        g = groups[i]
        parity = {'1': 1, '2': 2}.get(g) or int(rng.choice([3, 4, 5], p=[.5, .3, .2]))
        fresh = pd.Timestamp('2025-01-01') + pd.Timedelta(days=int(rng.integers(0, 365)))
        age = {1: 23, 2: 36, 3: 49, 4: 62, 5: 75}[parity] + int(rng.integers(-2, 4))
        birth = fresh - pd.Timedelta(days=int(age * 30.5))
        noise = np.empty(len(days))
        noise[0] = rng.normal(0, p['daily_log_sd'])
        phi = p['daily_autocorrelation']
        for t in range(1, len(days)):
            noise[t] = phi * noise[t - 1] + rng.normal(0, p['daily_log_sd'] * np.sqrt(1 - phi ** 2))
        milk = np.array(p['mean_curve_lb'][g]) * np.exp(ab[i, 0] + ab[i, 1] * x + noise)
        weighed = rng.random(len(days)) >= p['share_of_days_unweighed']
        weighed[0] = True
        for d, m in zip(days[weighed], milk[weighed]):
            rows.append((f'S{i + 1:04d}', parity, 'H', birth.date(), fresh.date(), int(d), round(float(m), 1)))
    df = pd.DataFrame(rows, columns=['cow', 'parity', 'breed', 'birth_date', 'fresh_date', 'dim', 'milk'])
    df.to_csv(out, index=False)
    print(f'{n} synthetic lactations, {len(df)} cow-days, written to {out}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    f = sub.add_parser('fit')
    f.add_argument('daily')
    f.add_argument('params')
    m = sub.add_parser('make')
    m.add_argument('params')
    m.add_argument('out')
    m.add_argument('--n', type=int, default=600)
    m.add_argument('--seed', type=int, default=2026)
    a = ap.parse_args()
    fit(a.daily, a.params) if a.cmd == 'fit' else make(a.params, a.out, a.n, a.seed)
