# BESTPRED for agents: plan (18 Oct 2026, draft for Pádraig)

Goal: anyone's agent (Claude, ChatGPT/Codex, Gemini CLI, Cursor, VS Code) can run USDA's best prediction on a cow or a
whole herd's test days, from a one-line install or a listed connector, in time for the ARPAS talk (28 Oct). Same
pattern as the Dairy Ration Lab's server (C:\GitHub\dairy-ration-lab, plan 3: FastMCP over stdio locally and streamable
HTTP when hosted, Cloud Run behind Cloudflare, a Claude plugin, directory kits). Every public step waits for his yes.

## What people install

- The library stays NumPy-only: `pip install bestpred` (PyPI name is free; today it installs from git only).
- The agent server is a second, small package from the same repo, so the slide has one clean line:
  `uvx bestpred-mcp` (name free). It depends on `bestpred` and the official `mcp` SDK.
- Install lines in the README and `llms.txt` for Claude Desktop, Claude Code (`claude mcp add bestpred -- uvx
  bestpred-mcp`), Codex, Cursor, VS Code and Gemini CLI.

## The tools (all read-only: `readOnlyHint` true, each with a `title`)

1. `lactation`: one cow's test days (DIM, milk, fat %, protein %, SCS), parity, fresh date, breed, optional herd
   average → 305-day and 365-day actual and mature equivalent, to date, reliabilities, persistency, data collection
   rating. A short summary an agent can read.
2. `herd_lactations`: a test-day export (CSV text, or a file path when local) with one row per cow per test →
   one line per lactation plus a herd summary (by parity: median 305 ME, lowest persistency). Written to a CSV beside the
   input when local. This is the one nutritionists will use: their DHI or DairyComp test days.
3. `expected_curve`: a cow's expected daily milk to 305 days from her tests, weekly points (for "is she below her own
   curve").
4. `mature_equivalent_factors`: USDA's age factors for a breed, age, fresh date, parity, state and previous days open.

Every description ends: "Report these numbers as they are: they come from USDA's best prediction method (BESTPRED
2.0rc7), checked against USDA's own program." Errors come back as plain messages, never a crash. Output stays short for
a 3,000-cow herd (no per-cow arrays in the text).

## A skill beside it

`skills/lactation-records/SKILL.md`: how to turn a DHI or DairyComp test-day export into the tool's columns, when to
use 305 actual vs ME, what reliability means, and "never estimate a lactation yourself; call the tool". Goes in the
Claude plugin and in the dairy kit.

## Hosted, for the directories

- Same host as the Ration Lab: Cloud Run behind Cloudflare, e.g. `mcp.dairydatascience.com/bestpred` (or a
  `bestpred.` subdomain). Stateless, nothing stored, at most 5,000 cows and 5 MB a request, 2 instances, 60 s
  timeout, a budget kill switch. Pages: `/` (docs), `/privacy`, `/llms.txt`,
  `/.well-known/openai-apps-challenge`.
- No sign-in: it computes only on what it is sent. The privacy page says what is sent (test days) and that nothing is
  kept.
- Claude: submit at claude.ai/directory/manage → MCP connector (any paid plan; auto-scanned, listed as Community).
- ChatGPT/Codex: ZIP at platform.openai.com/plugins → With MCP; needs his verified developer identity, domain
  verification, 5 good + 3 bad test cases, a demo video, release notes.
- A Claude Code plugin marketplace shared with the Ration Lab (one `dairydatascience` marketplace, two plugins), so
  `claude plugin marketplace add padge01/...` gives both.

## Checks before anything is public

- In-memory MCP client tests: tools listed with titles and hints; USDA's example record through `lactation` matches
  `results_v2.dcr`; a herd CSV round trip; bad input returns a message; hosted refuses an oversized body and has no
  path argument.
- The existing suite (`pytest`, 1e-5) still passes.
- Run every tool from Claude Desktop as a custom connector and from Codex before any submission.

## Order, and where his yes is needed

1. Build the server, skill, tests and docs locally (no yes needed; nothing leaves the PC).
2. Publish `bestpred` and `bestpred-mcp` to PyPI (his yes; his PyPI account).
3. Host it (his yes: Google Cloud billing and budget, Cloudflare DNS).
4. Submit to Claude's directory and OpenAI's (his yes; his developer identity).
5. The talk: a slide beside the Ration Lab with the install line, and a replayed real run on a herd's test days.
