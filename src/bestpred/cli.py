"""bestpred FILE: run Format 4 records (one lactation per line) and print results_v2.dcr lines, as USDA's program does."""

import argparse
import json
import sys

from .core import TRAITS, Settings
from .format4 import Format4, results_line, run_format4, with_length_from_tests


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog='bestpred', description=__doc__)
    ap.add_argument('file', help='Format 4 records, one per line ("-" for standard input)')
    ap.add_argument('--json', action='store_true', help='print one JSON object per lactation instead')
    ap.add_argument('--mtrait', type=int, default=3, choices=(1, 3, 4))
    ap.add_argument('--use3x', type=int, default=3, choices=(0, 1, 2, 3))
    ap.add_argument('--laclen', type=int, default=305)
    ap.add_argument('--method', default='W', choices=tuple('LWRCT'))
    ap.add_argument('--method-scs', default='G', choices=tuple('LGSDU'))
    ap.add_argument('--units', default='P', choices=('P', 'K'), help='pounds or kilograms, in and out')
    ap.add_argument('--keep-length', action='store_true',
                    help="use the record's own length (USDA's program replaces it with the last test day)")
    args = ap.parse_args(argv)
    settings = Settings(mtrait=args.mtrait, use3X=args.use3x, laclen=args.laclen, method=args.method,
                        method_scs=args.method_scs, units_in=args.units, units_out=args.units)
    stream = sys.stdin if args.file == '-' else open(args.file)
    with stream:
        for line in stream:
            if not line.strip():
                continue
            rec = Format4.parse(line)
            if not args.keep_length:
                rec = with_length_from_tests(rec)
            res = run_format4(rec, settings)
            if args.json:
                print(json.dumps({
                    'cowid': rec.cowid.strip(), 'fresh': rec.fresh, 'parity': rec.lacno,
                    'actual': res.yields('actual'), 'mature_equivalent': res.yields('me'),
                    'persistency': dict(zip(TRAITS, res.persistency.tolist())),
                    'reliability': dict(zip(TRAITS, res.rel_yield.tolist())),
                    'persistency_reliability': dict(zip(TRAITS, res.rel_persistency.tolist())),
                    'dcr': {'milk': res.dcr_milk, 'components': res.dcr_components, 'scs': res.dcr_scs},
                    'tests': dict(zip(TRAITS, res.ntests.tolist())),
                }, default=float))
            else:
                print(results_line(rec, res))
    return 0


if __name__ == '__main__':
    sys.exit(main())
