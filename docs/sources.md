# Outside sources

Added Oct 11, 2026. Every outside source the app reads, what stands in when one refuses or fails, and the candidates turned down. The rules are the owner's (Oct 11, 2026):

- Pace requests to a source's published limit, and no further. No cooldowns, queues or concurrency caps of the app's own.
- When a source refuses or fails (a 429, a 5xx, a block page, a dropped connection), switch to the next source for that data at once.
- Wait only when there is no other source, and then on the app's own, honouring `Retry-After`, so nobody has to restart anything.
- Cache answers that do not change. Results say which source they came from, errors say what to do, and the app keeps working on its last good data.

## Sources by data need

| Data need | Primary | Fallbacks, in order | Health name |
| --- | --- | --- | --- |
| 13F holdings | The SEC's [Form 13F data sets](https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets) | None | `sec` |
| Cash-flow figures | The SEC's XBRL frames (`data.sec.gov/api/xbrl/frames/...`) and `company_tickers.json` | None | `sec-xbrl` |
| Tickers | The [OpenFIGI](https://www.openfigi.com/api) mapping API | 1. The SEC's [fails-to-deliver data](https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data) (`sec-ftd`)<br>2. An exact issuer-name match against `company_tickers.json` (local, unverified) | `openfigi`, `sec-ftd` |

**13F holdings.** One zip per three-month filing window, read from the data sets page and kept in `data/raw/`; a zip already there is never fetched again. Every request goes through `SecClient` (`ingest/sec.py`), paced 0.11 s apart, just under the SEC's published 10 requests a second. Nothing else holds this data, so the client waits: a failed connection or a 5xx is asked again after about 1, 2 and 4 seconds (four attempts in all), and an SEC block (a 429, or the 403 page saying "Request Rate Threshold" or "Undeclared Automated Tool") is waited out for as long as `Retry-After` says, else 10 minutes, at most twice a run. Then the update stops with a message saying what to do; the app keeps the data it has.

**Cash-flow figures.** About 60 frames, fetched again each run because they grow as companies file, through the same client and the same waits. A frame nobody has reported yet (a 404) counts as an answer. The loaded figures stay in the database until a run brings new ones.

**Tickers.** The chain, in `tickers.py`:

1. The cache in DuckDB: OpenFIGI's answers in `openfigi`, as returned, and the fallbacks' provisional answers in `ticker_fallbacks`, each with its source.
2. OpenFIGI, for every CUSIP it has not answered. Requests are paced to its published limits (25 requests in any 6 seconds with a free key, 25 a minute without). A batch it refuses (429) or fails (a 5xx, a dropped connection), and any job it answers with an error, goes down the chain at once: nothing is retried or waited out, and the next batch asks OpenFIGI again.
3. The SEC's fails-to-deliver data, fetched the first time a run needs it: the page, then the newest 13 months of files (about 26 zips of 1.3 MB) not yet in `data/raw/ftd/`, where they are kept as downloaded. Links are read from the page and ordered by the date in each file's name, since the folders vary. Requests go through `SecClient` with `has_fallback=True`: a block or a failure moves on at once to the files already downloaded. A CUSIP's ticker is the symbol on its most recent settlement date.
4. The CUSIP's issuer name as filers write it, matched against the SEC's `company_tickers.json`, which the cash-flow step already loads. Both names lose case, punctuation, a leading "The", and trailing legal suffixes and class or share words (Inc, Corp, Co, Ltd, PLC, Cl A, Com, ...). The match must be exact and point to exactly one ticker, and exactly one stock in the 13F data must carry the name; otherwise there is no answer. Nothing is fetched, so nothing is recorded in the health file.

A fallback's ticker is provisional. The CUSIP stays unanswered in the OpenFIGI cache, so the next run asks OpenFIGI again, and its answer, found or not found, replaces the fallback's. A stock with a ticker from OpenFIGI on any of its CUSIPs keeps it; only a stock OpenFIGI gives none takes a fallback's. The stock page says where such a ticker came from: "Ticker · From the SEC's fails-to-deliver data · As of" the settlement date, or "Ticker · Matched by issuer name, unverified". An unverified ticker never brings a company's cash flow to the Accumulate list.

## Source health

Every request to an outside source is recorded as ok, failed or throttled in `data/source-health.json` (`thirteenf.health`), rewritten after each one; the requests themselves, the last 24 hours and at most 500 a source, are in `data/source-health-events.json`. The file's shape:

```json
{"updatedAt": "2026-10-11T16:00:00+00:00", "unreliable": false, "summary": "No source was unreliable in the last 24 hours.",
 "sources": {"openfigi": {"role": "primary", "for": "tickers", "ok": 412, "failed": 0, "throttled": 0,
                          "lastOk": "2026-10-11T15:59:58+00:00", "lastError": null}}}
```

A source is unreliable when it had at least 5 requests in the last 24 hours and under half of them were answered. `unreliable` is true when, for some data need, the primary and every fallback are unreliable, or the primary is and has no fallback. `update-data` and `python -m thirteenf.tickers` then end with a line starting "Sources:" and the summary. A session-start hook on the owner's PC reads this file, so its path and shape stay as they are.

## Considered and turned down

| Candidate | For | Why not |
| --- | --- | --- |
| EDGAR's per-filing XML (each 13F's information table) | 13F holdings, if the data sets fail | The same host and the same throttle as the data sets, so it fails when they do, and it takes thousands of requests a quarter where the data sets take one zip |
| Keyed or paid APIs (market-data vendors, paid CUSIP services) | Tickers, cash-flow figures | Against the owner's rules for outside services |
