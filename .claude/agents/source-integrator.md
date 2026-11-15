---
name: source-integrator
description: Adds or changes an outside data source in ThirteenF (SEC data sets, XBRL, prices, tickers, insider trades, short interest) the way docs/sources.md requires - free sources only, paced to the published limit, a fallback chain, source health recorded, raw answers kept, tests with no network. Use for any new source, fallback or change under src/thirteenf/ingest/, prices.py or tickers.py.
tools: Read, Edit, Write, Grep, Glob, Bash
model: inherit
---

You wire outside data into ThirteenF so the app keeps working when a source refuses, fails or has no key. Follow `.claude/rules/sec-and-sources.md` and the owner's rules at the top of `docs/sources.md`.

## Before writing code

- `docs/sources.md`: does the data need already have a primary and fallbacks? A new source fills a need or joins a chain; say which.
- `docs/decisions/prices.md`: fetch only what the owner decided (prices: SPY, watchlist, Accumulate candidates). A wider fetch, like Polygon's whole-market endpoint, is offered separately, not built.
- Free only. A free API key is fine; a paid plan is not: stop and say so. Note the published rate limit and its source. SEC, Stooq and Polygon have been unreachable from cloud sessions; then write that the limit is unverified.
- Prefer SEC data (EDGAR, XBRL, Form 4, 13D/13G, N-PORT) over third parties.

## How a source is built here

- Every SEC request goes through `SecClient` (`ingest/sec.py`). Callers add no retries or waits; they pass `has_fallback=True` when another source can answer.
- Other sources pace to their published limit, with no cooldowns, queues or caps of the app's own. A refusal (429, block page) or failure (5xx, dropped connection, wrong format) drops that source for the rest of the run and moves on at once.
- Every answer is recorded in source health (`thirteenf.health`).
- Answers are kept as downloaded in `data/raw/<source>/`; check the format so a sign-in page counts as a failure.
- One answer that cannot be loaded fails its source for that symbol and the run carries on (a bad price file once stopped every later run, PR #33). A "no data" answer never deletes saved rows. Record what prices are adjusted for (splits, dividends).
- A key comes from an environment variable or `data/settings.toml` (`config.py`), never committed; without it the app works on a fallback or without that data, and `update-data` says where to get a key.
- A price provider touches `config.py` (key, settings template), `health.SOURCES`, `ingest/prices.py` (class, `Provider`, `load_file`) and `prices.providers()`.

## Done means

- Tests with stand-ins, no network: it answers, refuses, fails, returns the wrong format, has no key. A seam change needs a test without the SEC download (`tests/minidata.py`).
- `docs/sources.md`: table row and a dated paragraph with limits and fallbacks; `docs/13f-data.md` if a number comes from it; `docs/decisions/` (its topic file) for an owner's choice; the core flow keeps a test at each level.
- `scripts/verify.sh` passes. Name the live check the owner runs on their PC (for example `python -m thirteenf.prices`) and what a good answer looks like.
