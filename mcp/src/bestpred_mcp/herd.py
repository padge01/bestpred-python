"""Turn the inputs an agent has (a cow's test days, or a herd's test-day export) into bestpred calls, and the results
into short summaries. Nothing here is a new calculation: every figure comes from bestpred()."""

from __future__ import annotations

import csv
import io
import statistics
from dataclasses import dataclass
from datetime import date, datetime

from bestpred import Settings, TestDay, age_factors, bestpred

# USDA's 2-digit state codes (BESTPRED's ClimateRegions file), by postal code.
STATES = {
    'ME': 11, 'NH': 12, 'VT': 13, 'MA': 14, 'RI': 15, 'CT': 16, 'NY': 21, 'NJ': 22, 'PA': 23, 'OH': 31, 'IN': 32,
    'IL': 33, 'MI': 34, 'WI': 35, 'MN': 41, 'IA': 42, 'MO': 43, 'ND': 45, 'SD': 46, 'NE': 47, 'KS': 48, 'DE': 50,
    'MD': 51, 'VA': 52, 'WV': 54, 'NC': 55, 'SC': 56, 'GA': 57, 'FL': 58, 'KY': 61, 'TN': 63, 'AL': 64, 'MS': 65,
    'AR': 71, 'LA': 72, 'OK': 73, 'TX': 74, 'MT': 81, 'ID': 82, 'WY': 83, 'CO': 84, 'NM': 85, 'AZ': 86, 'UT': 87,
    'NV': 88, 'WA': 91, 'OR': 92, 'CA': 93, 'PR': 94, 'HI': 95, 'AK': 96,
}
BREEDS = {'A': 'Ayrshire', 'B': 'Brown Swiss', 'G': 'Guernsey', 'H': 'Holstein', 'J': 'Jersey', 'M': 'Milking Shorthorn'}


class InputProblem(ValueError):
    """Something in the input the agent should fix; the message says what."""


def state_code(state: str | int | None) -> int:
    """A state as USDA's 2-digit code, from a postal code ('CA') or the code itself (93). 0 when not given."""
    if state is None or state == '':
        return 0
    text = str(state).strip().upper()
    if text.isdigit():
        code = int(text)
        if not 0 <= code <= 96:
            raise InputProblem(f'State code {code} is outside USDA\'s table (0-96).')
        return code
    if text in STATES:
        return STATES[text]
    raise InputProblem(f"Unknown state '{state}'. Give a 2-letter postal code (CA, WI, ...) or USDA's 2-digit code.")


def parse_date(text: str) -> date:
    """A calving or test date as YYYY-MM-DD, YYYYMMDD, MM/DD/YY or MM/DD/YYYY (DairyComp writes MM/DD/YY)."""
    t = str(text).strip()
    for fmt in ('%Y-%m-%d', '%Y%m%d', '%m/%d/%y', '%m/%d/%Y'):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    raise InputProblem(f"Can't read the date '{text}'. Use YYYY-MM-DD or MM/DD/YY.")


def breed_letter(breed: str | None) -> str:
    b = (breed or 'H').strip().upper()[:1]
    if b not in BREEDS:
        raise InputProblem(f"Unknown breed '{breed}'. Use one of {', '.join(f'{k} ({v})' for k, v in BREEDS.items())}.")
    return b


@dataclass
class Lactation:
    """One cow's lactation as bestpred needs it."""

    cow: str
    parity: int
    fresh: date
    tests: list[TestDay]
    breed: str = 'H'
    age_months: int | None = None
    prev_days_open: int = 0


def settings(units: str) -> Settings:
    u = units.strip().lower()
    if u not in ('lb', 'kg'):
        raise InputProblem("Units must be 'lb' or 'kg'.")
    p = 'P' if u == 'lb' else 'K'
    return Settings(units_in=p, units_out=p)


def run(lac: Lactation, herd_avg: tuple[float, float, float, float], units: str, state: int):
    """bestpred() for one lactation, with USDA's mature-equivalent factors when the cow's age and state are known."""
    if not lac.tests:
        raise InputProblem(f'Cow {lac.cow} has no usable test days (each needs days in milk above 0 and milk above 0).')
    if lac.parity < 1:
        raise InputProblem(f'Cow {lac.cow}: parity must be 1 or more.')
    # USDA's age factors need the state (its region) as well as the age; without both, actual yields only.
    me_known = lac.age_months is not None and state > 0
    if me_known:
        agefac = age_factors(lac.breed, int(lac.age_months), lac.fresh.year, lac.fresh.month, lac.parity, state,
                             int(lac.prev_days_open))
    else:
        agefac = (1.0, 1.0, 1.0, 1.0)
    res = bestpred(lac.tests, herdavg=herd_avg, agefac=agefac, cowid=lac.breed, fresh=lac.fresh.strftime('%Y%m%d'),
                   parity=lac.parity, herdstate=f'{state:02d}', settings=settings(units))
    return res, me_known


def summary(lac: Lactation, res, me_known: bool, units: str) -> dict:
    """The figures an agent should report, rounded as a DHI sheet shows them."""
    act, me = res.yields('actual'), res.yields('me')
    out = {
        'cow': lac.cow, 'parity': lac.parity, 'fresh': lac.fresh.isoformat(), 'tests': int(res.ntests[0]),
        'last_test_dim': max(t.dim for t in lac.tests), 'units': units,
        'milk_305': round(act['milk']['305']), 'fat_305': round(act['fat']['305']),
        'protein_305': round(act['protein']['305']), 'milk_365': round(act['milk']['365']),
        'milk_to_date': round(act['milk']['to_date']),
        'reliability_milk_pct': round(100 * float(res.rel_yield[0])),
        'persistency_milk': round(float(res.persistency[0]), 2),
        'data_collection_rating': round(float(res.dcr_milk)),
    }
    if me_known:
        out.update({'milk_305_me': round(me['milk']['305']), 'fat_305_me': round(me['fat']['305']),
                    'protein_305_me': round(me['protein']['305'])})
    return out


def curve(res, every: int = 7, through: int = 305) -> list[dict]:
    """The cow's expected daily milk (actual basis): her herd curve plus her own deviation, every `every` days."""
    herd, own = res.daily_herd[1, 0], res.daily_bp[1, 0]
    return [{'dim': d, 'milk': round(float(herd[d] + own[d]), 1)} for d in range(every, through + 1, every)]


# A herd's test-day export: one row per cow per test. Column names are matched loosely, as DHI and DairyComp exports
# name them differently.
COLUMNS = {
    'cow': ('cow', 'id', 'cowid', 'cow_id', 'animal'),
    'parity': ('parity', 'lact', 'lactation', 'lacno'),
    'fresh': ('fresh', 'fdat', 'fresh_date', 'calving', 'calving_date'),
    'dim': ('dim', 'days_in_milk'),
    'test_date': ('test_date', 'tdat', 'date'),
    'milk': ('milk', 'milk_lb', 'milk_kg'),
    'fat': ('fat', 'fat_pct', 'pctf', 'fat%'),
    'protein': ('protein', 'protein_pct', 'pctp', 'prot', 'protein%'),
    'scs': ('scs', 'linear_score', 'ls'),
    'breed': ('breed', 'cbrd'),
    'age_months': ('age_months', 'age'),
    'prev_days_open': ('prev_days_open', 'pdopn', 'previous_days_open'),
}
NEEDED = ('cow', 'parity', 'fresh', 'milk')


def _header_map(fields: list[str]) -> dict[str, str]:
    norm = {f.strip().lower().replace(' ', '_'): f for f in fields if f}
    found = {}
    for key, names in COLUMNS.items():
        for n in names:
            if n in norm:
                found[key] = norm[n]
                break
    missing = [k for k in NEEDED if k not in found]
    if 'dim' not in found and 'test_date' not in found:
        missing.append('dim (or test_date)')
    if missing:
        raise InputProblem(f"The test-day file needs columns for: {', '.join(missing)}. Found: {', '.join(fields)}.")
    return found


def _num(row: dict, col: str | None, default: float = 0.0) -> float:
    if not col:
        return default
    v = (row.get(col) or '').strip()
    if not v:
        return default
    try:
        return float(v)
    except ValueError:
        return default


def read_herd(text: str) -> tuple[list[Lactation], int]:
    """Group a test-day CSV into lactations (cow, parity, fresh date). Returns them and the count of rows skipped."""
    reader = csv.DictReader(io.StringIO(text.lstrip('﻿')))
    cols = _header_map(reader.fieldnames or [])
    groups: dict[tuple, Lactation] = {}
    skipped = 0
    for row in reader:
        cow = (row.get(cols['cow']) or '').strip()
        if not cow:
            skipped += 1
            continue
        try:
            fresh = parse_date(row[cols['fresh']])
            parity = int(_num(row, cols['parity']))
        except (InputProblem, KeyError):
            skipped += 1
            continue
        if 'dim' in cols:
            dim = int(_num(row, cols['dim']))
        else:
            try:
                dim = (parse_date(row[cols['test_date']]) - fresh).days
            except InputProblem:
                skipped += 1
                continue
        milk = _num(row, cols['milk'])
        if dim <= 0 or milk <= 0 or parity < 1:
            skipped += 1
            continue
        key = (cow, parity, fresh)
        if key not in groups:
            age = row.get(cols.get('age_months', ''), '') if 'age_months' in cols else ''
            groups[key] = Lactation(cow=cow, parity=parity, fresh=fresh, tests=[],
                                    breed=breed_letter(row.get(cols['breed']) if 'breed' in cols else 'H'),
                                    age_months=int(float(age)) if str(age).strip() else None,
                                    prev_days_open=int(_num(row, cols.get('prev_days_open'))))
        groups[key].tests.append(TestDay(dim=dim, milk=milk, fat=_num(row, cols.get('fat')),
                                         protein=_num(row, cols.get('protein')), scs=_num(row, cols.get('scs'))))
    lacs = list(groups.values())
    for lac in lacs:
        lac.tests.sort(key=lambda t: t.dim)
    return lacs, skipped


def herd_summary(rows: list[dict]) -> dict:
    """By parity group (1, 2, 3 and later): cows, median 305-day milk, reliability and persistency; the five cows with the
    least persistent lactations."""
    groups = {}
    for label, test in (('1', lambda p: p == 1), ('2', lambda p: p == 2), ('3+', lambda p: p >= 3)):
        g = [r for r in rows if test(r['parity'])]
        if g:
            groups[label] = {
                'lactations': len(g),
                'median_milk_305': round(statistics.median(r['milk_305'] for r in g)),
                'median_reliability_pct': round(statistics.median(r['reliability_milk_pct'] for r in g)),
                'median_persistency': round(statistics.median(r['persistency_milk'] for r in g), 2),
            }
    least = sorted(rows, key=lambda r: r['persistency_milk'])[:5]
    return {'by_parity': groups,
            'least_persistent': [{'cow': r['cow'], 'parity': r['parity'], 'persistency_milk': r['persistency_milk']}
                                 for r in least]}


def rows_to_csv(rows: list[dict]) -> str:
    keys: list[str] = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=keys, lineterminator='\n')
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()
