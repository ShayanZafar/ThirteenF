# ThirteenF

Are more funds holding a stock, or fewer? ThirteenF answers that for every US-listed stock and ETF in the SEC's Form 13F data, filing period by filing period. It shows where institutional money moved and who moved it: which managers opened, added, trimmed or sold out, and how much of each manager's portfolio a position takes up.

It is a personal app that runs on your computer. It downloads the SEC's Form 13F data sets (the quarterly holdings of every manager with $100M or more in US-listed securities), keeps them in a local DuckDB database, and serves the pages in your browser.

## What you can see

- **Overview**: your watchlist, each stock's funds holding against last quarter and against the typical stock, a two-year sparkline, and a live data check.
- **Look up a stock**: one answer first, then key figures, funds holding and net 13F flow by quarter, who added and who left (with each position's weight in the manager's book), where the stock sits in each book, and every filing period.
- **Biggest changes**: every stock held by 100 or more funds, ranked by its change in funds holding against the tide, with tabs for all, stocks and ETFs.
- **Accumulate**: stocks funds keep moving into, against the tide, whose free cash flow is high for their market value, from the companies' 10-K filings. Rebuilt every time you update the data.
- **Managers**: any 13F filer's holdings for a quarter, with the change from the quarter before and a CSV download.

Search takes a ticker, a company name, a CUSIP or a manager, and suggests matches as you type.

## Quick start

You need Python 3.12 or newer and about 4 GB of disk.

1. **Start the app**: double-click `scripts\start.cmd` (Windows) or `scripts/start.command` (macOS); on Linux, run `scripts/start.sh`. The first time, it sets the app up (a minute or two), then opens <http://127.0.0.1:8000>. Until the data is loaded, the pages say so.
2. **Identify yourself to the SEC**, once. The SEC asks every client for a name and contact email:
   - Windows: `setx SEC_USER_AGENT "ThirteenF you@example.com"`, then open a new terminal.
   - macOS and Linux: add `export SEC_USER_AGENT="ThirteenF you@example.com"` to `~/.zshrc` or `~/.bashrc`.
3. **Load the data** (about 15 minutes the first time): double-click `scripts\update-data.cmd` or `scripts/update-data.command`, or run `scripts/update-data.sh`. Optional, for tickers: get a free key at [openfigi.com](https://www.openfigi.com/user/signup) and paste it into `data/settings.toml` first (setup creates the file); without a key the first ticker run takes about 2.5 hours instead of a few minutes.

Press Ctrl+C in the app's window to stop it. Every script also runs from a terminal and passes options through: `scripts\start.cmd --port 8001`, `scripts/update-data.sh --no-download`.

## Scripts and commands

| Script (Windows / macOS, Linux) | Command it runs | What it does |
| --- | --- | --- |
| `scripts\setup.cmd` / `scripts/setup.sh` (`setup.command` on macOS) | | Creates `.venv`, installs the app, the test tools and Chromium for the browser tests, creates `data/settings.toml` |
| `scripts\update-data.cmd` / `scripts/update-data.sh` (`update-data.command` on macOS) | `python -m thirteenf.ingest` | Downloads new SEC data sets and company cash flow data, loads them, rebuilds the model, maps new tickers |
| `scripts\start.cmd` / `scripts/start.sh` (`start.command` on macOS) | `python -m thirteenf.web --open` | Serves the app at <http://127.0.0.1:8000> and opens it |
| `scripts\test.cmd` / `scripts/test.sh` | `python -m pytest` | Runs the tests |
| `scripts\verify.cmd` / `scripts/verify.sh` | | Checks formatting, lint and types, then runs the tests; CI runs the same |
| | `python -m thirteenf.model` | Rebuilds the model tables from the loaded data (a few minutes) |
| | `python -m thirteenf.tickers` | Maps new CUSIPs to tickers with OpenFIGI, or, where it cannot answer, the SEC's fails-to-deliver data and the issuer's name until the next run (for a CUSIP OpenFIGI does not know, the fails-to-deliver data alone) |

`start` and `update-data` run `setup` for you when `.venv` is missing. The `.command` files run the matching `.sh` from Finder on macOS, and `scripts\keep-window.cmd` keeps a double-clicked window open to read the result. Scripts pass options through: `scripts\start.cmd --port 8001`, `scripts\update-data.cmd --no-download`, `scripts\test.cmd -k tickers`.

New 13F data arrives in three-month batches (December to February, March to May, June to August, September to November). Run `update-data` after each to pick up the new quarter.

## Documentation

- [docs/getting-started.md](docs/getting-started.md): setup, the first data load, keeping the data current
- [docs/using-the-app.md](docs/using-the-app.md): each page, and how to read the numbers
- [docs/13f-data.md](docs/13f-data.md): the SEC data sets, how every number is computed, and the data checks
- [docs/sources.md](docs/sources.md): every outside source, the fallbacks when one refuses or fails, and how their health is recorded
- [docs/architecture.md](docs/architecture.md): how the pieces fit together, module by module and table by table
- [docs/development.md](docs/development.md): tests, conventions, CI, and changing the app
- [docs/troubleshooting.md](docs/troubleshooting.md): what to do when something goes wrong
- [docs/build-plan.md](docs/build-plan.md): the phases the app was built in, each with its check
- [design/README.md](design/README.md) and [design-system/README.md](design-system/README.md): the screens and the design system

## Good to know

- 13F filings show long positions in US-listed securities only, from managers with $100M or more, as of each quarter end. They arrive up to 45 days later, so every number on a page carries its date.
- Every number is derived from the SEC's raw files, which are kept untouched in `data/raw/`, so all of it can be rebuilt.
- Funds holding counts managers. 13f.info counts filings, so its numbers run a few percent higher; see the reference notes in [docs/13f-data.md](docs/13f-data.md).
- `data/` (the downloads, the database, your watchlist and your settings) and `.venv/` stay out of git.
