---
paths:
  - "src/thirteenf/ingest/**"
  - "src/thirteenf/tickers.py"
  - "src/thirteenf/health.py"
  - "src/thirteenf/config.py"
  - "tests/conftest.py"
  - "tests/test_sec_retry.py"
  - "tests/test_ingest.py"
  - "tests/test_ftd.py"
  - "tests/test_openfigi.py"
  - "tests/test_tickers.py"
  - "tests/test_ticker_fallbacks.py"
  - "tests/test_health.py"
  - "tests/test_seams.py"
  - "docs/sources.md"
  - "docs/troubleshooting.md"
---

# SEC access, tickers and outside sources

`docs/sources.md` is the register of outside sources: for each data need the primary, the fallbacks in order, what "unreliable" means, where source health is recorded, and the candidates turned down. Follow the owner's rules at its top, and update it when a source or fallback changes.

## The SEC client (`ingest/sec.py`)

- `SecClient` keeps under 10 requests per second by pacing every request 0.11 s apart.
- `SecClient` already waits only where nothing else can answer: for the 13F data sets and the XBRL frames, a failed connection or a 5xx is asked again after about 1, 2 and 4 seconds (four attempts in all), and an SEC block (a 429, or the 403 "Request Rate Threshold" page) is waited out for as long as `Retry-After` says, else 10 minutes, as many times as it comes (decision #13, Oct 12, 2026).
- The 403 "Undeclared Automated Tool" page means `SEC_USER_AGENT` is wrong, so waiting won't help: it stops at once with a `RuntimeError` saying to set it correctly.
- A caller with another source for the same data passes `has_fallback=True`: a block or a failure then raises `SecUnavailable` (`SecBlocked` for a block) at once and the caller moves on.
- Every answer is recorded in `data/source-health.json` (`thirteenf.health`).

## Tickers (`tickers.py`, `ingest/openfigi.py`, `ingest/ftd.py`, `ingest/issuer_names.py`)

- OpenFIGI's answers are cached in DuckDB. A batch OpenFIGI refuses or fails goes at once to the SEC's fails-to-deliver data (zips kept in `data/raw/ftd/`), then to an exact issuer-name match (unverified).
- A CUSIP OpenFIGI answers "not found" for takes the fails-to-deliver symbol alone, never the issuer-name match (decision #14, Oct 12, 2026).
- Those tickers are provisional, and the next run asks OpenFIGI again. `docs/sources.md` has the whole chain.
