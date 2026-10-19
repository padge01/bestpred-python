# bestpred

USDA's best prediction of dairy lactation yields (BESTPRED 2.0rc7, ported to Python and checked against USDA's own
program), for Claude and Codex. Ask for 305-day milk, mature equivalent, reliability or persistency from a herd's test days, and
Claude runs the method USDA uses for official lactation records instead of estimating the numbers itself.

## What it adds

- **Four tools** (an MCP server): a herd's test-day export (DHI or DairyComp columns) to a record for every lactation;
  one cow's record; a cow's expected daily milk to day 305; and USDA's mature-equivalent age factors.
- **A skill, lactation-records**: how to prepare test days, which tool to use, and how to read 305-day, mature
  equivalent, reliability and persistency.

## What it runs, reads and sends

- It runs one program on your computer: the `bestpred-mcp` server, with `uv run --locked` (in Codex, `uvx
  bestpred-mcp==0.2.1`). The first time, uv downloads it and its dependencies (`bestpred`, NumPy, the MCP SDK) from
  PyPI, at the exact versions and checksums in this folder's `uv.lock`. It needs [uv](https://docs.astral.sh/uv/).
- It reads only the test-day file you point it at, and writes its table to a new file beside it. It never overwrites a
  file.
- It sends nothing anywhere itself: no network calls, no telemetry. What Claude reads back from the tools (the
  summary) goes to Anthropic as part of your conversation, like anything else in a chat.

## Source and licence

Source: https://github.com/padge01/bestpred-python (the library in `src/`, the server in `mcp/`). Apache-2.0.
BESTPRED is USDA-ARS public-domain work; this is not affiliated with or endorsed by USDA.
