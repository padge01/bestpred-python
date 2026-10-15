"""Mature-equivalent factors: aiplage.c (milk, fat, protein) and adjscs.c (SCS), and the date arithmetic they need.

C's float arithmetic is kept where it changes the last digits: a float times an int stays a float in C.
"""

import numpy as np

from .tables import F32, scs_factors, table

AGELIM = ((16, 36), (28, 56), (40, 74), (52, 86), (64, 98), (76, 165))  # age limits (months) by parity 1..6+
REGDOT = (0, 0, 1, 4, 4, 1, 3, 2, 3, 5, 5, 6)  # Holstein region -> previous-days-open region
BREEDS7 = 'ABGHJMW'
REGBRD = (0, 0, 0, 1, 2, 3, 2)  # breed -> column of the region table (Ayr, Hol, Jer, MS)
DOMEAN = 120


def _ctrunc(a: int, b: int) -> int:
    """C integer division (truncates toward zero)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def _pdo_effect(coef: np.ndarray, pdo: int) -> float:
    """Previous-days-open effect: c0 + c1*pdo (float) + c2*pdo^2 (double), plus c3*(pdo-150)^2 past 150 days."""
    doprev2 = float(pdo * pdo)
    eff = float(F32(coef[0] + F32(coef[1] * F32(pdo)))) + float(coef[2]) * doprev2
    if pdo > 150:
        eff += float(coef[3]) * float((pdo - 150) * (pdo - 150))
    return eff


def aiplage(breed: str, age: int, fresh_year: int, fresh_month: int, parity: int, state: int, doprev: int,
            agebase: int = 0) -> tuple[float, float, float]:
    """Factors that standardize 305-d milk, fat and protein for age, month of calving and previous days open.

    agebase 0 adjusts to mature equivalent, 36 to 36 months (and so on). `state` is the 2-digit USDA state code."""
    brd = BREEDS7.find(breed[:1]) if breed else -1
    if brd < 0:
        brd = 3
    if brd == 6:
        raise ValueError("breed code 'W' has no age factors in aiplage")
    if not 0 <= state <= 96:
        raise ValueError(f'state code {state} is outside the table (0-96)')
    reg = int(table('region')[state, REGBRD[brd]]) - 1
    if reg < 0 and brd != 5:
        raise ValueError(f'state code {state} has no region in the age-factor tables')
    if parity == 0:
        raise ValueError('parity must be at least 1')
    lac = min(parity - 1, 5)
    a = age
    lo, hi = AGELIM[lac]
    a = lo if a < lo else hi if a > hi else a
    mo = fresh_month - 1
    pdo = doprev
    if (parity > 1 and pdo < 20) or pdo > 305:
        pdo = DOMEAN
    if fresh_year >= 1987:
        yrgp, yrgpp = 4, 1
    else:
        yrgp = _ctrunc(fresh_year - 1963, 6) if fresh_year >= 1969 else 0
        yrgpp = 0

    def factors(a, lac, pdo, mo):
        if lac > 0:
            lacdo = min(lac, 2) - 1
            if brd == 3:
                regdo = REGDOT[reg]
                eff = [_pdo_effect(table(f'h{t}dop')[regdo, lacdo], pdo) for t in 'mfp']
            else:
                brddo = brd if brd < 3 else brd - 1
                eff = [_pdo_effect(table(f'{t}dop')[brddo, lacdo], pdo) for t in 'mfp']
        else:
            eff = [0., 0., 0.]
        age2 = float(a * a)
        out = []
        prefix = 'abghjm'[brd]
        for t, (trait, yg) in enumerate((('m', yrgp), ('f', yrgp), ('p', yrgpp))):
            name = prefix + trait
            if brd == 5:  # Milking Shorthorn: no regions
                regtm = float(table(name + 'regtm')[yg])
                equ0 = float(table(name + 'equ0')[yg, lac, mo])
                equ = table(name + 'equ')[yg, lac]
            else:
                regtm = float(table(name + 'regtm')[reg, yg])
                equ0 = float(table(name + 'equ0')[yg, reg, lac, mo])
                equ = table(name + 'equ')[yg, reg, lac]
            denom = regtm + eff[t] + equ0 + float(F32(equ[0] * F32(a))) + float(equ[1]) * age2
            out.append(regtm / denom)
        return out

    fac = factors(a, lac, pdo, mo)
    if agebase > 0:
        base_lac = _ctrunc(agebase - 18, 13)
        avg = np.zeros(3)
        for month in range(12):
            avg += np.array(factors(agebase, base_lac, 90, month)) / 12
        fac = [f / v for f, v in zip(fac, avg)]
    return fac[0], fac[1], fac[2]


def adjscs(breed: str, parity: int, fresh_month: int, state: int, age: int, dim: int = 305, scs: int = 329) -> int:
    """Adjusted 100 x SCS for days in milk, age and month of calving (additive factors, 2009 on)."""
    dimfac, agefac, monfac = scs_factors()
    lact = 0 if parity == 1 else 1
    facbrd = 1 if breed[:1] in ('J', 'G') else 0
    age = min(max(age, 18), 120)
    reg = 0 if state <= 23 else 1 if state <= 48 else 2 if state <= 74 else 3
    dim = min(max(dim, 15), 305)
    value = np.rint(scs - dimfac[dim, lact, facbrd] - monfac[fresh_month, reg, facbrd]
                    + (agefac[age, facbrd] - 1) * 300)
    return int(min(max(value, 1), 999))


def age_factors(breed: str, age: int, fresh_year: int, fresh_month: int, parity: int, state: int, doprev: int,
                agebase: int = 0) -> np.ndarray:
    """agefac(1:4) as bestpred_fmt4 builds it: milk, fat, protein from aiplage, SCS from adjscs (305 d, SCS 3.29)."""
    m, f, p = aiplage(breed, age, fresh_year, fresh_month, parity, state, doprev, agebase)
    s = adjscs(breed, parity, fresh_month, state, age, 305, 329) / 329.
    return np.array([m, f, p, s])


MODAYS = ((31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31), (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31))


def pday(date8: str) -> int:
    """Days since 1 Jan 1960 (function pday, by Chris Schanefelter), for a YYYYMMDD date."""
    def num(text):
        text = text.strip()
        return int(text) if text else 0
    year, month, day = num(date8[0:4]) - 1900, num(date8[4:6]), num(date8[6:8])
    if year <= 0:
        return -21916
    leap = year // 4
    number_of_years = year - 60
    year_groups = abs(number_of_years) // 4
    balance_years = abs(number_of_years) - year_groups * 4
    leap = 2 if year == leap * 4 else 1
    month = min(max(month, 1), 12)
    if day == 0:
        day = 1
    days_in = MODAYS[leap - 1]
    if day > days_in[month - 1]:
        day = days_in[month - 1]
    day += sum(days_in[:month - 1])
    if number_of_years <= -1:
        day = 365 - day
        result = -((year_groups * 1461) + day + (balance_years - 1) * 365)
    else:
        if balance_years > 0:
            balance_years = (balance_years - 1) * 365 + 366
        result = year_groups * 1461 + day + balance_years
    return result - 1
