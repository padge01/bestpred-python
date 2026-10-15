"""Best prediction of lactation yields and persistency: a line-by-line port of subroutine bestpred() in bestpred.f90.

The structure, names and order of operations follow the Fortran so the two can be read side by side; quirks of the
original that change results are kept (and noted), because the aim is the same numbers USDA's program gives.
"""

from dataclasses import dataclass, field

import numpy as np

from .curves import Obs, TRUE_DAY, covary, parity_tables, vary, vary_true_days
from .tables import BRDSD, BRDYLD, BREEDS, F32, LB, NEW3X, OLD3X, RMONTH, X305

LAST = 2  # parity groups: first, second and later
MAXTD = 50  # test days used per lactation
MAXY = 200  # observations used per lactation
TRAITS = ('milk', 'fat', 'protein', 'scs')


@dataclass
class Settings:
    """The options in bestpred.par that change the calculation. Defaults are the file's."""

    mtrait: int = 3  # 1 single-trait only; 3 multi-trait milk, fat, protein (SCS single-trait); 4 multi-trait all four
    use3X: int = 3  # 0 no 3X adjustment; 1 old factors; 2 new factors; 3 phased in by fresh year
    laclen: int = 305
    maxlen: int = 365
    method: str = 'W'  # milk, fat, protein standard curves: L linear, W Woods, R region, C calving season, T both
    method_scs: str = 'G'  # SCS curves: L linear, G Morant-Gnanasakthy, S region, D calving season, U both
    units_in: str = 'P'  # 'P' pounds or 'K' kilograms, milk, fat and protein
    units_out: str = 'P'
    breed_unknown: int = 4  # breed used for an unknown breed code: 1 AY 2 BS 3 GU 4 HO 5 JE 6 MS
    dim0: tuple = (115, 115, 150, 155, 161, 152, 159, 148)  # persistency mid-points, first then later parities

    def __post_init__(self):
        if self.mtrait not in (1, 3, 4):
            raise ValueError('mtrait must be 1, 3 or 4')
        if not 0 < self.laclen <= self.maxlen:
            raise ValueError('need 0 < laclen <= maxlen')


@dataclass
class TestDay:
    """One test day as Format 4 carries it. Milk in the input unit, fat and protein in %, SCS on its 0-9.9 scale."""

    __test__ = False  # not a pytest class, despite the name

    dim: int
    milk: float
    fat: float = 0.0
    protein: float = 0.0
    scs: float = 0.0
    super: int = 1  # supervision code: 1 supervised, 2 owner-sampler, 0 or 4 unusable, ...
    times_milked: int = 2
    times_weighed: int = 2
    times_sampled: int = 2
    mrd: int = 1  # milk-recorded days averaged into this test (LER); 1 for an ordinary test day


@dataclass
class Result:
    """Outputs of bestpred(), named. Index 0 of yldvec is mature equivalent, 1 actual; columns are 305-d, 365-d,
    laclen-d and to-date (part record) yields, each milk, fat, protein, SCS (SCS as a lactation mean)."""

    yldvec: np.ndarray  # (2, 16)
    persistency: np.ndarray  # (4,)
    rel_yield: np.ndarray  # (4,)
    rel_persistency: np.ndarray  # (4,)
    dcr: np.ndarray  # (4,) data collection rating by trait
    dcr_milk: float
    dcr_components: float
    dcr_scs: float
    yvec: np.ndarray  # (2, 4) expanded yields (or persistency for SCS)
    herd305: np.ndarray  # (2, 4) contemporary means, ME and actual
    herdavg: np.ndarray  # (4,) the herd average as the caller's array ends up (breed mean filled in when missing)
    bump: np.ndarray  # (4,) test-day bumpiness
    ntests: np.ndarray  # (4,)
    method: tuple  # 'MT' or 'ST' per trait
    agefac: np.ndarray
    fact3X: np.ndarray
    daily_bp: np.ndarray = field(repr=False)  # (2, 4, maxlen+1): the cow's daily deviation from the herd curve, ME/actual
    daily_herd: np.ndarray = field(repr=False)  # (2, 4, maxlen+1): the herd (contemporary) curve, ME/actual

    def yields(self, basis: str = 'actual') -> dict:
        """{trait: {'305': .., '365': .., 'laclen': .., 'to_date': ..}} for basis 'actual' or 'me'."""
        row = self.yldvec[1 if basis == 'actual' else 0]
        return {name: {'305': row[t], '365': row[4 + t], 'laclen': row[8 + t], 'to_date': row[12 + t]}
                for t, name in enumerate(TRAITS)}


def breed_index(cowid: str, breed_unknown: int) -> int:
    i = BREEDS.find(cowid[:1]) + 1 if cowid[:1] else 0
    return i if i > 0 else breed_unknown


def state_to_region(state: str) -> int:
    for region, codes in ((1, '50 51 52 54 55 61 63'), (2, '31 32 33 34 35 41 42 43'), (3, '45 46 47 48 81 83 84 87'),
                          (4, '11 12 13 14 15 16 21 22 23'), (5, '82 91 92 96'),
                          (6, '56 57 58 64 65 71 72 73 74 94'), (7, '85 86 88 93 95')):
        if state in codes.split():
            return region
    return 2


def date_to_season(fresh: str) -> int:
    month = fresh[4:6]
    for season, months in ((1, '03 04 05'), (2, '06 07 08'), (3, '09 10 11'), (4, '12 01 02')):
        if month in months.split():
            return season
    return 1


def ymean(tab, trait: int, dim: int, mrd: int, hratio: np.ndarray) -> float:
    """Expected yield on a test day from the standard curve, scaled to the herd (function ymean)."""
    if trait > 0:
        begin = end = dim - (mrd - 1) // 2
    else:
        begin, end = dim - mrd + 1, dim
    total = float(tab.dyield[trait, begin:end + 1].astype(np.float64).sum())
    return total / (end - begin + 1) * hratio[trait]


def binsort(values: list) -> list:
    return sorted(values)


def adjust3x(ntd, dim, length, yearfr, parity, xmilk, meanyld, use3X, maxlen):
    """Factors to adjust each test day (test3X), the 305-d record (fact3X) and the part record (part3X) for 3X."""
    lacn = min(parity, LAST)
    if lacn <= 0:
        lacn = LAST
    lacn3 = min(parity, 3)
    if lacn <= 0:  # sic: the original tests lacn, not lacn3
        lacn3 = 3
    adj3x = np.zeros(4, dtype=np.float32)
    for j in range(4):
        if use3X == 0:
            adj3x[j] = 0.
        elif use3X == 1:
            adj3x[j] = OLD3X[j, lacn3 - 1]
        elif use3X == 2:
            adj3x[j] = NEW3X[j, lacn3 - 1]
        elif use3X == 3:
            yrfr = max(min(yearfr, 1999), 1996)
            year0 = F32(1999 - yrfr) / F32(1999 - 1996)
            year1 = F32(1.) - year0
            adj3x[j] = year0 * OLD3X[j, lacn3 - 1] + year1 * NEW3X[j, lacn3 - 1]
        adj3x[j] = F32(1.0) / (F32(1.0) + adj3x[j])
    fact3x = np.ones(4)
    part3x = np.ones(4)
    lac3x = np.zeros(4)
    yld3x = np.zeros(4)
    test3x = np.ones((4, max(ntd, 1)))
    if ntd == 0:
        return test3x, fact3x, part3x
    dimsort = [0] * ntd
    freq = {}
    ntd2 = 0
    for i in range(ntd):
        if dim[i] <= maxlen:
            dimsort[i] = dim[i]
            freq[dim[i]] = xmilk[i]
            ntd2 += 1
        for j in range(4):
            test3x[j, i] = float(adj3x[j]) if xmilk[i] > 2 else 1.0
    dimsort[:ntd2] = binsort(dimsort[:ntd2])
    if ntd2 == 0 or dimsort[0] > maxlen or dimsort[0] <= 0:
        return test3x, fact3x, part3x
    a3x = np.ones(4)
    begin1 = begin2 = end1 = end2 = 0
    for i in range(ntd2):
        end1 = min(dimsort[i], 305)
        end2 = min(dimsort[i], length)
        for j in range(4):
            a3x[j] = float(adj3x[j]) if freq.get(dimsort[i], 0) > 2 else 1.0
            if i > 0:
                lac3x[j] -= meanyld[j, begin1] / a3x[j]
            lac3x[j] += meanyld[j, end1] / a3x[j]
            if i > 0:
                yld3x[j] -= meanyld[j, begin2] / a3x[j]
            yld3x[j] += meanyld[j, end2] / a3x[j]
        begin1, begin2 = end1, end2
    for j in range(4):
        if end1 < 305:
            lac3x[j] += (meanyld[j, 305] - meanyld[j, end1]) / a3x[j]
        if end1 < length:  # sic: end1, not end2
            yld3x[j] += (meanyld[j, length] - meanyld[j, end2]) / a3x[j]
        fact3x[j] = 1. if lac3x[j] == 0. else meanyld[j, 305] / lac3x[j]
        part3x[j] = 1. if yld3x[j] == 0. else meanyld[j, length] / yld3x[j]
    return test3x, fact3x, part3x


def bestpred(test_days: list, herdavg, agefac, cowid: str = 'H', fresh: str = '20000101', parity: int = 2,
             length: int | None = None, herdstate: str = '00', settings: Settings | None = None) -> Result:
    """Best prediction for one lactation.

    `herdavg` is the herd's 305-d mature-equivalent milk, fat and protein (input units) and mean SCS; zero or less
    means unknown (the breed mean is used). `agefac` multiplies actual yields to mature equivalent (1.0 for none).
    `cowid` only matters for its first letter, the breed (A B G H J M). `fresh` is YYYYMMDD; `length` is days from
    calving to the last test or to the end of the record (default: the last test day)."""
    s = settings or Settings()
    maxlen, laclen = s.maxlen, s.laclen
    td = list(test_days)
    if length is None:
        length = max((t.dim for t in td), default=0)
    agefac = np.array(agefac, dtype=np.float64)
    herdavg = np.array(herdavg, dtype=np.float64)

    # Inputs as BESTPRED's arrays (1 test day minimum, as the original pads an empty lactation).
    tstdays = len(td)
    ntd = 1 if tstdays <= 0 else min(tstdays, MAXTD)
    dim = [t.dim for t in td[:ntd]] or [maxlen + 1]
    super_ = [t.super for t in td[:ntd]] or [0]
    xmilk = [t.times_milked for t in td[:ntd]] or [0]
    weigh = [t.times_weighed for t in td[:ntd]] or [0]
    sample = [t.times_sampled for t in td[:ntd]] or [0]
    mrd = [t.mrd for t in td[:ntd]] or [0]
    yld = np.zeros((4, ntd))
    for i, t in enumerate(td[:ntd]):
        yld[:, i] = (t.milk, t.fat, t.protein, t.scs)

    brdyld, brdsd = BRDYLD.copy(), BRDSD.copy()
    if s.units_in == 'P':
        yld[0] = yld[0] / np.float64(LB)
        herdavg[:3] = herdavg[:3] / np.float64(LB)
        brdyld[:, :3, :] = brdyld[:, :3, :] / LB
        brdsd[:, :3] = brdsd[:, :3] / LB

    brd = breed_index(cowid, s.breed_unknown)
    if s.method in 'LW' and s.method_scs in 'LG':
        herdstate = '00'
    if herdstate == '00':
        region, season = 2, 1
    else:
        region, season = state_to_region(herdstate), date_to_season(fresh)

    lacn = min(parity, LAST)
    if lacn <= 0:
        lacn = LAST
    tab = parity_tables(lacn, brd, region, season, s.method, s.method_scs, maxlen, laclen, s.units_in, tuple(s.dim0))
    if length > maxlen:
        length = maxlen

    # Exclude duplicate test days and overlapping LER segments.
    dimvec = np.zeros(maxlen + 2, dtype=int)  # day -> 1-based index of the test that owns it
    for i in range(ntd):
        if dim[i] <= maxlen and dim[i] >= 1:
            if dim[i] - mrd[i] < 0:
                mrd[i] = dim[i]
            for k in range(1, mrd[i] + 1):
                d = dim[i] - k + 1
                if dimvec[d] > 0:
                    if mrd[i] > 1:
                        mrd[i] = k - 1
                        break
                else:
                    dimvec[d] = i + 1

    yearfr = int(fresh[:4]) if fresh[:4].strip().isdigit() else 0
    test3x, fact3x, part3x = adjust3x(ntd, dim, length, yearfr, parity, xmilk, tab.meanyld, s.use3X, maxlen)

    herd305 = np.zeros((2, 4))
    herd365 = np.zeros((2, 4))
    herd999 = np.zeros((2, 4))
    hratio = np.zeros(4)
    varfac = np.zeros(4)
    std = np.full((2, 4, maxlen + 1), -999.0)
    for j in range(4):
        if herdavg[j] <= 0.:
            herdavg[j] = brdyld[brd - 1, j, lacn - 1]  # sic: the year-group index is the parity group
        herd305[0, j] = herdavg[j] * X305[j]
        herd305[0, j] = herd305[0, j] * fact3x[j]
        if herd305[0, j] <= 0.:
            herd305[0, j] = brdyld[brd - 1, j, 0 if yearfr < 2000 else 1] * X305[j]
        hratio[j] = herd305[0, j] / tab.meanyld[j, 305]
        curve = tab.dyield[j, 1:].astype(np.float64) * hratio[j]
        std[0, j, 1:] = curve
        sum305, sum365, sum999 = curve[:305].sum(), curve[:365].sum(), curve[:laclen].sum()
        herd365[0, j] = herd305[0, j] * (sum365 / sum305)
        herd999[0, j] = herd305[0, j] * (sum999 / sum305)
        varfac[j] = np.float64(F32(brdsd[brd - 1, j] * F32(305.))) / np.sqrt(tab.stdvar[j])

    yldvec = np.zeros((2, 16))
    persvec = np.zeros(4)
    relyld = np.zeros(4)
    relpers = np.zeros(4)
    regrel = np.zeros(4)
    dcrvec = np.zeros(4)
    bump = np.zeros(4)
    ntests = np.zeros(4, dtype=int)
    daily_bp = np.full((2, 4, maxlen + 1), -999.0)
    grafall = np.zeros((2, 4, maxlen + 1))
    part = 1

    def usable(i):
        return 1 <= dim[i] <= maxlen and dimvec[dim[i]] == i + 1

    def edit(i, j):
        """The test-day edits BESTPRED applies (in place) before using trait j of test i; False if not usable."""
        if sample[i] > xmilk[i]:
            sample[i] = xmilk[i]
        if mrd[i] > 1:
            weigh[i] = xmilk[i]
        if weigh[i] < 1:
            yld[j, i] = 0.
        if sample[i] < 1:
            yld[1, i] = 0.
            yld[2, i] = 0.
            if yld[3, i] > 0.:
                sample[i] = 1
        if yld[j, i] <= 0.:
            return False
        if j in (1, 2):
            yld[j, i] = yld[0, i] * yld[j, i] / 100.
        return True

    def observation(i, j):
        return Obs(dim[i], j, super_[i], xmilk[i], weigh[i] if j == 0 else sample[i], mrd[i])

    def deviation(i, j):
        return yld[j, i] * test3x[j, i] - ymean(tab, j, dim[i], mrd[i], hratio) / agefac[j]

    # ................................................ multi-trait best prediction
    if s.mtrait > 1:
        obs, dev = [], []
        for i in range(ntd):
            if not usable(i):
                continue
            if sample[i] > xmilk[i]:
                sample[i] = xmilk[i]
            if mrd[i] > 1:
                weigh[i] = xmilk[i]
            for j in range(4):
                if weigh[i] < 1:
                    yld[j, i] = 0.
                if sample[i] < 1:
                    yld[1, i] = 0.
                    yld[2, i] = 0.
                    if yld[3, i] > 0.:
                        sample[i] = 1
                if yld[j, i] <= 0.:
                    continue
                if j in (1, 2):
                    yld[j, i] = yld[0, i] * yld[j, i] / 100.
                if j + 1 > s.mtrait or len(obs) == MAXY:
                    continue
                ntests[j] += 1
                if j == 0:
                    ntests[0] += mrd[i] - 1
                obs.append(observation(i, j))
                dev.append(deviation(i, j))
        size = len(obs)
        if size == 0:
            multi = {e: np.zeros(4) for e in (305, 365, laclen)}
            vari305 = np.zeros((4, 4))
            persist = np.zeros(4)
            dvari = np.zeros((4, 4))
            partrec = np.zeros(4)
        else:
            dev = np.array(dev)
            var = np.zeros((size, size))
            for a in range(size):
                for b in range(a + 1):
                    ja, jb = obs[a].trait, obs[b].trait
                    var[a, b] = var[b, a] = (vary(obs[a], obs[b], tab.sd, lacn) * varfac[ja] * varfac[jb]
                                             / (agefac[ja] * agefac[jb]))
            vinv = np.linalg.inv(var)
            trait_of = np.array([o.trait for o in obs])
            cov = {}
            for e in (305, 365, laclen):
                cov[e] = np.array([[covary(tab, k, o.trait, o.dim, e, o.mrd, 1) for o in obs] for k in range(4)])
                cov[e] *= varfac[trait_of] * varfac[:, None] / agefac[trait_of]
            dcov = np.array([[covary(tab, k, o.trait, o.dim, 305, o.mrd, 2) for o in obs] for k in range(4)])
            dcov *= varfac[trait_of] * varfac[:, None] / agefac[trait_of]
            raw = np.array([vary_true_days(o, tab.sd, lacn, maxlen) for o in obs])  # (size, 4, maxlen+1)
            covsum = (raw[:, :, 1:length + 1].sum(axis=2).T * varfac[trait_of] * varfac[:, None] / agefac[trait_of])
            multi = {e: cov[e] @ vinv @ dev for e in (305, 365)}
            multi[laclen] = multi.get(laclen, cov[laclen] @ vinv @ dev) if laclen in (305, 365) else \
                cov[laclen] @ vinv @ dev
            vari305 = cov[305] @ vinv @ cov[305].T
            for j in range(s.mtrait):
                curves = raw[:, j, :].T * varfac[trait_of] * varfac[j] / (agefac[trait_of] * agefac[j])
                graph = curves @ vinv @ dev
                grafall[0, j, 1:] = graph[1:]
                daily_bp[0, j, 1:] = graph[1:]
            partrec = covsum @ vinv @ dev
            persist = dcov @ vinv @ dev
            dvari = dcov @ vinv @ dcov.T
        for l in range(4):
            yldvec[0, l] = multi[305][l] + herd305[0, l]
            yldvec[0, 4 + l] = multi[365][l] + herd365[0, l]
            yldvec[0, 8 + l] = multi[laclen][l] + herd999[0, l]
            if part == 0 or s.mtrait < l + 1 or length == 0:
                yldvec[0, 12 + l] = 0.
            else:
                yldvec[0, 12 + l] = partrec[l] + tab.meanyld[l, length] * hratio[l]
            relyld[l] = vari305[l, l] / (tab.stdvar[l] * varfac[l] ** 2)
            regrel[l] = relyld[l]
            dcrvec[l] = 100. * relyld[l] / RMONTH[l, lacn - 1]
            persvec[l] = persist[l]
            relpers[l] = dvari[l, l] / varfac[l] ** 2

    # ................................................ single-trait estimates
    if s.mtrait < 4:
        st_start = 0 if s.mtrait == 1 else 3
        for j in range(st_start, 4):
            ntests[j] = 0
            obs, dev, order, zdev = [], [], [], {}
            for i in range(ntd):
                if not usable(i) or not edit(i, j):
                    continue
                if len(obs) == MAXY:
                    continue
                ntests[j] += 1
                if j == 0:
                    ntests[0] += mrd[i] - 1
                obs.append(observation(i, j))
                dev.append(deviation(i, j))
                order.append(i)
            size = len(obs)
            var = np.zeros((size, size))
            for a in range(size):
                for b in range(a + 1):
                    var[a, b] = var[b, a] = vary(obs[a], obs[b], tab.sd, lacn) * varfac[j] ** 2 / agefac[j] ** 2
            for a, i in enumerate(order):
                zdev[i] = dev[a] * 305 / (np.float64(X305[j]) * np.sqrt(var[a, a]))
            # Bumpiness: changes between successive test days against their expected size.
            if size > 1:
                dimsort = sorted(o.dim for o in obs)
                bumpsd = varb = 0.
                for k in range(1, size):
                    zdif = zdev[dimvec[dimsort[k]] - 1] - zdev[dimvec[dimsort[k - 1]] - 1]
                    bumpsd += zdif ** 2
                    varb += 2. * (1. - var[k, k - 1] / np.sqrt(var[k, k] * var[k - 1, k - 1]))  # sic: unsorted k
                with np.errstate(divide='ignore', invalid='ignore'):
                    b = np.float64(bumpsd) / np.float64(varb)
                bump[j] = 0. if b < 0 else 99. if b > 99. else b
            if j == 0:
                regrel[0] = relyld[0]
            if size == 0:
                single = {e: 0. for e in (305, 365, laclen)}
                vari = 0.
                pers = 0.
                dvar = 0.
                partial = 0.
            else:
                dev = np.array(dev)
                vinv = np.linalg.inv(var)
                cov = {e: np.array([covary(tab, j, j, o.dim, e, o.mrd, 1) for o in obs]) * varfac[j] ** 2 / agefac[j]
                       for e in (305, 365, laclen)}
                dcov = np.array([covary(tab, j, j, o.dim, 305, o.mrd, 2) for o in obs]) * varfac[j] ** 2 / agefac[j]
                raw = np.array([vary_true_days(o, tab.sd, lacn, maxlen)[j] for o in obs])  # (size, maxlen+1)
                single = {e: cov[e] @ vinv @ dev for e in (305, 365, laclen)}
                vari = cov[305] @ vinv @ cov[305]
                curve = raw.T * varfac[j] ** 2 / agefac[j] ** 2
                graph = curve @ vinv @ dev
                grafall[0, j, 1:] = graph[1:]
                daily_bp[0, j, 1:] = np.where(graph[1:] != 0., graph[1:], -999.)
                covsum = raw[:, 1:length + 1].sum(axis=1) * varfac[j] ** 2 / agefac[j]
                partial = covsum @ vinv @ dev
                pers = dcov @ vinv @ dev
                dvar = dcov @ vinv @ dcov
            yldvec[0, j] = single[305] + herd305[0, j]
            yldvec[0, 4 + j] = single[365] + herd365[0, j]
            yldvec[0, 8 + j] = single[laclen] + herd999[0, j]
            if part == 0 or length == 0:
                yldvec[0, 12 + j] = 0.
            else:
                yldvec[0, 12 + j] = partial + tab.meanyld[j, length] * hratio[j]
            relyld[j] = vari / (tab.stdvar[j] * varfac[j] ** 2)
            regrel[j] = relyld[j]
            dcrvec[j] = 100. * relyld[j] / RMONTH[j, lacn - 1]
            persvec[j] = pers
            relpers[j] = dvar / varfac[j] ** 2

    # ................................................ actual yields, units, outputs
    for j in range(4):
        scale = agefac[j] * fact3x[j]
        for c in (j, j + 4, j + 8):
            yldvec[1, c] = yldvec[0, c] / scale
        herd305[1, j] = herd305[0, j] / scale
        herd365[1, j] = herd365[0, j] / scale
        herd999[1, j] = herd999[0, j] / scale
        yldvec[1, j + 12] = yldvec[0, j + 12] / (agefac[j] * part3x[j])
    lb = np.float64(LB)
    if s.units_out == 'P':
        for j in range(3):
            yldvec[:, [j, j + 4, j + 8, j + 12]] *= lb
            herd305[:, j] *= lb
            herd365[:, j] *= lb
            herd999[:, j] *= lb
    yldvec[:, 3] /= 305.
    yldvec[:, 7] /= 365.
    yldvec[:, 11] /= laclen
    yldvec[:, 15] = yldvec[:, 15] / length if length > 0 else 0.
    herd305[:, 3] /= 305.
    herd365[:, 3] /= 365.
    herd999[:, 3] /= laclen

    if s.mtrait == 4:
        method = ('MT',) * 4
    elif s.mtrait == 1:
        method = ('ST',) * 4
    else:
        method = ('MT', 'MT', 'MT', 'ST')
    dcr_c = (dcrvec[1] + dcrvec[2]) / 2.
    if ntests[2] == 0:
        dcr_c = dcrvec[1]

    yvec = np.zeros((2, 4))
    with np.errstate(divide='ignore', invalid='ignore'):
        for j in range(4):
            if s.mtrait > 1:
                yvec[0, j] = herd305[0, j] + (yldvec[0, j] - herd305[0, j]) / regrel[j]
                yvec[1, j] = herd305[1, j] + (yldvec[1, j] - herd305[1, j]) / regrel[j]
                if s.mtrait == 3 and j == 3:
                    yvec[0, j] = persvec[j] / relpers[j]
                    yvec[1, j] = yvec[0, j]
            else:
                yvec[0, j] = persvec[j] if relpers[j] == 0 else persvec[j] / relpers[j]
                yvec[1, j] = yvec[0, j]
    yvec[:, 3] /= 305.

    # Daily curves: the herd's, and the cow's deviation from it, mature equivalent then actual.
    for j in range(4):
        scale = agefac[j] * fact3x[j]
        std[1, j] = np.where(std[0, j] > -999., std[0, j] / scale, std[1, j])
        daily_bp[1, j] = np.where(daily_bp[0, j] > -999., daily_bp[0, j] / scale, daily_bp[1, j])
    if s.units_out == 'P':
        std[:, :3] = np.where(std[:, :3] > -999., std[:, :3] * lb, std[:, :3])
        daily_bp[:, :3] = np.where(daily_bp[:, :3] > -999., daily_bp[:, :3] * lb, daily_bp[:, :3])
        herdavg[:3] = herdavg[:3] * lb

    return Result(yldvec=yldvec, persistency=persvec, rel_yield=relyld, rel_persistency=relpers, dcr=dcrvec,
                  dcr_milk=dcrvec[0], dcr_components=dcr_c, dcr_scs=dcrvec[3], yvec=yvec, herd305=herd305,
                  herdavg=herdavg, bump=bump, ntests=ntests, method=method, agefac=agefac, fact3X=fact3x,
                  daily_bp=daily_bp, daily_herd=std)
