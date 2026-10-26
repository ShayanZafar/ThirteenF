# Getting started

## What you need

- **Python 3.12 or newer.** On Windows: `winget install Python.Python.3.12`, or the installer from [python.org](https://www.python.org/downloads/).
- **About 4 GB of disk**: about 800 MB of SEC downloads in `data/raw/` and a 3 GB database.
- **An internet connection** for the downloads. The app itself runs offline once the data is loaded.

## 1. Set up

The quick way: double-click `scripts\start.cmd` (Windows) or `scripts/start.command` (macOS), or run `scripts/start.sh` (Linux). When `.venv` is missing, they run setup first, then start the app. To run setup on its own:

Windows:

```bat
scripts\setup.cmd
```

macOS (double-click `scripts/setup.command`, or) and Linux:

```sh
scripts/setup.sh
```

Setup finds Python, creates a virtual environment in `.venv`, installs the app and its dependencies (with the test tools and, for the browser tests, Chromium through Playwright, about 150 MB the first time), and creates `data/settings.toml`. It is safe to run again, for example after pulling new code.

## 2. Tell the SEC who you are

The SEC asks every client that downloads its data to identify itself with a name and a contact email. ThirteenF reads it from the `SEC_USER_AGENT` environment variable and stops if it is missing.

Windows (then open a new terminal):

```bat
setx SEC_USER_AGENT "ThirteenF you@example.com"
```

macOS and Linux (add the line to `~/.zshrc` or `~/.bashrc`):

```sh
export SEC_USER_AGENT="ThirteenF you@example.com"
```

## 3. Add an OpenFIGI key (optional, for tickers)

13F filings name stocks by CUSIP. ThirteenF looks up each CUSIP's ticker with the free OpenFIGI API.

1. Sign up at [openfigi.com/user/signup](https://www.openfigi.com/user/signup) with your email, and enter the code they send.
2. Open your account page and copy your API key.
3. Paste it between the quotes in `data/settings.toml`:

   ```toml
   openfigi_api_key = "your-key"
   ```

With a key, the first ticker run takes a few minutes; without one, OpenFIGI's lower rate limit makes it about 2.5 hours. The file is in `data/`, which git ignores. An `OPENFIGI_API_KEY` environment variable, if set, overrides it.

## 3b. Add a Stooq key (optional, for daily prices)

The Accumulate page says whether each pick's price has already moved since funds bought in. That needs daily prices, which the app fetches from [Stooq](https://stooq.com) with a free key: open any stock's historical data page there, follow its API key link, and paste the key into `data/settings.toml` as `stooq_api_key`. Optionally add a free [Tiingo](https://www.tiingo.com) key as `tiingo_api_key`: it answers for stocks Stooq lacks, and for the rest of a run once Stooq's daily limit is reached (its free plan allows 50 symbols an hour). `STOOQ_API_KEY` and `TIINGO_API_KEY` environment variables override the file. Without either key the app works as before, with no price column.

## 4. Load the data

Windows: `scripts\update-data.cmd` · macOS and Linux: `scripts/update-data.sh`

The first run:

1. Reads the download links from the SEC's [Form 13F data sets](https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets) page and downloads every three-month filing window from June 2024 on (about 800 MB).
2. Loads each zip into DuckDB exactly as filed, checking every table's row count against its file.
3. Builds the model: one current filing per manager, positions, funds holding, changes, net 13F flow, and the data checks.
4. Downloads the companies' cash flow data from the SEC (about 60 files), for the Accumulate page.
5. Maps CUSIPs to tickers, if you added an OpenFIGI key.
6. Fetches daily prices and volume, if you added a Stooq or Tiingo key: for the market (SPY), the stocks on your watchlist and the Accumulate list's candidates, about three years back, into `data/raw/prices/`. A symbol fetched in the last 20 hours is not asked for again, so a run stopped by a source's limit picks up where it left off next time. The Accumulate page needs tickers to match companies to their stocks. Where OpenFIGI cannot answer, the SEC's fails-to-deliver data and the issuer's name stand in until the next run; for a CUSIP OpenFIGI does not know, the fails-to-deliver data alone ([sources.md](sources.md)).

Allow about 15 minutes. Later runs skip zips already downloaded and loaded.

## 5. Start the app

Windows: `scripts\start.cmd` · macOS and Linux: `scripts/start.sh`

The app opens at <http://127.0.0.1:8000>. It only listens on your own computer. Press Ctrl+C in the terminal to stop it. To use another port: `scripts\start.cmd --port 8001`.

## Keeping the data current

The SEC publishes the 13F data sets in three-month windows of filing dates: December to February, March to May, June to August, and September to November. Each window holds the filings made in it, so a quarter's holdings (due 45 days after the quarter ends) arrive in the window after the quarter. Positions for Sep 30, for example, are due by mid-November and arrive in the September to November window, published in December.

Run `update-data` after each window is published. It downloads only the new zip, downloads the companies' cash flow data again (new 10-Ks arrive all year), reloads, rebuilds the model and maps any new CUSIPs. Until the data reaches the next period's filing deadline, the latest period is marked "Still arriving", because late filers keep adding to it.

## Where things live

| Path | What it holds |
| --- | --- |
| `data/raw/` | The SEC's zips, never edited |
| `data/raw/xbrl/` | The SEC's company cash flow data (XBRL frames) and ticker list, as downloaded |
| `data/raw/ftd/` | The SEC's fails-to-deliver files, downloaded only when OpenFIGI could not answer for some CUSIPs or does not know them, and kept as downloaded |
| `data/thirteenf.duckdb` | The database: the raw tables as loaded, and the model built from them |
| `data/settings.toml` | Your settings, such as the OpenFIGI key |
| `data/source-health.json` | How the SEC and OpenFIGI answered over the last 24 hours, rewritten after every request (the requests themselves are in `data/source-health-events.json`); [sources.md](sources.md) explains it |
| `data/watchlist.csv` | Your watchlist, started from `config/watchlist.csv` the first time you open the app |
| `.venv/` | The Python virtual environment |

All of `data/` and `.venv/` stay out of git. To rebuild the database from scratch, delete `data/thirteenf.duckdb` and run `update-data --no-download`: it reloads the zips already in `data/raw/`. The ticker lookups are cached in the database, so they run again too (a few minutes with a key).
