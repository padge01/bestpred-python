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

- In Claude, it connects to the hosted BESTPRED service at `https://bestpred.dairydatascience.com/mcp`: no install,
  and it works in Claude Code, Cowork and the Claude apps. The test days Claude sends with a call go there, are used only
  to compute that answer, and are not stored or logged (privacy policy: https://bestpred.dairydatascience.com/privacy).
- In Codex, it runs the server on your own computer instead (`uvx bestpred-mcp==0.2.1`, which needs
  [uv](https://docs.astral.sh/uv/)); your files stay there.
- To keep everything on your own computer in Claude too, skip the plugin and add the server yourself:
  `claude mcp add bestpred -- uvx bestpred-mcp`.
- What Claude reads back from the tools goes to Anthropic as part of your conversation, like anything else in a chat.

## Source and licence

Source: https://github.com/padge01/bestpred-python (the library in `src/`, the server in `mcp/`). Apache-2.0.
BESTPRED is USDA-ARS public-domain work; this is not affiliated with or endorsed by USDA.
