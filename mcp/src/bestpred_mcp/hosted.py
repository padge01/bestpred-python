"""The server as a hosted web service: the MCP endpoint at /mcp, and the pages the Claude and OpenAI directories ask
for (what it is, privacy, llms.txt, OpenAI's domain check). Stateless: every call computes and forgets."""

from __future__ import annotations

import os

from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, PlainTextResponse, Response

from . import __version__
from .server import HOSTED_MAX_LACTATIONS, build_server

MAX_BODY = 5 * 1024 * 1024
SOURCE = 'https://github.com/padge01/bestpred-python'
ISSUES = SOURCE + '/issues'

PAGE = f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>BESTPRED for agents</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;max-width:46rem;margin:2rem auto;padding:0 1rem;color:#1a1a1a}}
code{{background:#f2f2f0;padding:.1em .3em;border-radius:4px}}</style>
<h1>BESTPRED for agents</h1>
<p>USDA's best prediction of dairy lactation yields (BESTPRED 2.0rc7, ported to Python and checked against USDA's own
program), as tools an AI agent can call: 305-day and mature-equivalent milk, fat and protein, reliability and
persistency from a cow's or a herd's test days.</p>
<p>MCP endpoint: <code>/mcp</code> (streamable HTTP, no sign-in). Tools: <code>herd_lactations</code>,
<code>lactation</code>, <code>expected_curve</code>, <code>mature_equivalent_factors</code>.</p>
<p>To keep your test days on your own computer, run it there instead: <code>uvx bestpred-mcp</code>.</p>
<p><a href="/privacy">Privacy</a> · <a href="/terms">Terms</a> · <a href="{SOURCE}">Source and install lines</a> · <a href="{ISSUES}">Support</a>
· version {__version__}</p></html>"""

PRIVACY = f"""Privacy: BESTPRED for agents (hosted)

What is sent: the test days your agent sends with a tool call (days in milk, milk, fat %, protein %, somatic cell score,
parity, calving date, and optionally cow IDs, breed, age and state), and the request's ordinary network details.

How it is used: only to compute the records you asked for, in memory, during that call. The answer goes back to your
agent.

What is kept: nothing. Test days and results are not written to disk, logged or kept after the call. The hosting
provider keeps standard request logs (time, size, status), not the request's contents.

Shared with: no one. No third parties, no analytics, no advertising, no training.

Limits: at most {HOSTED_MAX_LACTATIONS:,} lactations and 5 MB a call.

To keep your data on your own computer entirely, run the same tools locally: uvx bestpred-mcp

Contact: {ISSUES}
"""

TERMS = f"""Terms of use: BESTPRED for agents (hosted)

The service is free, with no sign-in, provided as is, with no warranty and no promise that it stays available.

The numbers come from USDA's best prediction method (BESTPRED 2.0rc7) as ported to Python and checked against USDA's own
program. They are estimates for herd management and research, not official USDA or DHI records. This service is not a
product of, or endorsed by, USDA.

Use it fairly: at most {HOSTED_MAX_LACTATIONS:,} lactations and 5 MB a call; no attempts to overload or break it.

The code is Apache-2.0: {SOURCE}. Privacy: /privacy. Contact: {ISSUES}
"""

LLMS = """# BESTPRED for agents (hosted)

> USDA's best prediction of dairy lactation yields as MCP tools. Endpoint: /mcp (streamable HTTP, no sign-in).

- herd_lactations: a herd's test-day CSV (csv_text; ID, LACT, FDAT, DIM or TDAT, MILK, PCTF, PCTP, SCS, AGE) to a
  record per lactation, a summary by parity and the least persistent cows
- lactation: one cow's test days to her record
- expected_curve: a cow's expected daily milk to day 305
- mature_equivalent_factors: USDA's age factors

Report the numbers the tools return as they are; never estimate a lactation record. Run locally instead: uvx bestpred-mcp
"""


def hosted_app(allowed_hosts: list[str] | None = None) -> Starlette:
    """The hosted service. `allowed_hosts` (e.g. ['bestpred.example.com']) turns on the Host header check; behind a
    proxy that already checks it, leave it empty."""
    mcp = build_server(hosted=True)

    @mcp.custom_route('/', methods=['GET'])
    async def home(_: Request) -> Response:
        return HTMLResponse(PAGE)

    @mcp.custom_route('/privacy', methods=['GET'])
    async def privacy(_: Request) -> Response:
        return PlainTextResponse(PRIVACY)

    @mcp.custom_route('/terms', methods=['GET'])
    async def terms(_: Request) -> Response:
        return PlainTextResponse(TERMS)

    @mcp.custom_route('/llms.txt', methods=['GET'])
    async def llms(_: Request) -> Response:
        return PlainTextResponse(LLMS)

    @mcp.custom_route('/.well-known/openai-apps-challenge', methods=['GET'])
    async def challenge(_: Request) -> Response:
        token = os.environ.get('OPENAI_APPS_CHALLENGE', '').strip()
        return PlainTextResponse(token) if token else PlainTextResponse('', status_code=404)

    security = TransportSecuritySettings(enable_dns_rebinding_protection=bool(allowed_hosts),
                                         allowed_hosts=list(allowed_hosts or []))
    return mcp.streamable_http_app(json_response=True, stateless_http=True, max_request_body_size=MAX_BODY,
                                   transport_security=security, host='0.0.0.0')
