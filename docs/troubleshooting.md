# Troubleshooting

**"Python 3.12 or newer was not found"** (setup)
Install it with `winget install Python.Python.3.12` or from [python.org](https://www.python.org/downloads/), open a new terminal, and run setup again.

**"SEC_USER_AGENT is not set"** (setup or update-data)
Run `setx SEC_USER_AGENT "ThirteenF you@example.com"` with your own email, then open a new terminal. On macOS and Linux, export it in your shell profile. The SEC refuses downloads without it.

**"SEC paused requests from this computer; waiting 10 minutes, then carrying on"** (update-data)
The SEC blocks a computer for about 10 minutes when it sees too many requests or an undeclared tool (an HTTP 429, or a 403 page saying "Request Rate Threshold" or "Undeclared Automated Tool"). The SEC is the only source of the 13F data, so the update waits it out by itself, as long as the SEC says or else 10 minutes, then carries on. Nothing to do; Ctrl+C stops it, and finished downloads are kept.

**"The SEC paused requests from this computer 3 times in this run"** (update-data)
The update waits out two blocks per run, then stops. Run `update-data` again later; it carries on from the finished downloads. If it keeps happening, check that `SEC_USER_AGENT` holds a real name and email.

**"The SEC failed to answer 4 times"** (update-data)
The connection failed or the SEC answered with a server error four times in a row, about 1, 2 and 4 seconds apart (lines starting `SEC:` show each try). Check your connection and run `update-data` again; it carries on from the finished downloads, and a stopped download restarts cleanly.

**Downloads fail with another 403 or a 404**
The SEC refused that request outright, so it is not tried again. Check `SEC_USER_AGENT`; a 404 means the SEC moved a file, and the app needs a fix.

**"Sources: No reliable source for ..."** (update-data or `python -m thirteenf.tickers`)
In the last 24 hours, every source for that data answered under half of at least 5 requests. The app keeps working on the data it already has. Check your connection, `SEC_USER_AGENT` and your OpenFIGI key, then run the update again later; the line goes away once the sources answer again. `data/source-health.json` has each source's counts and its last error, and [sources.md](sources.md) lists the sources.

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

**"OpenFIGI did not answer: HTTP 429. Its CUSIPs go to the next source"** (the ticker step)
OpenFIGI refused or failed a request, so its CUSIPs got their tickers from the SEC's fails-to-deliver data, or else from an exact match of the issuer's name, and the run carried on at full speed. Nothing to do: those tickers are provisional, and the next run asks OpenFIGI about them again. The line at the end of the step says how many came from each.

**"OpenFIGI does not know N CUSIPs. For now M take their ticker from the SEC's fails-to-deliver data"** (the ticker step)
OpenFIGI looked these CUSIPs up and found nothing, so those the SEC's fails-to-deliver data has a symbol for take it, marked as from that source. Nothing to do: the next run asks OpenFIGI about them again, and its answer replaces the symbol once it knows them.

**A stock's page says "Ticker · From the SEC's fails-to-deliver data" or "Matched by issuer name, unverified"**
OpenFIGI could not answer for that stock on the last ticker run, or does not know it, so its ticker came from a fallback ([sources.md](sources.md)). A stock OpenFIGI does not know only ever takes the fails-to-deliver symbol. A ticker matched by issuer name is unverified: check it against the company's filings, and note that it never brings a company's cash flow to the Accumulate list. Run `python -m thirteenf.tickers` again; OpenFIGI's answer replaces it.

**"cnsfails….zip: not loaded (...)"** (the ticker step)
A fails-to-deliver file from the SEC did not read as documented (its header, its line count or its trailer's record count), so it is left out; the other files still answer, and the file stays in `data/raw/ftd/` as downloaded. If every file says so, the SEC has changed the format and the app needs a fix.

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
