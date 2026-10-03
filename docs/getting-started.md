# Getting started

## What you need

- **Python 3.12 or newer.** On Windows: `winget install Python.Python.3.12`, or the installer from [python.org](https://www.python.org/downloads/).
- **About 4 GB of disk**: about 800 MB of SEC downloads in `data/raw/` and a 3 GB database.
- **An internet connection** for the downloads. The app itself runs offline once the data is loaded.

## 1. Set up

Windows:

```bat
scripts\setup.cmd
```

macOS and Linux:

```sh
scripts/setup.sh
```

Setup finds Python, creates a virtual environment in `.venv`, installs the app and its dependencies, and creates `data/settings.toml`. It is safe to run again, for example after pulling new code.

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

## 4. Load the data

Windows: `scripts\update-data.cmd` · macOS and Linux: `scripts/update-data.sh`

The first run:

1. Reads the download links from the SEC's [Form 13F data sets](https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets) page and downloads every three-month filing window from June 2024 on (about 800 MB).
2. Loads each zip into DuckDB exactly as filed, checking every table's row count against its file.
3. Builds the model: one current filing per manager, positions, funds holding, changes, net 13F flow, and the data checks.
4. Maps CUSIPs to tickers, if you added an OpenFIGI key.

Allow about 15 minutes. Later runs skip zips already downloaded and loaded.

## 5. Start the app

Windows: `scripts\start.cmd` · macOS and Linux: `scripts/start.sh`

The app opens at <http://127.0.0.1:8000>. It only listens on your own computer. Press Ctrl+C in the terminal to stop it. To use another port: `scripts\start.cmd --port 8001`.

## Keeping the data current

The SEC publishes the 13F data sets in three-month windows of filing dates: December to February, March to May, June to August, and September to November. Each window holds the filings made in it, so a quarter's holdings (due 45 days after the quarter ends) arrive in the window after the quarter. Positions for Sep 30, for example, are due by mid-November and arrive in the September to November window, published in December.

Run `update-data` after each window is published. It downloads only the new zip, reloads, rebuilds the model and maps any new CUSIPs. Until the data reaches the next period's filing deadline, the latest period is marked "Still arriving", because late filers keep adding to it.

## Where things live

| Path | What it holds |
| --- | --- |
| `data/raw/` | The SEC's zips, never edited |
| `data/thirteenf.duckdb` | The database: the raw tables as loaded, and the model built from them |
| `data/settings.toml` | Your settings, such as the OpenFIGI key |
| `data/watchlist.csv` | Your watchlist, started from `config/watchlist.csv` the first time you open the app |
| `.venv/` | The Python virtual environment |

All of `data/` and `.venv/` stay out of git. To rebuild the database from scratch, delete `data/thirteenf.duckdb` and run `update-data --no-download`: it reloads the zips already in `data/raw/`. The ticker lookups are cached in the database, so they run again too (a few minutes with a key).
