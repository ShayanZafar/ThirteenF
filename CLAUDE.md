# ThirteenF

A personal app, run locally: are more funds holding each US-listed stock in the SEC's Form 13F data, or fewer, filing period by filing period, across the market or for one stock?

Instructions for Claude are this file (≤600 words, checked by `scripts/verify.sh`) and `.claude/rules/` (each loads only when its files are touched); the rest is documentation, read when needed.

## Where things are

- `design/README.md`: start here. The screens (`design/screens/`), what each needs, the build order.
- `design-system/`: tokens, `tf-` classes, fonts, and the style guide (`README.md`).
- `docs/build-plan.md`: the phases, in order, each with its check.
- `docs/13f-data.md`: the SEC data sets, how each number is computed, the data checks.
- `docs/sources.md`: outside sources, fallbacks, source health.
- `docs/README.md`: the index of the other docs.
- `docs/decisions.md`: decisions made; pending ones and debt are GitHub issues (`backlog` skill).
- `docs/core-flows.md`: the core flows and their tests.
- `config/watchlist.csv`: the example starting watchlist.
- `.claude/rules/sec-and-sources.md`: SEC access, tickers, source health.
- `.claude/rules/ui.md`: pages, design system, copy.
- `.claude/rules/data.md`: raw SEC files, the model, data checks.
- `.claude/skills/`: `/verify`, `/refactor`, `backlog`.

## Stack

Python 3.12 in `.venv`; DuckDB in `data/thirteenf.duckdb`; FastAPI with Jinja2 templates reusing the markup and `tf-` classes of `design/screens`; server-made inline SVG charts; no front-end framework; httpx, pytest, ruff, mypy.

## Commands (add them as you build)

- `python -m thirteenf.ingest`: download and load the 13F data sets and XBRL frames, build the model, then tickers and prices when their keys are set. `--no-download` loads the zips in `data/raw/`; `--download-only` only downloads.
- `python -m thirteenf.model`: rebuild the model from the raw tables (about a minute).
- `python -m thirteenf.prices`: daily prices (Stooq, then Tiingo, free keys) for the market, the watchlist and the Accumulate candidates.
- `python -m thirteenf.tickers`: map new CUSIPs to tickers (OpenFIGI, then fallbacks: `docs/sources.md`); `--retry-missing` retries the unknown ones.
- `python -m thirteenf.web`: serve at http://127.0.0.1:8000; `--open` opens the browser, `--reload` restarts on code changes.
- `pytest`: the tests, with the reference-number checks.
- `scripts/verify.sh` (`scripts\verify.cmd`): the one check, run by CI on every push to `main` and pull request: ruff format and lint, mypy, licences (free, open-source only), the tests, the core flows and Claude files checks.
- `scripts/`: `setup`, `update-data`, `start`, `test`, for people running the app (`README.md`).

## Rules

- Nothing is specific to one company. Shopify and the other names in the designs are examples and test fixtures only; every page works for any CUSIP.
- Build in the order of `docs/build-plan.md`, finishing a phase's check before the next.
- Every SEC request goes through `SecClient`: under 10 a second, with `SEC_USER_AGENT` as the User-Agent (for example `ThirteenF you@example.com`; if unset, stop and ask the user for it). Callers add no retries or waits, pass `has_fallback=True` when another source can answer, and every answer is recorded in source health (details: `.claude/rules/sec-and-sources.md`).
- `data/` and `.venv/` stay out of git.

## Definition of done

- `scripts/verify.sh` passes; show its last lines in your summary.
- Every core flow in `docs/core-flows.md` names a unit, integration and UI test (defined there). Changing a flow updates its tests at all three levels; a new feature adds its flow and three tests before it's done. `Gaps allowed` only goes down.
- A change at a seam (a route, the build, tickers, a network call) comes with a test that runs without the SEC download (`tests/minidata.py` is a small made-up data set).
- Never loosen a test tolerance, a threshold in `docs/13f-data.md`, the complexity ceiling in `pyproject.toml` or a check without asking the user first; record the reason with a date.
