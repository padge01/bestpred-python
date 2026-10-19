"""The MCP server, called as an agent would call it (the SDK's in-process client)."""

import json

import pytest
from mcp import Client

from bestpred import TestDay, bestpred
from bestpred_mcp.server import build_server

pytestmark = pytest.mark.anyio

TESTS = [{'dim': 12, 'milk': 78.0, 'fat': 4.4, 'protein': 3.2, 'scs': 3.1},
         {'dim': 43, 'milk': 96.5, 'fat': 3.7, 'protein': 2.9, 'scs': 2.0},
         {'dim': 71, 'milk': 99.0, 'fat': 3.5, 'protein': 3.0, 'scs': 1.8},
         {'dim': 104, 'milk': 94.2, 'fat': 3.6, 'protein': 3.1, 'scs': 2.4}]
HERD = """ID,LACT,FDAT,DIM,MILK,PCTF,PCTP,SCS,AGE
101,1,03/01/26,15,62.0,3.9,3.1,2.4,24
101,1,03/01/26,45,75.5,3.6,3.0,2.1,24
101,1,03/01/26,76,78.0,3.5,3.0,2.0,24
202,3,02/10/26,20,98.0,3.8,3.0,2.9,
202,3,02/10/26,52,112.0,3.4,2.9,2.5,
202,3,02/10/26,80,108.5,3.5,3.0,2.6,
303,2,,30,90.0,3.6,3.0,2.2,
"""


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def data(result) -> dict:
    assert not result.is_error, result.content
    return result.structured_content if result.structured_content else json.loads(result.content[0].text)


async def test_the_tools_are_listed_with_titles_and_hints():
    async with Client(build_server()) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
    assert set(tools) == {'lactation', 'expected_curve', 'mature_equivalent_factors', 'herd_lactations'}
    for name, tool in tools.items():
        assert tool.title, name
        assert tool.annotations is not None and tool.annotations.destructive_hint is False, name
        assert 'Never estimate a lactation yourself' in tool.description, name
    assert tools['lactation'].annotations.read_only_hint is True
    assert tools['herd_lactations'].annotations.read_only_hint is False  # local: it writes a new file


async def test_one_cow_matches_bestpred_called_directly():
    direct = bestpred([TestDay(**t) for t in TESTS], herdavg=(0, 0, 0, 0), agefac=(1, 1, 1, 1), cowid='H', parity=2,
                      fresh='20260301')
    async with Client(build_server()) as c:
        got = data(await c.call_tool('lactation', {'tests': TESTS, 'parity': 2, 'fresh': '2026-03-01'}))
    assert got['milk_305'] == round(direct.yields('actual')['milk']['305'])
    assert got['reliability_milk_pct'] == round(100 * float(direct.rel_yield[0]))
    assert 'milk_305_me' not in got and 'age_months and state' in got['note']


async def test_age_gives_mature_equivalent():
    async with Client(build_server()) as c:
        got = data(await c.call_tool('lactation', {'tests': TESTS, 'parity': 1, 'fresh': '2026-03-01',
                                                   'age_months': 24, 'state': 'CA'}))
    assert got['milk_305_me'] > got['milk_305']  # a two-year-old's mature equivalent is above her actual


async def test_expected_curve_is_weekly_to_305():
    async with Client(build_server()) as c:
        got = data(await c.call_tool('expected_curve', {'tests': TESTS, 'parity': 2, 'fresh': '2026-03-01'}))
    pts = got['points']
    assert pts[0]['dim'] == 7 and pts[-1]['dim'] == 301 and all(p['milk'] > 0 for p in pts)


async def test_mature_equivalent_factors():
    async with Client(build_server()) as c:
        got = data(await c.call_tool('mature_equivalent_factors', {'age_months': 24, 'fresh': '2026-03-01',
                                                                   'parity': 1, 'state': 'CA'}))
    assert got['milk'] > 1.0


async def test_a_herd_file_round_trip(tmp_path):
    src = tmp_path / 'tests.csv'
    src.write_text(HERD, encoding='utf-8')
    async with Client(build_server()) as c:
        got = data(await c.call_tool('herd_lactations', {'path': str(src), 'state': 'CA'}))
        again = data(await c.call_tool('herd_lactations', {'path': str(src)}))
    assert got['lactations'] == 2 and got['rows_skipped'] == 1  # cow 303 has no fresh date
    assert set(got['by_parity']) == {'1', '3+'}
    table = (tmp_path / 'tests-bestpred.csv').read_text(encoding='utf-8').splitlines()
    assert table[0].startswith('cow,parity,fresh') and len(table) == 3
    assert 'milk_305_me' in table[0]  # cow 101 has her age
    assert again['table_file'].endswith('tests-bestpred-2.csv')  # the first file is never replaced
    assert 'no state' in again['note']  # ages without a state: actual yields, and it says why


async def test_bad_input_is_a_message_not_a_crash():
    async with Client(build_server()) as c:
        r = await c.call_tool('lactation', {'tests': TESTS, 'parity': 2, 'fresh': 'last spring'})
        h = await c.call_tool('herd_lactations', {'csv_text': 'a,b\n1,2\n'})
    assert r.is_error and "Can't read the date" in r.content[0].text
    assert h.is_error and 'needs columns' in h.content[0].text


async def test_hosted_reads_no_files_and_returns_the_table():
    async with Client(build_server(hosted=True)) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
        got = data(await c.call_tool('herd_lactations', {'csv_text': HERD}))
    assert 'path' not in tools['herd_lactations'].input_schema['properties']
    assert tools['herd_lactations'].annotations.read_only_hint is True
    assert got['table_csv'].splitlines()[0].startswith('cow,parity,fresh')


def test_the_hosted_service_has_its_pages(monkeypatch):
    from starlette.testclient import TestClient

    from bestpred_mcp.hosted import hosted_app

    monkeypatch.delenv('OPENAI_APPS_CHALLENGE', raising=False)
    with TestClient(hosted_app()) as web:
        assert web.get('/').status_code == 200 and 'uvx bestpred-mcp' in web.get('/').text
        assert 'not written to disk' in web.get('/privacy').text
        assert 'not official USDA' in web.get('/terms').text
        assert 'herd_lactations' in web.get('/llms.txt').text
        assert web.get('/.well-known/openai-apps-challenge').status_code == 404
    monkeypatch.setenv('OPENAI_APPS_CHALLENGE', 'token-123')
    with TestClient(hosted_app()) as web:
        assert web.get('/.well-known/openai-apps-challenge').text == 'token-123'


def test_the_hosted_service_refuses_an_oversized_call():
    from starlette.testclient import TestClient

    from bestpred_mcp.hosted import hosted_app

    with TestClient(hosted_app()) as web:
        r = web.post('/mcp', content=b'x' * (6 * 1024 * 1024),
                     headers={'content-type': 'application/json', 'accept': 'application/json, text/event-stream'})
    assert r.status_code == 413


async def test_every_tool_has_an_annotation_title():
    for hosted in (False, True):
        async with Client(build_server(hosted=hosted)) as c:
            for tool in (await c.list_tools()).tools:
                assert tool.annotations.title == tool.title, tool.name
