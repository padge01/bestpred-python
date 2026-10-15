"""Standard lactation curves and test-day (co)variances: subroutine interpolate() and functions vary() and covary().

Index conventions: traits 0-3 are milk, fat, protein and SCS; parity group `lacn` is 1 (first) or 2 (later); days in
milk are 1-based, so arrays indexed by day carry an unused slot 0.
"""

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from .tables import DCR_WEIGHT, DSD, DYLD, F32, LB, MFPCORR, table

MFP64 = MFPCORR.astype(np.float64)


def standard_curve(trait: int, lacn: int, method: str, breed: int, region: int, season: int, maxlen: int,
                   units_in: str) -> tuple[np.ndarray, np.ndarray]:
    """Daily mean (float32, as Fortran REAL) and SD (float32 values) of one trait for days 1..maxlen, slot 0 unused.

    `breed` is 1-6 (A B G H J M), region 1-7 and season 1-4 as in BESTPRED. Woods (W, C, R, T) and Morant-Gnanasakthy
    (G, D, S, U) curves are in kg; linear interpolation (L) uses the monthly tables, which BESTPRED converts to kg when
    the input is in pounds."""
    i = np.arange(1, maxlen + 1, dtype=np.float32)
    lc, t = lacn - 1, trait
    if trait < 3:
        if method not in 'LWRTC':
            method = 'L'
    elif method not in 'LGSUD':
        method = 'L'
    if not 1 <= breed <= 6:
        breed = 4
    b, r, s = breed - 1, region - 1, season - 1

    if method == 'L':
        dyld, dsd = DYLD.copy(), DSD.copy()
        if units_in == 'P':
            dyld[:, :3, :] = dyld[:, :3, :] / LB
            dsd[:, :3, :] = dsd[:, :3, :] / LB
        day = np.arange(1, maxlen + 1)
        month = np.minimum(np.maximum(1, (day + 15) // 30), 11)
        w_next = (day - month * 30 + 15).astype(np.float32)
        w_this = ((month + 1) * 30 - 15 - day).astype(np.float32)
        mean = (w_next * dyld[month, t, lc] + w_this * dyld[month - 1, t, lc]) / F32(30.)
        sd = (w_next * dsd[month, t, lc] + w_this * dsd[month - 1, t, lc]) / F32(30.)
        mean[day > 365] = dyld[11, t, lc]
        sd[day > 365] = dsd[11, t, lc]
    elif method in 'WRCT':
        if method == 'W':
            pm, ps = table('woods_means')[:, t, lc, b], table('woods_sd')[:, t, lc, b]
        elif method == 'R':
            pm, ps = table('regional_woods_means')[:, t, lc, r], table('regional_woods_sd')[:, t, lc, r]
        elif method == 'C':
            pm, ps = table('calving_woods_means')[:, t, lc, s], table('calving_woods_sd')[:, t, lc, s]
        else:
            pm, ps = table('seasonal_woods_means')[:, t, lc, s, r], table('seasonal_woods_sd')[:, t, lc, s, r]
        mean = pm[0] * i ** pm[1] * np.exp(-i * pm[2])
        sd = ps[0] * i ** ps[1] * np.exp(-i * ps[2])
    else:
        if method == 'G':
            pm, ps = table('mandg_means')[:, 0, lc, b], table('mandg_sd')[:, 0, lc, b]
        elif method == 'S':
            pm, ps = table('regional_mandg_means')[:, 0, lc, r], table('regional_mandg_sd')[:, 0, lc, r]
        elif method == 'D':
            pm, ps = table('calving_mandg_means')[:, 0, lc, s], table('calving_mandg_sd')[:, 0, lc, s]
        else:
            pm, ps = table('seasonal_mandg_means')[:, 0, lc, s, r], table('seasonal_mandg_sd')[:, 0, lc, s, r]
        x = i + F32(10)
        mean = pm[0] - pm[1] * x + pm[2] * (x * x) + pm[3] / x
        sd = ps[0] - ps[1] * x + (ps[2] * (x * x)) / F32(2) + ps[3] / x
    out_mean = np.zeros(maxlen + 1, dtype=np.float32)
    out_sd = np.zeros(maxlen + 1, dtype=np.float32)
    out_mean[1:] = mean
    out_sd[1:] = sd
    return out_mean, out_sd


def base_corr(t1: int, t2: int, d: np.ndarray, same: np.ndarray, lacn: int) -> np.ndarray:
    """Correlation between true daily yields of traits t1, t2 on two days `d` apart (vary(), before the test-day terms).

    `same` marks pairs that are the same day; the same trait on the same day correlates 1."""
    idiag = same.astype(np.float64)
    d = d.astype(np.float64)
    mfp = MFP64[t1, t2]
    if lacn == 1:
        mfp_parm = (F32(0.214), F32(0.786), F32(0.998))
    else:
        mfp_parm = (F32(0.132), F32(0.868), F32(0.997))
    scs_parm = (F32(0.199), F32(0.801), F32(0.998))
    if t1 < 3 and t2 < 3:
        a, b, r = mfp_parm
        corr = (np.float64(a) * idiag + np.float64(b) * np.float64(r) ** d) * mfp
    elif t1 == 3 and t2 == 3:
        a, b, r = scs_parm
        corr = (np.float64(a) * idiag + np.float64(b) * np.float64(r) ** d) * mfp
    else:
        a, b, r = mfp_parm
        sq1 = np.sqrt(np.float64(a) * idiag + np.float64(b) * np.float64(r) ** d).astype(np.float32)
        a, b, r = scs_parm
        sq2 = np.sqrt(np.float64(a) * idiag + np.float64(b) * np.float64(r) ** d).astype(np.float32)
        corr = (sq1 * sq2 * MFPCORR[t1, t2]).astype(np.float64)
    if t1 == t2:
        corr = np.where(same, 1.0, corr)
    return corr


@dataclass(frozen=True)
class Obs:
    """One test-day observation as vary() sees it: q(1:6) in BESTPRED."""

    dim: int
    trait: int  # 0-3
    super: int  # supervision code 0-9
    xmilk: int  # times milked a day
    sample: int  # times weighed (milk) or sampled (components)
    mrd: int  # milk-recorded days averaged together (LER)

    def days(self) -> np.ndarray:
        if self.trait > 0:
            return np.array([self.dim - (self.mrd - 1) // 2])
        return np.arange(self.dim - self.mrd + 1, self.dim + 1)


TRUE_DAY = dict(super=1, xmilk=2, sample=2, mrd=1)


def _err(super_code: int) -> np.float32:
    w = DCR_WEIGHT[super_code]
    if w > 0:
        return F32((F32(1.) / w - F32(1.)) * F32(.62))
    return F32(0.)


def vary(a: Obs, b: Obs, sd: np.ndarray, lacn: int) -> float:
    """(Co)variance of two test-day observations: the mean over the days each covers. `sd` is (4, maxlen+1)."""
    di, dj = a.days(), b.days()
    i, j = np.meshgrid(di, dj, indexing='ij')
    same = i == j
    corr = base_corr(a.trait, b.trait, np.abs(i - j), same, lacn)
    mfp = MFPCORR[a.trait, b.trait]
    if same.any():
        ampm = F32(F32(.3) * mfp) * F32(F32(F32(1.) * F32(a.xmilk)) / F32(max(a.sample, b.sample)) - F32(1.))
        corr = np.where(same, corr + np.float64(ampm), corr)
        if a.trait == b.trait and DCR_WEIGHT[a.super] == 0.:
            corr = np.where(same, 1000000., corr)
    err = F32(np.sqrt(F32(_err(a.super) * _err(b.super)))) * mfp
    corr = corr + np.float64(F32(err))
    total = (corr * sd[a.trait, i] * sd[b.trait, j]).sum()
    return total / len(di) / len(dj)


def vary_true_days(a: Obs, sd: np.ndarray, lacn: int, maxlen: int) -> np.ndarray:
    """vary(a, true day m of trait l) for l = 0..3 and m = 1..maxlen: shape (4, maxlen+1), slot 0 unused."""
    di = a.days()
    m = np.arange(1, maxlen + 1)
    out = np.zeros((4, maxlen + 1))
    i, mm = np.meshgrid(di, m, indexing='ij')
    same = i == mm
    for t in range(4):
        corr = base_corr(a.trait, t, np.abs(i - mm), same, lacn)
        mfp = MFPCORR[a.trait, t]
        ampm = F32(F32(.3) * mfp) * F32(F32(F32(1.) * F32(a.xmilk)) / F32(max(a.sample, 2)) - F32(1.))
        corr = np.where(same, corr + np.float64(ampm), corr)
        if a.trait == t and DCR_WEIGHT[a.super] == 0.:
            corr = np.where(same, 1000000., corr)
        # A true day is supervised (no owner-sampler error), so the error term is sqrt(err * 0) = 0.
        out[t, 1:] = (corr * sd[a.trait, i] * sd[t, mm]).sum(axis=0) / len(di)
    return out


@dataclass
class ParityTables:
    """Everything BESTPRED computes once per breed, region, season and parity group."""

    dyield: np.ndarray  # (4, maxlen+1) float32 daily means, kg
    sd: np.ndarray  # (4, maxlen+1) daily SDs
    meanyld: np.ndarray  # (4, maxlen+1) cumulative means
    stdvar: np.ndarray  # (4,) variance of the 305-d yield
    covari: dict  # endpoint -> (4, 4, maxlen+1): covariance of trait k's yield to the endpoint with trait j on day m
    covd: np.ndarray  # (4, 4, maxlen+1): the same for persistency (305-d basis)
    d0: np.ndarray  # (4,) persistency mid-points


@lru_cache(maxsize=64)
def parity_tables(lacn: int, breed: int, region: int, season: int, method: str, method_scs: str, maxlen: int,
                  laclen: int, units_in: str, dim0: tuple) -> ParityTables:
    dyield = np.zeros((4, maxlen + 1), dtype=np.float32)
    sd32 = np.zeros((4, maxlen + 1), dtype=np.float32)
    for t in range(4):
        dyield[t], sd32[t] = standard_curve(t, lacn, method if t < 3 else method_scs, breed, region, season, maxlen,
                                            units_in)
    sd = sd32.astype(np.float64)
    meanyld = np.cumsum(dyield.astype(np.float64), axis=1)

    days = np.arange(1, maxlen + 1)
    ii, kk = np.meshgrid(days, days, indexing='ij')
    dist, same = np.abs(ii - kk), ii == kk
    ends = sorted({305, 365, laclen} & set(range(1, maxlen + 1)))
    covari = {e: np.zeros((4, 4, maxlen + 1)) for e in ends}
    covd = np.zeros((4, 4, maxlen + 1))
    stdvar = np.zeros(4)
    dv1 = np.zeros(4)
    dvd = np.zeros(4)
    weight_i = days.astype(np.float64)
    for t305 in range(4):
        for t in range(4):
            # c[i-1, k-1] = vary(true day i of trait t305, true day k of trait t)
            c = base_corr(t305, t, dist, same, lacn) * sd[t305, 1:, None] * sd[t, None, 1:]
            cum = np.cumsum(c, axis=0)
            for e in ends:
                covari[e][t305, t, 1:] = cum[e - 1]
            covd[t305, t, 1:] = (c[:305] * weight_i[:305, None]).sum(axis=0)
            if t == t305:
                c305 = c[:305, :305]
                stdvar[t] = c305.sum()
                dv1[t] = (c305 * weight_i[:305, None]).sum()
                dvd[t] = (c305 * weight_i[:305, None] * weight_i[None, :305]).sum()
    d0 = np.array(dim0[4 * (lacn - 1): 4 * lacn], dtype=np.float64)
    varp = dvd - 2 * dv1 * d0 + stdvar * d0 ** 2
    covd = (covd - covari[305] * d0[:, None, None]) / np.sqrt(varp)[:, None, None]
    return ParityTables(dyield=dyield, sd=sd, meanyld=meanyld, stdvar=stdvar, covari=covari, covd=covd, d0=d0)


def covary(tab: ParityTables, trt305: int, trait: int, dim: int, end: int, mrd: int, stat: int) -> float:
    """Covariance of a test day (trait, dim, mrd) with lactation yield (stat 1) or persistency (stat 2) of trt305."""
    if trait > 0:
        days = [dim - (mrd - 1) // 2]
    else:
        days = range(dim - mrd + 1, dim + 1)
    source = tab.covari[end] if stat == 1 else tab.covd
    return sum(source[trt305, trait, m] for m in days) / len(days)
