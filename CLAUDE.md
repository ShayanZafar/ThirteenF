# ThirteenF

A personal app, run locally, that answers one question for every US-listed stock in the 13F data: are more funds holding it, or fewer, filing period by filing period? It ranks the whole market by that change, so you can see where funds are moving in and out, and lets you look up any single stock. It downloads the SEC's Form 13F data (the quarterly holdings of every manager with $100M or more in US-listed securities), stores it in a local database, and shows the answer in the browser using the ThirteenF design system.

## Where things are

- `design/README.md`: start here. The screens, what each needs, and the order to build them.
- `design-system/`: the design system. `tokens.css` (colors, type, spacing as CSS variables), `components/bundle.css` (the `tf-` pattern classes), fonts, and `README.md` with the voice, number formats and color rules. Read `design-system/README.md` before writing any UI.
- `design/screens/*.html`: each screen as a static page, linked to `design-system/`. Open in a browser; add `#dark` to the URL for the dark theme. `design/screens/png/` has screenshots of both themes.
- `docs/build-plan.md`: the phases, in order, each with a check that proves it works.
- `docs/13f-data.md`: the SEC data sets, how every number is computed, and the data checks.
- `docs/reference/13finfo-holdings.csv`: published numbers for 8 stocks, used as test fixtures.
- `config/watchlist.csv`: an example starting watchlist (ticker, CUSIP, name); the user can change it in the app.

## Stack

- Python 3.12 in a virtual environment at `.venv`.
- DuckDB for storage and queries, one file at `data/thirteenf.duckdb`.
- FastAPI with Jinja2 templates: server-rendered HTML that reuses the markup and `tf-` classes from `design/screens`. Charts are inline SVG generated on the server, as in the designs. No front-end framework.
- httpx for downloads, pytest for tests.

## Rules

- Nothing is specific to one company. Shopify and the other names in the designs are examples and test fixtures only; every page must work for any CUSIP in the data.
- Build in the order of `docs/build-plan.md`. Finish a phase's check before starting the next phase.
- UI comes from the design system: use its CSS variables and `tf-` classes, never hard-coded colors. `flow-in` and `flow-out` mean only more or fewer funds (money in or out). Signed numbers take the color of their sign through the `|signed` template filter: + in `flow-in` green, − in `flow-out` red (the user asked for this). Every number shows its as-of date and source with a freshness stamp.
- Copy follows `design-system/README.md`: plain, dated, sentence case, no buy or sell language.
- Raw SEC files are never edited. Load them as they are and derive everything from them, so every number can be rebuilt from the raw tables.
- Never show a share total that fails the implied-price check in `docs/13f-data.md`; show the check instead.
- SEC access: send the User-Agent from the `SEC_USER_AGENT` environment variable (for example `ThirteenF you@example.com`). If it is not set, stop and ask the user for it. Stay under 10 requests per second.
- Keep `data/` and `.venv/` out of git.

## Commands (add them as you build)

- `python -m thirteenf.ingest` downloads the Form 13F data sets, loads them and builds the model. `--no-download` loads only the zips already in `data/raw/`.
- `python -m thirteenf.model` rebuilds the model tables from the raw tables (about a minute).
- `python -m thirteenf.tickers` maps new CUSIPs to tickers with OpenFIGI and caches them in DuckDB. It reads a free OpenFIGI key from `openfigi_api_key` in `data/settings.toml` (git-ignored; an `OPENFIGI_API_KEY` environment variable overrides it); without a key the first run takes about 2.5 hours. `python -m thirteenf.ingest` runs it too when a key is set.
- `python -m thirteenf.web` serves the app at http://127.0.0.1:8000. `--open` also opens it in the browser; `--reload` restarts it when the Python code changes.
- `pytest` runs the tests, including the reference-number checks.
- `scripts/` wraps these for people running the app: `setup`, `update-data`, `start` and `test`, as `.cmd` for Windows and `.sh` for macOS and Linux. `README.md` has the table; `docs/` has the user and developer documentation.
