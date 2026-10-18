# bestpred-mcp

USDA's best prediction of dairy lactation yields ([bestpred](https://github.com/padge01/bestpred-python), the
Python port of BESTPRED 2.0rc7) as tools any AI agent can call. An agent can't work out a lactation record in its head;
with this it runs the method USDA uses for official records, and reports the numbers it gets back.

It is an MCP server. MCP is the open standard agents use for tools, so the same server works in Claude, ChatGPT and
Codex, Cursor, VS Code and Gemini CLI.

## Install

You need [uv](https://docs.astral.sh/uv/) (it runs the server; nothing else to install).

```bash
uvx bestpred-mcp
```

- **Claude Code:** `claude mcp add bestpred -- uvx bestpred-mcp`
- **Claude Desktop, Cursor, Gemini CLI:** add to the app's MCP settings file:

  ```json
  { "mcpServers": { "bestpred": { "command": "uvx", "args": ["bestpred-mcp"] } } }
  ```

- **VS Code** (`.vscode/mcp.json`): `{ "servers": { "bestpred": { "command": "uvx", "args": ["bestpred-mcp"] } } }`
- **Codex plugin** (with the skill): `codex plugin marketplace add padge01/bestpred-python`, then install BESTPRED from
  the Plugins tab.
- **Codex, the server alone** (`~/.codex/config.toml`):

  ```toml
  [mcp_servers.bestpred]
  command = "uvx"
  args = ["bestpred-mcp"]
  ```

Then ask your agent, for example: "Work out 305-day milk for every cow in `tests.csv`".

## The tools

| Tool | What it does |
|---|---|
| `herd_lactations` | A herd's test-day export (CSV, one row per cow per test) to a record for every lactation: a summary by parity, the least persistent cows, and the full table written to a new file beside the input. Columns are matched loosely: `ID`, `LACT`, `FDAT`, `DIM` (or `TDAT`), `MILK`, `PCTF`, `PCTP`, `SCS`; `AGE` in months adds mature equivalent. |
| `lactation` | One cow's test days to 305-day and 365-day milk, fat and protein, mature equivalent (with her age), reliability, persistency and data collection rating. |
| `expected_curve` | A cow's expected daily milk to day 305 from her test days, to compare with what she is giving. |
| `mature_equivalent_factors` | USDA's age factors for a breed, age at calving, calving month, parity, state and previous days open. |

Pounds by default; pass `units: "kg"` for kilograms. With no herd average given, the breed average is used.

## What stays on your computer

Run this way, the server runs on your computer: your files are read there and the table is written there. What your
agent shows the AI model (the summary it reads back) goes to that model's company, as everything in a chat does.

`bestpred-mcp --http` serves the same tools over HTTP for hosting. Hosted, it reads no files, keeps nothing, and takes
at most 5,000 lactations a call.

## Licence

Apache-2.0. BESTPRED is USDA-ARS public-domain work (VanRaden; Cole and VanRaden); this is not affiliated with or
endorsed by USDA. See the main repository's NOTICE.
