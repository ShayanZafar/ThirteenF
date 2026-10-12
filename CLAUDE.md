# ThirteenF

A personal app, run locally, that answers one question for every US-listed stock in the 13F data: are more funds holding it, or fewer, filing period by filing period? It ranks the whole market by that change, so you can see where funds are moving in and out, and lets you look up any single stock. It downloads the SEC's Form 13F data (the quarterly holdings of every manager with $100M or more in US-listed securities), stores it in a local database, and shows the answer in the browser using the ThirteenF design system.

## Where things are

- `design/README.md`: start here. The screens, what each needs, and the order to build them.
- `design-system/`: the design system. `tokens.css` (colors, type, spacing as CSS variables), `components/bundle.css` (the `tf-` pattern classes), fonts, and `README.md` with the voice, number formats and color rules. Read `design-system/README.md` before writing any UI.
- `design/screens/*.html`: each screen as a static page, linked to `design-system/`. Open in a browser; add `#dark` to the URL for the dark theme. `design/screens/png/` has screenshots of both themes.
- `docs/build-plan.md`: the phases, in order, each with a check that proves it works.
- `docs/13f-data.md`: the SEC data sets, how every number is computed, and the data checks.
- `docs/sources.md`: the register of outside sources: for each data need the primary, the fallbacks in order, what "unreliable" means, where source health is recorded, and the candidates turned down. Update it when a source or fallback changes.
- `docs/decisions.md`: decisions made, one line each (date, decision, why, issue). Pending decisions and debt are GitHub issues labelled `decision` and `debt`; the `backlog` skill files and closes them, and the monthly refactor takes `debt` issues first.
- `docs/core-flows.md`: the core flows (what a person relies on the app for), each with the unit, integration and UI tests that prove it, and the count of gaps still open. `scripts/check_core_flows.py` checks it in `scripts/verify.sh`.
- `docs/reference/13finfo-holdings.csv`: published numbers for 8 stocks, used as test fixtures.
- `config/watchlist.csv`: an example starting watchlist (ticker, CUSIP, name); the user can change it in the app.
- `.github/workflows/`: CI (verify, CodeQL, Claude Code Review, the monthly Claude Refactor and mutation testing); `docs/development.md` has the list. `.claude/skills/`: the `/verify`, `/refactor` and `backlog` skills (`backlog` files, triages and works the `debt` and `decision` issues).

## Stack

- Python 3.12 in a virtual environment at `.venv`.
- DuckDB for storage and queries, one file at `data/thirteenf.duckdb`.
- FastAPI with Jinja2 templates: server-rendered HTML that reuses the markup and `tf-` classes from `design/screens`. Charts are inline SVG generated on the server, as in the designs. No front-end framework.
- httpx for downloads, pytest for tests, ruff for formatting and lint, mypy for types.

## Rules

- Nothing is specific to one company. Shopify and the other names in the designs are examples and test fixtures only; every page must work for any CUSIP in the data.
- Build in the order of `docs/build-plan.md`. Finish a phase's check before starting the next phase.
- UI comes from the design system: use its CSS variables and `tf-` classes, never hard-coded colors. `flow-in` and `flow-out` mean only more or fewer funds (money in or out). Signed numbers take the color of their sign through the `|signed` template filter: + in `flow-in` green, − in `flow-out` red (the user asked for this). Every number shows its as-of date and source with a freshness stamp.
- Copy follows `design-system/README.md`: plain, dated, sentence case, no buy or sell language. One exception, asked for by the user (Oct 10, 2026): the Accumulate page names stocks to accumulate, because recommending them is the app's goal. It still says how each was chosen and that it is not advice.
- Raw SEC files are never edited. Load them as they are and derive everything from them, so every number can be rebuilt from the raw tables.
- Never show a share total that fails the implied-price check in `docs/13f-data.md`; show the check instead.
- SEC access: send the User-Agent from the `SEC_USER_AGENT` environment variable (for example `ThirteenF you@example.com`). If it is not set, stop and ask the user for it. Stay under 10 requests per second (`SecClient` paces every request 0.11 s apart). `SecClient` already waits only where nothing else can answer: for the 13F data sets and the XBRL frames, a failed connection or a 5xx is asked again after about 1, 2 and 4 seconds (four attempts in all), and an SEC block (a 429, or the 403 "Request Rate Threshold" page) is waited out for as long as `Retry-After` says, else 10 minutes, as many times as it comes (decision #13, Oct 12, 2026). The 403 "Undeclared Automated Tool" page means `SEC_USER_AGENT` is wrong, so waiting won't help: it stops at once with a `RuntimeError` saying to set it correctly. A caller with another source for the same data passes `has_fallback=True`: a block or a failure then raises `SecUnavailable` (`SecBlocked` for a block) at once and the caller moves on. Callers never add their own retries or waits. Every answer is recorded in `data/source-health.json` (`thirteenf.health`).
- Keep `data/` and `.venv/` out of git.

## Definition of done

- `scripts/verify.sh` passes. Show its last lines in your summary.
- Every core flow in `docs/core-flows.md` names at least one test at each level: unit (one module, no network), integration (several parts together through real routes, the database or the ingest pipeline, outside services played by stand-ins) and UI (a real browser driving the running app). A change to a core flow updates its tests at all three levels in the same change; a new feature adds its flow and all three tests before it's done. The verify check fails when a flow lacks a level, a named test no longer exists, or the gaps differ from `Gaps allowed`, which only ever goes down. All three levels run on every pull request; tests that need the real SEC download or another live service (the `data` tests) are kept separate and are not named there.
- A change at a seam (a route, the build, tickers, a network call) comes with a test that runs without the SEC download; `tests/minidata.py` builds a small made-up data set for that.
- Never loosen a test tolerance, a threshold in `docs/13f-data.md`, the complexity ceiling in `pyproject.toml` or a check without asking the user first. Record the reason with a date.

## Commands (add them as you build)

- `python -m thirteenf.ingest` downloads the Form 13F data sets and the companies' cash flow data (XBRL frames), loads them and builds the model. `--no-download` loads only the zips already in `data/raw/`; `--download-only` downloads without loading.
- `python -m thirteenf.model` rebuilds the model tables from the raw tables (about a minute).
- `python -m thirteenf.tickers` maps new CUSIPs to tickers with OpenFIGI and caches them in DuckDB; `--retry-missing` asks again about the ones OpenFIGI did not know. A batch OpenFIGI refuses or fails goes at once to the SEC's fails-to-deliver data (zips kept in `data/raw/ftd/`), then to an exact issuer-name match (unverified); those tickers are provisional, and the next run asks OpenFIGI again (`docs/sources.md`). It reads a free OpenFIGI key from `openfigi_api_key` in `data/settings.toml` (git-ignored; an `OPENFIGI_API_KEY` environment variable overrides it); without a key the first run takes about 2.5 hours. `python -m thirteenf.ingest` runs it too when a key is set.
- `python -m thirteenf.web` serves the app at http://127.0.0.1:8000. `--open` also opens it in the browser; `--reload` restarts it when the Python code changes.
- `pytest` runs the tests, including the reference-number checks.
- `scripts/verify.sh` (or `scripts\verify.cmd`) is the one check: ruff format, ruff lint, mypy, the dependency licence check (pip-licenses: free, open-source licences only), the tests, then the core flows check (`scripts/check_core_flows.py`). CI runs the same script on every push to `main` and every pull request.
- `scripts/` wraps these for people running the app: `setup`, `update-data`, `start` and `test`, as `.cmd` for Windows and `.sh` for macOS and Linux. `README.md` has the table; `docs/` has the user and developer documentation.
