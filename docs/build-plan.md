# Build plan

Seven phases. Each ends with a check; do not start the next phase until it passes. Phases 1 to 5 make the first useful version, from real SEC data: every stock ranked by the change in funds holding it, a page for any single stock, and a watchlist. Nothing is built for one company; the stocks named below are only test cases.

## Phase 0: Project setup

- Layout: `src/thirteenf/` (package), `src/thirteenf/ingest/`, `src/thirteenf/model/`, `src/thirteenf/web/` (FastAPI app, `templates/`), `tests/`, `data/` (git-ignored).
- `.venv` with Python 3.12; dependencies: `duckdb`, `httpx`, `fastapi`, `uvicorn`, `jinja2`, `pytest`.
- `.gitignore`: `data/`, `.venv/`, `__pycache__/`.
- Serve `design-system/` as static files at `/ds/` so templates link `/ds/tokens.css` and `/ds/components/bundle.css`.
- A base template with the app's top bar, copied from `design/screens/overview.html`, and a light/dark switch that sets `data-theme` on `<html>`.

**Check:** `python -m thirteenf.web` serves a page whose "ThirteenF" wordmark renders in Newsreader and whose background is the `paper` color, in both themes.

## Phase 1: Download and load the SEC data

- Read `docs/13f-data.md` first.
- Find the zip links on the SEC's Form 13F data sets page instead of building URLs by hand: the folder in the link has changed between releases.
- Download every filing window from `01jun2024-31aug2024` up to the latest one. Together they hold the filings for the periods Q2 2024 to Q2 2026, plus late filings and amendments.
- Keep each zip in `data/raw/` untouched. Load `SUBMISSION`, `COVERPAGE`, `SUMMARYPAGE` and `INFOTABLE` into DuckDB tables prefixed `raw_`, each row tagged with the zip it came from. Loading the same zip twice must not duplicate rows.

**Check:** a `load_log` table lists each zip with its row count per table; every period has holdings for thousands of distinct CUSIPs; and each of the eight test stocks in `docs/reference/13finfo-holdings.csv` has `raw_infotable` rows for all nine periods.

## Phase 2: Holdings model and data checks

Build these as DuckDB views or tables, exactly as defined in `docs/13f-data.md`:

- `filings`: one current filing per manager (CIK) per period, with amendments applied.
- `positions`: manager × CUSIP × period, with shares (options and bond principal left out) and value in dollars.
- `holders`: per CUSIP and period, funds holding, shares held and value.
- `filers_total`: per period, how many managers filed holdings.
- `changes`: per CUSIP and period, how many managers opened, added, trimmed, sold out or held.
- `price_check`: the implied-price check, with each flagged row and the manager who filed it.

**Check (pytest):**
- Funds holding for each stock in `docs/reference/13finfo-holdings.csv` is within 3% of the `filings` column for every period. The reference counts filings and the app counts managers, so exact matches are not expected.
- The Q2 2026 share totals for AAPL, MSFT, NVDA, AMZN, GOOGL, META and TSLA, which jump 46% to 117% in the reference, either come out in line with their value once flagged rows are removed, or are flagged by `price_check`. The test prints the managers whose rows were flagged.

## Phase 3: The "Look up a stock" page

Design: `design/screens/lookup.html`.

- Route `/stock/{cusip}` for any stock in the data; the search box accepts a CUSIP or a company name for now (tickers arrive in Phase 6). The design shows Shopify only as the example.
- In order: the one-sentence answer, key figures, the funds-holding bar chart with the change row, the per-period table, the method notes.
- Write the answer sentence from rules: more or fewer funds than last period, the streak, and the change against the typical stock. Wording follows `design-system/README.md`.
- Compare with the tide in two ways, both defined in `docs/13f-data.md`: the market median (what the typical stock did) and the change against the tide (against all 13F filers). The design says "watchlist median" because it was drawn from eight stocks; use the market median. Show "share of all 13F filers holding it" in the table.
- Hide share totals that fail the price check and say why.

**Check:** all eight reference stocks match the reference within 3%, and at least five other stocks of different sizes render correctly, including one held by fewer than 50 funds. Both themes, no hard-coded colors.

## Phase 4: Biggest changes across all stocks

Design: the two ranked tables at the bottom of `design/screens/most-bought-and-sold.html` (ignore the older layout at the top of that file).

- Route `/changes`, with the period and the minimum below as query parameters.
- Rank every stock by its change against the tide from one period to the next (defined in `docs/13f-data.md`), not the raw count. Let the user sort by the change in count instead.
- Two lists for the selected period: most funds added and most funds lost, 25 each by default. Columns: stock, funds holding, change (count and %), change against the tide, shares held change (only when it passes the price check), streak.
- A minimum number of funds holding (default 100) keeps thinly held stocks from topping the list on small counts; let the user change it.
- Every row links to its lookup page. Leave out the est. value and "priced in?" columns until price data exists.

**Check:** the lists for Q2 2026 render; the same ranking comes out of a plain SQL query on the model tables; no stock below the minimum appears.

## Phase 5: The Overview page

Design: `design/screens/overview.html`.

- Start from `config/watchlist.csv`, which is only an example list; any stock can be added or removed on the page.
- For each stock: funds holding, change against last period, change against the market median, a nine-period sparkline, the streak, and the two-year change. Each row links to its lookup page.
- The data-check table is computed live from `price_check`.

**Check:** the eight example stocks match the reference within 3%, a stock added from search appears with its numbers, and the page flags the Q2 2026 share totals that fail the check.

## Phase 6: Tickers and search

- Map every CUSIP in the data to a ticker with the OpenFIGI API (free key, `idType` `ID_CUSIP`); also use the `FIGI` column in `INFOTABLE` where filers supplied it. Cache the results in DuckDB and refresh only new CUSIPs.
- The search box accepts a ticker, a name or a CUSIP and suggests matches as you type.

**Check:** for any stock, its ticker, its name and its CUSIP all open its page (test with at least five).

## Phase 7 and later

Build only after Phases 1 to 5 work with real data. These designs use fictional sample data:

- Who moved: on the lookup page, the managers who opened, added, trimmed or sold out, and how big the position is in each manager's portfolio. Design: the holder table and conviction meters in `design/screens/company.html`.
- Manager pages: `design/screens/manager.html`.
- Estimated value and "priced in?": these need company financials and daily prices, which 13F does not provide. Leave them out of the first version.
