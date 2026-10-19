"""BESTPRED for agents: USDA's best prediction of lactation yields as MCP tools any agent can call.

Run on your own computer over stdio (`bestpred-mcp`), or hosted over streamable HTTP (`bestpred-mcp --http`). Hosted,
it computes only on what it is sent, keeps nothing and reads no files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from . import __version__
from .herd import (InputProblem, Lactation, breed_letter, curve, herd_summary, parse_date, read_herd, rows_to_csv, run,
                   state_code, summary)
from bestpred import TestDay, age_factors

REPORT = (' Report these numbers as they are: they come from USDA\'s best prediction method (BESTPRED 2.0rc7), checked '
          'against USDA\'s own program. Never estimate a lactation yourself.')
INSTRUCTIONS = (
    "USDA's best prediction (BESTPRED) of dairy lactation yields: 305-day and 365-day milk, fat and protein, mature "
    'equivalent when the age is known, reliability and persistency, from a cow\'s test days. Use herd_lactations for a '
    "herd's test-day export, lactation for one cow, expected_curve for a cow's expected daily milk, and "
    'mature_equivalent_factors for USDA\'s age factors. Pounds unless the user works in kilograms.' + REPORT
)
READ_ONLY = dict(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
# Local herd_lactations writes its table to a new file and never overwrites one.
WRITES_NEW_FILE = dict(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
HOSTED_MAX_LACTATIONS = 5000
HOSTED_TABLE_ROWS = 300


class MilkTest(BaseModel):
    """One test day."""

    dim: int = Field(description='Days in milk on the test day')
    milk: float = Field(description='Milk that day, lb (or kg)')
    fat: float = Field(0.0, description='Fat %, 0 if not tested')
    protein: float = Field(0.0, description='Protein %, 0 if not tested')
    scs: float = Field(0.0, description='Somatic cell score (linear score, 0-9.9), 0 if not tested')


HerdAverage = Annotated[float, Field(description="The herd's 305-day mature-equivalent average; 0 if unknown (the "
                                                 'breed average is used)')]


def _lactation(tests: list[MilkTest], parity: int, fresh: str, breed: str, age_months: int | None,
               prev_days_open: int) -> Lactation:
    usable = [TestDay(dim=t.dim, milk=t.milk, fat=t.fat, protein=t.protein, scs=t.scs) for t in tests
              if t.dim > 0 and t.milk > 0]
    return Lactation(cow='this cow', parity=parity, fresh=parse_date(fresh), tests=sorted(usable, key=lambda t: t.dim),
                     breed=breed_letter(breed), age_months=age_months, prev_days_open=prev_days_open)


def _new_file(path: Path) -> Path:
    """`path`, or the same name with -2, -3 ... when a file is already there: an existing file is never replaced."""
    n, candidate = 2, path
    while candidate.exists():
        candidate = path.with_name(f'{path.stem}-{n}{path.suffix}')
        n += 1
    return candidate


def build_server(hosted: bool = False) -> MCPServer:
    """The server. `hosted` drops the file path inputs and caps what one call may send."""
    mcp = MCPServer('bestpred', title='BESTPRED lactation records', instructions=INSTRUCTIONS, version=__version__,
                    website_url='https://github.com/padge01/bestpred-python')

    @mcp.tool(title='One cow\'s lactation record', annotations=ToolAnnotations(title='One cow\'s lactation record', **READ_ONLY),
              description='Best prediction for one cow from her test days: 305-day and 365-day milk, fat and protein '
                          '(and mature equivalent when age_months is given), reliability, persistency and data '
                          'collection rating.' + REPORT)
    def lactation(tests: list[MilkTest], parity: int, fresh: str, breed: str = 'H', age_months: int | None = None,
                  prev_days_open: int = 0, state: str = '', herd_milk: HerdAverage = 0, herd_fat: HerdAverage = 0,
                  herd_protein: HerdAverage = 0, herd_scs: HerdAverage = 0, units: str = 'lb') -> dict:
        try:
            lac = _lactation(tests, parity, fresh, breed, age_months, prev_days_open)
            res, me_known = run(lac, (herd_milk, herd_fat, herd_protein, herd_scs), units, state_code(state))
        except (InputProblem, ValueError) as e:
            raise ToolError(str(e)) from e
        out = summary(lac, res, me_known, units)
        out.pop('cow')
        if not me_known:
            out['note'] = 'Mature equivalent not given: it needs age_months and state.'
        return out

    @mcp.tool(title='A cow\'s expected daily milk', annotations=ToolAnnotations(title='A cow\'s expected daily milk', **READ_ONLY),
              description='A cow\'s expected daily milk to day 305 from her test days (her herd curve plus her own '
                          'deviation), one point every `every` days, to compare with what she is giving.' + REPORT)
    def expected_curve(tests: list[MilkTest], parity: int, fresh: str, breed: str = 'H', every: int = 7,
                       herd_milk: HerdAverage = 0, units: str = 'lb') -> dict:
        try:
            lac = _lactation(tests, parity, fresh, breed, None, 0)
            res, _ = run(lac, (herd_milk, 0, 0, 0), units, 0)
        except (InputProblem, ValueError) as e:
            raise ToolError(str(e)) from e
        return {'units': units, 'points': curve(res, every=max(1, min(int(every), 30)))}

    @mcp.tool(title='Mature-equivalent factors', annotations=ToolAnnotations(title='Mature-equivalent factors', **READ_ONLY),
              description="USDA's factors that turn a cow's actual 305-day milk, fat and protein into mature "
                          'equivalent, for her breed, age at calving, calving month, parity, state and previous days '
                          'open.' + REPORT)
    def mature_equivalent_factors(age_months: int, fresh: str, parity: int, state: str, breed: str = 'H',
                                  prev_days_open: int = 0) -> dict:
        try:
            d = parse_date(fresh)
            f = age_factors(breed_letter(breed), int(age_months), d.year, d.month, parity, state_code(state),
                            int(prev_days_open))
        except (InputProblem, ValueError) as e:
            raise ToolError(str(e)) from e
        return {'milk': round(float(f[0]), 4), 'fat': round(float(f[1]), 4), 'protein': round(float(f[2]), 4)}

    herd_doc = ("Best prediction for every lactation in a herd's test-day export (CSV, one row per cow per test; DHI or "
                'DairyComp columns such as ID, LACT, FDAT, DIM or TDAT, MILK, PCTF, PCTP, SCS; AGE in months adds '
                'mature equivalent). Returns a summary by parity and the least persistent cows')

    def herd(lacs: list[Lactation], skipped: int, herd_avg, units: str, state: int) -> tuple[list[dict], dict]:
        rows, problems = [], []
        for lac in lacs:
            try:
                res, me_known = run(lac, herd_avg, units, state)
                rows.append(summary(lac, res, me_known, units))
            except (InputProblem, ValueError) as e:
                problems.append(f'{lac.cow}: {e}')
        if not rows:
            raise ToolError('No lactation could be computed. ' + ' '.join(problems[:3]))
        out = {'lactations': len(rows), 'rows_skipped': skipped, 'units': units, **herd_summary(rows)}
        if not state and any(lac.age_months is not None for lac in lacs):
            out['note'] = 'Ages were given but no state: mature equivalent needs the state too.'
        if problems:
            out['not_computed'] = problems[:10]
        return rows, out

    if hosted:
        @mcp.tool(title='A herd\'s lactation records', annotations=ToolAnnotations(title='A herd\'s lactation records', **READ_ONLY),
                  description=herd_doc + '; with the full table when the herd is small.' + REPORT)
        def herd_lactations(csv_text: str, state: str = '', herd_milk: HerdAverage = 0, herd_fat: HerdAverage = 0,
                            herd_protein: HerdAverage = 0, herd_scs: HerdAverage = 0, units: str = 'lb') -> dict:
            try:
                lacs, skipped = read_herd(csv_text)
                if len(lacs) > HOSTED_MAX_LACTATIONS:
                    raise InputProblem(f'{len(lacs):,} lactations is more than the hosted limit of '
                                       f'{HOSTED_MAX_LACTATIONS:,}. Install it locally: uvx bestpred-mcp')
                rows, out = herd(lacs, skipped, (herd_milk, herd_fat, herd_protein, herd_scs), units,
                                 state_code(state))
            except (InputProblem, ValueError) as e:
                raise ToolError(str(e)) from e
            if len(rows) <= HOSTED_TABLE_ROWS:
                out['table_csv'] = rows_to_csv(rows)
            else:
                out['table'] = f'{len(rows):,} rows: too many to send back here. Installed locally, it writes a file.'
            return out
    else:
        @mcp.tool(title='A herd\'s lactation records', annotations=ToolAnnotations(title='A herd\'s lactation records', **WRITES_NEW_FILE),
                  description=herd_doc + '; the full table is written to a new file beside the input (or `out_path`).'
                              + ' Give `path` to a CSV on this computer, or `csv_text`.' + REPORT)
        def herd_lactations(path: str = '', csv_text: str = '', out_path: str = '', state: str = '',
                            herd_milk: HerdAverage = 0, herd_fat: HerdAverage = 0, herd_protein: HerdAverage = 0,
                            herd_scs: HerdAverage = 0, units: str = 'lb') -> dict:
            try:
                if path:
                    src = Path(path).expanduser()
                    if not src.is_file():
                        raise InputProblem(f'No file at {src}.')
                    text = src.read_text(encoding='utf-8-sig', errors='replace')
                elif csv_text:
                    src, text = None, csv_text
                else:
                    raise InputProblem('Give `path` to a test-day CSV, or `csv_text`.')
                lacs, skipped = read_herd(text)
                rows, out = herd(lacs, skipped, (herd_milk, herd_fat, herd_protein, herd_scs), units,
                                 state_code(state))
                dest = _new_file(Path(out_path).expanduser() if out_path else (
                    src.with_name(src.stem + '-bestpred.csv') if src else Path.cwd() / 'bestpred-lactations.csv'))
                dest.write_text(rows_to_csv(rows), encoding='utf-8')
            except (InputProblem, ValueError, OSError) as e:
                raise ToolError(str(e)) from e
            out['table_file'] = str(dest)
            return out

    return mcp
