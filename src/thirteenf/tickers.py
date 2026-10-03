"""python -m thirteenf.tickers maps every new CUSIP to a ticker with OpenFIGI.

Put a free key from openfigi.com in data/settings.toml first (openfigi_api_key):
with it the ~39,000 CUSIPs take a few minutes; without it OpenFIGI allows about
250 a minute.
"""

import argparse
import sys

from thirteenf.config import ensure_settings_file, openfigi_api_key
from thirteenf.db import connect
from thirteenf.ingest import openfigi


def update_tickers(log=print, retry_missing: bool = False) -> dict:
    key = openfigi_api_key()
    with connect() as con:
        con.execute(openfigi.CACHE_DDL)
        if retry_missing:
            con.execute("DELETE FROM openfigi WHERE NOT found")
        pending = len(openfigi.pending_cusips(con))
    if not key:
        minutes = pending / (openfigi.WITHOUT_KEY.jobs_per_request * openfigi.WITHOUT_KEY.requests_per_window)
        log(
            f"No OpenFIGI key: {pending:,} CUSIPs at OpenFIGI's keyless rate take about {minutes:,.0f} "
            f"minutes. A free key from openfigi.com, pasted into {ensure_settings_file()}, makes it a few minutes."
        )
    log(f"Mapping CUSIPs to tickers with OpenFIGI ({'with' if key else 'without'} an API key)")
    client = openfigi.OpenFigiClient(key)
    try:
        counts = openfigi.update(connect, client, log=log)
    finally:
        client.close()
    from thirteenf.model.build import SQL_STOCKS

    with connect() as con:
        con.execute(SQL_STOCKS)
        tickers = con.execute("SELECT count(*) FROM stocks WHERE ticker IS NOT NULL").fetchone()[0]
    log(f"  {tickers:,} stocks have a ticker")
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m thirteenf.tickers")
    parser.add_argument("--retry-missing", action="store_true", help="ask again about CUSIPs OpenFIGI did not know")
    args = parser.parse_args()
    update_tickers(retry_missing=args.retry_missing)
    return 0


if __name__ == "__main__":
    sys.exit(main())
