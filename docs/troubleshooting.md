# Troubleshooting

**"Python 3.12 or newer was not found"** (setup)
Install it with `winget install Python.Python.3.12` or from [python.org](https://www.python.org/downloads/), open a new terminal, and run setup again.

**"SEC_USER_AGENT is not set"** (setup or update-data)
Run `setx SEC_USER_AGENT "ThirteenF you@example.com"` with your own email, then open a new terminal. On macOS and Linux, export it in your shell profile. The SEC refuses downloads without it.

**Downloads fail with 403 or 429**
The SEC is refusing the requests: check that `SEC_USER_AGENT` holds a real name and email, wait a few minutes, and run `update-data` again. Finished downloads are kept; a stopped one restarts cleanly.

**"Running scripts is disabled on this system"**
That message comes from PowerShell `.ps1` scripts. The Windows scripts here are `.cmd` batch files, which are not affected: run `scripts\start.cmd` from PowerShell or Command Prompt, or double-click it.

**The page says "The data is being updated"**
Another ThirteenF command (`update-data`, `python -m thirteenf.model` or `python -m thirteenf.tickers`) is writing to the database. Reload when it finishes, usually within a few minutes.

**The page says the data has not been loaded**
Run `scripts\update-data.cmd`.

**"Address already in use" or nothing at port 8000**
Something else is using port 8000, perhaps another copy of the app. Close it, or run `scripts\start.cmd --port 8001` and open <http://127.0.0.1:8001>.

**Stocks have no ticker**
Tickers need the OpenFIGI step: put your key in `data/settings.toml` and run `python -m thirteenf.tickers` (or `update-data`). About 1% of stocks held by 100 or more funds still have none, mostly companies acquired or delisted since; their pages work by name and CUSIP. `python -m thirteenf.tickers --retry-missing` asks OpenFIGI again about the ones it did not know.

**The ticker step is very slow**
Without an OpenFIGI key, OpenFIGI allows about 250 lookups a minute. Add a key (see [getting-started.md](getting-started.md)); the cache keeps what was already found.

**A page looks unstyled or out of date**
Reload with Ctrl+F5. The app already versions its stylesheets, so this is rare.

**Numbers differ from 13f.info**
Expected. ThirteenF counts managers, 13f.info counts filings, and the SEC data sets do not hold every filing 13f.info does; changes from quarter to quarter agree within about 2 points. [13f-data.md](13f-data.md) has the measured differences.

**A manager's page says its report is incomplete**
The SEC's data set holds only part of that report's holdings (Norges Bank's Q1 2026 report lists 1 of 1,507). The app shows what is there and leaves the manager out of changes and flows for that quarter.

**Start over**
Delete `data/thirteenf.duckdb` and run `update-data --no-download` to rebuild everything from the zips in `data/raw/`. Delete `data/raw/` as well to download again.
