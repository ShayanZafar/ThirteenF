# Architecture

ThirteenF is three steps run in order, and a web app that reads the result.

```
SEC Form 13F data sets page
        |  ingest/sec.py: read the zip links, download (User-Agent, under 10 requests a second)
        v
data/raw/*.zip                      kept exactly as downloaded
        |  ingest/load.py: load the TSVs as text, tag each row with its zip
        v
raw_submission, raw_coverpage,      DuckDB: data/thirteenf.duckdb
raw_summarypage, raw_infotable,
load_log
        |  model/build.py: SQL, every table derived from the raw ones
        v
filings, positions, holders,        the model
changes, stock_periods, ...
        |  ingest/openfigi.py: CUSIP -> ticker, cached
        v
openfigi, stocks
        |
        v
web/app.py (FastAPI)  ->  Jinja2 templates + inline SVG  ->  your browser
```

`python -m thirteenf.ingest` runs the download, the load, the model build and the ticker mapping. `python -m thirteenf.model` and `python -m thirteenf.tickers` run their step alone.

## Modules

| Module | Role |
| --- | --- |
| `config.py` | Paths, the SEC user agent, the OpenFIGI key from `data/settings.toml` |
| `db.py` | DuckDB connections that wait briefly for another process's write lock |
| `ingest/sec.py` | Finds the data set links on the SEC page and downloads new zips |
| `ingest/load.py` | Loads each zip into the `raw_` tables; reloading a zip replaces its rows |
| `ingest/openfigi.py` | Maps CUSIPs to tickers and security types, in three passes, cached |
| `model/periods.py` | Quarter ends and their 13F deadlines (45 days, next business day) |
| `model/build.py` | Builds every model table in SQL, in order (see below) |
| `tickers.py` | The `python -m thirteenf.tickers` command |
| `web/app.py` | Routes: overview, stock, changes, managers, search, watchlist, suggestions |
| `web/data.py` | Read-only queries for the pages; one connection per request |
| `web/story.py` | The sentences and key figures, written from rules |
| `web/charts.py` | The bar charts, net flow chart and sparklines as SVG |
| `web/format.py` | Number, date and name formats from the design system |
| `web/watchlist.py` | Your watchlist in `data/watchlist.csv` |
| `web/templates/` | Jinja2 templates built from `design/screens` and the `tf-` classes |
| `web/static/` | `app.css` (layout, built only on design tokens) and `suggest.js` (search suggestions) |

## The model tables

Built by `model/build.py` in this order. Definitions are in [13f-data.md](13f-data.md).

| Table | One row per | Holds |
| --- | --- | --- |
| `submissions` | filing | Parsed dates, CIK, role (original, restatement, new holdings, notice) |
| `periods` | quarter end | Label, deadline, whether late filings are still arriving |
| `filing_parts` | filing in use | The accessions that make up each manager's current report |
| `filings` | manager and quarter | The current report, amendments applied, and whether the data set holds it in full |
| `managers` | manager | Latest name |
| `positions` | manager, CUSIP and quarter | Shares and value, with the implied-price check |
| `price_check` | flagged position | Reports left out of share totals, and value-in-thousands reports |
| `cusip_holders` | CUSIP and quarter | Funds holding each CUSIP, for finding CUSIP changes |
| `cusip_changes` | change of CUSIP | Old and new CUSIP, exchange ratio, how many funds moved |
| `stock_keys` | CUSIP | The stock it belongs to (its current CUSIP) and the share ratio |
| `securities` | CUSIP | Names and class as filed |
| `stocks` | stock | Display name, ticker, security type, kind (stock, ETF, other) |
| `holders` | stock and quarter | Funds holding, shares and value after the checks |
| `filers_total` | quarter | Managers that filed holdings: the tide |
| `manager_totals` | manager and quarter | Reported 13F portfolio value and positions |
| `changes` | stock and quarter | Managers that opened, added, held, trimmed, sold out or have not filed; shares bought and sold |
| `stock_periods` | stock and quarter | Every comparison the pages show: against last quarter, the tide and the typical stock or ETF, the share check, the streak, the net 13F flow |
| `openfigi` | CUSIP | OpenFIGI's answer, as returned |

Nothing in the model is edited by hand: drop it and `python -m thirteenf.model` rebuilds it from the raw tables.

## The web app

Server-rendered HTML, no front-end framework. Each request opens a read-only DuckDB connection and closes it, so `update-data` can write between requests; while a long write runs, pages show "The data is being updated". Templates reuse the markup of `design/screens` and the `tf-` classes from `design-system/components/bundle.css`; colors come only from `design-system/tokens.css`. The design system is served at `/ds/`, and stylesheet links carry each file's modification time so browsers fetch them again after a change.
