"""USDA's coefficient tables, loaded once from data/tables.json (see tools/extract_tables.py) and data/adjust.scs.

Every table is single precision in the original (Fortran REAL, C float), so they are returned as float32 arrays; the
arithmetic that uses them follows the original's mix of single and double precision.
"""

from functools import lru_cache
from importlib import resources
import json

import numpy as np

F32 = np.float32


@lru_cache(maxsize=None)
def _all() -> dict:
    raw = json.loads(resources.files('bestpred').joinpath('data/tables.json').read_text())['tables']
    out = {}
    for name, t in raw.items():
        a = np.array(t['values'], dtype=np.float64)
        out[name] = a.reshape(t['shape'], order=t['order']).astype(np.float32 if name != 'region' else np.int64)
    return out


def table(name: str) -> np.ndarray:
    """A table by its name in the USDA source. Fortran tables keep Fortran index order (0-based here)."""
    return _all()[name]


@lru_cache(maxsize=None)
def scs_factors() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """SCS adjustment factors from adjust.scs, read in the order adjscs.c reads them.

    Returns dimfac[306][2][2] (DIM, lactation group, breed group), agefac[121][2] (age in months, breed group) and
    monfac[13][4][2] (fresh month, region, breed group), double precision as fscanf("%lf") gives."""
    tokens = resources.files('bestpred').joinpath('data/adjust.scs').read_text().split()
    values = iter(float(t) for t in tokens)
    dimfac = np.zeros((306, 2, 2))
    agefac = np.zeros((121, 2))
    monfac = np.zeros((13, 4, 2))
    for j in range(2):
        for i in range(15, 306):
            dimfac[i, j, 0] = next(values)
            dimfac[i, j, 1] = next(values)
    for j in range(18, 121):
        agefac[j, 0] = next(values)
        agefac[j, 1] = next(values)
    for j in range(4):
        for i in range(1, 13):
            monfac[i, j, 0] = next(values)
            monfac[i, j, 1] = next(values)
    return dimfac, agefac, monfac


def fortran_reshape(values, shape) -> np.ndarray:
    """A Fortran array constructor (RESHAPE of a list), single precision, column-major."""
    return np.array(values, dtype=np.float32).reshape(shape, order='F')


# Constants written inline in bestpred.f90 (RESHAPE constructors and SAVEd arrays), 0-based, Fortran index order.

LB = F32(2.205)  # pounds per kilogram, as BESTPRED has it

# Monthly test-day means (dyld) and SDs (dsd) of milk, fat, protein (lb) and SCS: (month, trait, parity group).
DYLD = fortran_reshape([
    53.3, 63., 66.3, 65.5, 63.9, 62., 60.1, 58.1, 55.6, 52.3, 49., 47.,
    2.3, 2.32, 2.31, 2.28, 2.25, 2.22, 2.19, 2.16, 2.11, 2.03, 1.95, 1.9,
    1.81, 1.9, 1.99, 2.01, 2.01, 1.99, 1.96, 1.92, 1.87, 1.8, 1.74, 1.67,
    3.38, 2.63, 2.41, 2.44, 2.48, 2.52, 2.57, 2.6, 2.66, 2.74, 2.82, 2.9,
    75.1, 86., 86.9, 82.2, 77.2, 72.2, 67.2, 62.1, 56.2, 49.8, 46., 42.,
    3.33, 3.2, 3.0, 2.85, 2.71, 2.58, 2.45, 2.29, 2.12, 1.92, 1.81, 1.7,
    2.6, 2.55, 2.55, 2.49, 2.4, 2.3, 2.17, 2.04, 1.89, 1.72, 1.62, 1.55,
    3.35, 2.84, 2.8, 2.9, 3.02, 3.15, 3.28, 3.43, 3.58, 3.76, 3.88, 4.0], (12, 4, 2))
DSD = fortran_reshape([
    10.7, 10.6, 9.9, 9.6, 9.5, 9.5, 9.5, 9.6, 9.8, 10.3, 10.7, 11.2,
    .51, .45, .41, .39, .38, .38, .37, .37, .37, .39, .40, .41,
    .34, .31, .28, .28, .28, .29, .29, .29, .30, .32, .33, .34,
    1.51, 1.45, 1.42, 1.41, 1.4, 1.41, 1.41, 1.41, 1.41, 1.42, 1.42, 1.42,
    15., 15.3, 14.4, 13.8, 13.3, 13., 12.9, 13., 13.6, 14.7, 15., 15.5,
    .75, .69, .62, .58, .55, .52, .51, .51, .53, .57, .58, .59,
    .50, .43, .40, .38, .38, .38, .38, .39, .42, .46, .47, .49,
    1.63, 1.69, 1.71, 1.69, 1.66, 1.61, 1.56, 1.51, 1.47, 1.45, 1.44, 1.4], (12, 4, 2))

# Mature breed means (breed A B G H J M, trait, 1995 / 2000) and SDs (breed, trait).
BRDYLD = fortran_reshape([
    15080., 16616., 13864., 20845., 14120., 14472.,
    589., 668., 625., 763., 662., 518.,
    505., 586., 481., 656., 531., 476.,
    3.16, 3.22, 3.35, 3.20, 3.31, 2.87,
    18532., 21577., 16850., 25658., 18161., 17475.,
    713., 867., 745., 935., 833., 624.,
    582., 714., 551., 771., 644., 544.,
    2.95, 2.93, 3.29, 3.08, 3.32, 3.06], (6, 4, 2))
BRDSD = fortran_reshape([
    2300., 2530., 2324., 2946., 2128., 2332.,
    115., 115., 112., 119., 109., 112.,
    92., 92., 92., 97., 89., 92.,
    1.28, 1.21, 1.35, 1.34, 1.18, 1.30], (6, 4))

# Squared correlations of monthly with daily testing (trait, parity group): DCR is 100 for monthly testing.
RMONTH = fortran_reshape([.962, .960, .962, .943, .958, .956, .958, .960], (4, 2))

# Phenotypic correlations among milk, fat, protein and SCS (the same in both parity groups).
MFPCORR = fortran_reshape([
    1., .67, .85, -.08,
    .67, 1., .77, -.14,
    .85, .77, 1., -.10,
    -.08, -.14, -.10, 1.], (4, 4))

# Data collection rating weight of each supervision code 0-9.
DCR_WEIGHT = np.array([0., 1., .77, .97, 1., 1., .77, .97, 1., 1.], dtype=np.float32)

# 3X adjustments (trait, parity 1/2/3+): Karaca (1998) and Kendrick (1953).
NEW3X = fortran_reshape([.12, .09, .10, .00, .14, .10, .11, .00, .14, .10, .11, .00], (4, 3))
OLD3X = fortran_reshape([.20, .20, .20, .00, .17, .17, .17, .00, .15, .15, .15, .00], (4, 3))

X305 = np.array([1., 1., 1., 305.], dtype=np.float32)
X100 = np.array([1., 1., 1., 100.], dtype=np.float32)

BREEDS = 'ABGHJM'
