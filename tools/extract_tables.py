"""Copy BESTPRED's coefficient tables out of the USDA source into bestpred/data/tables.json.

Run once against a checkout of https://github.com/wintermind/bestpred (public domain, USDA-ARS-AGIL):

    python tools/extract_tables.py path/to/bestpred

It reads the C arrays in aiplage.h (age, month and previous-days-open adjustments for milk, fat and protein) and the
Fortran DATA statements in bestpred.f90 (standard lactation curves). Values are stored as written in the source; C
arrays keep their C (row-major) shape, Fortran arrays their Fortran (column-major) shape, and each entry records which.
"""

import json
import re
import sys
from pathlib import Path

# Fortran arrays filled by DATA statements in subroutine interpolate(), with their declared shapes.
FORTRAN_SHAPES = {
    'woods_means': (3, 3, 2, 6),
    'woods_sd': (3, 3, 2, 6),
    'mandg_means': (4, 1, 2, 6),
    'mandg_sd': (4, 1, 2, 6),
    'regional_woods_means': (3, 3, 2, 7),
    'regional_woods_sd': (3, 3, 2, 7),
    'regional_mandg_means': (4, 1, 2, 7),
    'regional_mandg_sd': (4, 1, 2, 7),
    'calving_woods_means': (3, 3, 2, 4),
    'calving_woods_sd': (3, 3, 2, 4),
    'calving_mandg_means': (4, 1, 2, 4),
    'calving_mandg_sd': (4, 1, 2, 4),
    'seasonal_woods_means': (3, 3, 2, 4, 7),
    'seasonal_woods_sd': (3, 3, 2, 4, 7),
    'seasonal_mandg_means': (4, 1, 2, 4, 7),
    'seasonal_mandg_sd': (4, 1, 2, 4, 7),
}

NUMBER = re.compile(r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eEdD][-+]?\d+)?')


def product(shape):
    n = 1
    for s in shape:
        n *= s
    return n


def c_tables(text: str) -> dict:
    text = re.sub(r'/\*.*?\*/', ' ', text, flags=re.S)
    out = {}
    for m in re.finditer(r'\b(float|char|double)\s+(\w+)\s*((?:\[\s*\d+\s*\]\s*)+)=\s*\{(.*?)\}\s*;', text, re.S):
        name = m.group(2)
        shape = tuple(int(d) for d in re.findall(r'\d+', m.group(3)))
        values = [float(v) for v in NUMBER.findall(m.group(4))]
        if len(values) != product(shape):
            raise SystemExit(f'{name}: expected {product(shape)} values, found {len(values)}')
        out[name] = {'order': 'C', 'shape': shape, 'values': values}
    return out


def fortran_tables(text: str) -> dict:
    lines = [re.sub(r'!.*', '', line) for line in text.splitlines()]
    text = '\n'.join(lines).replace('&', ' ')
    out = {}
    for name, shape in FORTRAN_SHAPES.items():
        m = re.search(r'\bdata\s+' + name + r'\s*/([^/]*)/', text, re.I)
        if not m:
            raise SystemExit(f'{name}: DATA statement not found')
        values = [float(v.replace('d', 'e').replace('D', 'e')) for v in NUMBER.findall(m.group(1))]
        if len(values) != product(shape):
            raise SystemExit(f'{name}: expected {product(shape)} values, found {len(values)}')
        out[name] = {'order': 'F', 'shape': shape, 'values': values}
    return out


def main(src: str) -> None:
    root = Path(src)
    tables = {}
    tables.update(c_tables((root / 'aiplage.h').read_text(errors='replace')))
    tables.update(fortran_tables((root / 'bestpred.f90').read_text(errors='replace')))
    dest = Path(__file__).resolve().parents[1] / 'src' / 'bestpred' / 'data' / 'tables.json'
    dest.write_text(json.dumps({'source': 'USDA-ARS-AGIL BESTPRED 2.0rc7 (public domain)', 'tables': tables}))
    print(f'{len(tables)} tables written to {dest}')


if __name__ == '__main__':
    main(sys.argv[1])
