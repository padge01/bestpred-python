"""USDA Format 4 lactation records: read one, adjust it as bestpred_fmt4() does, and write the results line.

Format 4 is AIPL's fixed-width lactation record: a 248-byte fixed part, the number of test-day segments, then 23-byte
segments. Only the fields BESTPRED reads are parsed here (1-based columns as in the Fortran FORMATs).
"""

from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal
import math

import numpy as np

from .adjust import age_factors, pday
from .core import Result, Settings, TestDay, bestpred


def fnum(text: str, decimals: int = 0) -> float:
    """A Fortran Fw.d / Iw input field: blanks ignored, all-blank is zero, no point means `decimals` implied."""
    t = text.replace(' ', '')
    if not t or t in '+-':
        return 0.
    if '.' in t or 'e' in t.lower():
        return float(t)
    return int(t) / 10 ** decimals


@dataclass
class Format4:
    cowid: str
    birth: str
    herd: str
    fresh: str
    length: int
    lacno: int
    doprev: int
    me305: tuple
    dev305: tuple
    test_days: list
    status: list

    @classmethod
    def parse(cls, record: str) -> 'Format4':
        r = record.rstrip('\r\n').ljust(250)
        col = lambda a, b: r[a - 1:b]  # noqa: E731  (1-based, inclusive, as Fortran T edits)
        ntd = int(fnum(col(249, 250)))
        tds, status = [], []
        for i in range(min(ntd, 50)):
            seg = r[250 + 23 * i: 250 + 23 * (i + 1)].ljust(23)
            st = int(fnum(seg[4]))
            milk, fat, prot, scs = fnum(seg[13:17], 1), fnum(seg[17:19], 1), fnum(seg[19:21], 1), fnum(seg[21:23], 1)
            if st == 3:
                milk = fat = prot = scs = 0.
            if st == 2:
                fat = prot = 0.
            tds.append(TestDay(dim=int(fnum(seg[0:3])), milk=milk, fat=fat, protein=prot, scs=scs,
                               super=int(fnum(seg[3])), times_milked=int(fnum(seg[5])),
                               times_weighed=int(fnum(seg[6])), times_sampled=int(fnum(seg[7])),
                               mrd=int(fnum(seg[8:10]))))
            status.append(st)
        return cls(cowid=col(3, 19), birth=col(71, 78), herd=col(107, 114), fresh=col(128, 135),
                   length=int(fnum(col(136, 138))), lacno=int(fnum(col(159, 160))), doprev=int(fnum(col(246, 248))),
                   me305=(fnum(col(188, 192)), fnum(col(193, 196)), fnum(col(197, 200))),
                   dev305=(fnum(col(201, 206)), fnum(col(207, 211)), fnum(col(212, 216))),
                   test_days=tds, status=status)


def run_format4(rec: Format4, settings: Settings | None = None, herd305=None, agebase: int = 0) -> Result:
    """bestpred_fmt4(): herd means from the record, mature-equivalent factors, then best prediction.

    `herd305` overrides the herd means (milk, fat, protein lb, SCS x 100) where positive, as the Fortran's argument
    does; by default they are backsolved from the record's ME and deviation."""
    herd = np.zeros(4) if herd305 is None else np.array(herd305, dtype=np.float64)
    for j in range(4):
        if herd[j] <= 0:
            if j < 3:
                herd[j] = 0. if rec.me305[j] == 0. else rec.me305[j] - rec.dev305[j]
            else:
                herd[j] = 0.
    birth = rec.birth
    if birth.strip() == '' or birth < '19500101':
        birth = '19500101'
    age = int(np.float32(pday(rec.fresh) - pday(birth)) / np.float32(30.5))
    if rec.fresh.strip() == '':
        age = 84
    lacno = rec.lacno
    if lacno <= 0:
        lacno = max(1, (age - 6) // 13)
    if birth == '19500101':
        age = 12 + 15 * lacno
    fryr = int(fnum(rec.fresh[0:4]))
    frmo = max(int(fnum(rec.fresh[4:6])), 1)
    state = int(fnum(rec.herd[0:2]))
    brd = rec.cowid[0] if rec.cowid[:1] in tuple('ABGHJM') else 'H'
    doprev = rec.doprev
    if doprev < 1:
        doprev = 140
    if lacno == 1:
        doprev = 0
    if state == 0:
        state = 35
    agefac = age_factors(brd, age, fryr, frmo, lacno, state, doprev, agebase)
    herd[3] = herd[3] / 100
    return bestpred(rec.test_days, herd, agefac, cowid=rec.cowid, fresh=rec.fresh, parity=lacno, length=rec.length,
                    herdstate=rec.herd[0:2], settings=settings)


def ffmt(value: float, width: int, decimals: int) -> str:
    """Fortran Fw.d output: rounded half away from zero, '*'s when it does not fit."""
    if math.isnan(value):
        return 'NaN'.rjust(width)
    if math.isinf(value):
        return ('-Infinity' if value < 0 else 'Infinity').rjust(width) if width >= 9 else '*' * width
    q = Decimal(value).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    text = f'{q:.{decimals}f}'
    if decimals == 0:
        text += '.'
    if q == 0 and value < 0:
        text = '-' + text.lstrip('-')
    if len(text) > width and text.lstrip('-').startswith('0.'):
        text = text.replace('0.', '.', 1)
    return text.rjust(width) if len(text) <= width else '*' * width


def results_line(rec: Format4, res: Result) -> str:
    """A results_v2.dcr line (FORMAT 60 in bestpred_main.f90)."""
    length = max((t.dim for t in rec.test_days), default=0)
    parts = [rec.cowid.ljust(17)[:17], ' ', rec.fresh.ljust(8)[:8], str(length).rjust(4), ' ']
    parts += [ffmt(v, 5, 0) for v in (res.dcr_milk, res.dcr_components, res.dcr_scs)]
    for g in range(4):
        parts += [ffmt(v, 7, 0) for v in res.yldvec[0, 4 * g:4 * g + 3]] + [ffmt(res.yldvec[0, 4 * g + 3], 7, 2)]
    parts += [ffmt(v, 6, 2) for v in res.persistency]
    parts += [ffmt(v, 5, 2) for v in np.concatenate([res.rel_yield, res.rel_persistency])]
    for row in (res.yvec[0], res.herdavg):
        parts += [ffmt(v, 7, 0) for v in row[:3]] + [ffmt(row[3], 7, 2)]
    parts += [' '] + [ffmt(v, 7, 4) for v in res.bump[:3]] + [ffmt(res.bump[3], 9, 2)]
    return ''.join(parts)


def with_length_from_tests(rec: Format4) -> Format4:
    """bestpred_main overwrites the record's length with its last test day; do the same."""
    return replace(rec, length=max((t.dim for t in rec.test_days), default=0))
