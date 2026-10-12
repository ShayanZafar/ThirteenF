"""python -m thirteenf.tickers maps every new CUSIP to a ticker.

The chain, from docs/sources.md: the DuckDB cache, then OpenFIGI (the primary),
then for a batch OpenFIGI refuses or fails, at once, the SEC's fails-to-deliver
data, then an exact issuer-name match against the SEC's ticker list (unverified).
For a CUSIP OpenFIGI answers "not found", the fails-to-deliver symbol alone stands
in (decision #14, Oct 12, 2026). A fallback's ticker is provisional: the next run
asks OpenFIGI about it again.

Put a free key from openfigi.com in data/settings.toml first (openfigi_api_key):
with it the ~39,000 CUSIPs take a few minutes; without it OpenFIGI allows about
250 a minute.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from datetime import UTC, date, datetime

import duckdb
import httpx

from thirteenf import health
from thirteenf.config import MissingUserAgent, ensure_settings_file, openfigi_api_key
from thirteenf.db import connect, scalar
from thirteenf.ingest import ftd, issuer_names, openfigi
from thirteenf.ingest.sec import SecClient, SecUnavailable

FTD = "sec-ftd"
NAMES = "issuer-name"


class TickerFallback:
    """The sources after OpenFIGI, for the CUSIPs of a batch it did not answer, and
    (`not_found`) for the CUSIPs it does not know.

    The first call of a run fetches the fails-to-deliver files not downloaded yet
    (the SEC can refuse; the files already there still answer) and loads them. Each
    CUSIP OpenFIGI did not answer takes the symbol on its most recent settlement
    date, else an issuer-name match, else nothing; one it does not know takes only
    the symbol. What is found goes to ticker_fallbacks, replacing an earlier
    fallback's ticker for the same CUSIP."""

    def __init__(
        self,
        open_db: Callable = connect,
        log: Callable[[str], None] = print,
        make_client: Callable[[], SecClient] | None = None,
    ) -> None:
        self.open_db, self.log = open_db, log
        self.make_client = make_client or (lambda: SecClient(log=log))
        self.symbols: dict[str, tuple[str, date]] | None = None  # the fails-to-deliver data, once loaded
        self.names: issuer_names.NameMatch | None = None
        self.counts = {"asked": 0, FTD: 0, NAMES: 0}  # CUSIPs OpenFIGI did not answer
        self.unknown = {"asked": 0, FTD: 0}  # CUSIPs OpenFIGI does not know

    def __call__(self, cusips: list[str]) -> None:
        rows = self._answer(cusips, by_name=True)
        self.counts["asked"] += len(cusips)
        for row in rows:
            self.counts[row[2]] += 1

    def not_found(self, cusips: list[str]) -> None:
        """CUSIPs OpenFIGI answered "not found" for: only the fails-to-deliver symbol stands in."""
        rows = self._answer(cusips, by_name=False)
        self.unknown["asked"] += len(cusips)
        self.unknown[FTD] += len(rows)

    def _answer(self, cusips: list[str], by_name: bool) -> list[tuple]:
        """Store each CUSIP's fallback ticker, if any, and return the rows stored."""
        if self.symbols is None:
            self.symbols = self._fails_to_deliver()
        fetched_at = datetime.now(UTC).replace(tzinfo=None)
        rows: list[tuple[str, str, str, date | None, str | None, datetime]] = []
        for cusip in cusips:
            symbol = self.symbols.get(cusip)
            if symbol:
                rows.append((cusip, symbol[0], FTD, symbol[1], None, fetched_at))
                continue
            if not by_name:
                continue
            if self.names is None:
                with self.open_db() as con:
                    self.names = issuer_names.NameMatch.from_db(con)
            named = self.names.ticker(cusip)
            if named:
                rows.append((cusip, named[0], NAMES, None, named[1], fetched_at))
        if rows:
            marks = ", ".join(["?"] * len(rows))
            with self.open_db() as con:
                con.execute(openfigi.CACHE_DDL)
                con.execute(f"DELETE FROM ticker_fallbacks WHERE cusip IN ({marks})", [row[0] for row in rows])
                con.execute(
                    "INSERT INTO ticker_fallbacks VALUES " + ", ".join(["(?, ?, ?, ?, ?, ?)"] * len(rows)),
                    [value for row in rows for value in row],
                )
        return rows

    def _fails_to_deliver(self) -> dict[str, tuple[str, date]]:
        """Fetch the files not downloaded yet, load the new ones, and read each CUSIP's latest symbol."""
        self.log("  Turning to the SEC's fails-to-deliver data for the CUSIPs OpenFIGI did not answer or does not know")
        try:
            client = self.make_client()
        except MissingUserAgent:
            self.log("    SEC_USER_AGENT is not set, so nothing new is downloaded; using the files already here")
        else:
            try:
                ftd.download_new(client, self.log)
            except (SecUnavailable, httpx.HTTPStatusError, ftd.NoLinks, OSError) as err:
                self.log(
                    f"    {str(err).splitlines()[0]}; using the files already downloaded, then the issuer-name match"
                )
            finally:
                client.close()
        with self.open_db() as con:
            ftd.load_new(con, log=self.log)
            return ftd.latest_symbols(con)

    def summary(self) -> str:
        """A line on what the fallbacks found this run for the CUSIPs OpenFIGI did not answer, and one for
        those it does not know; "" when there were none."""
        lines = []
        if self.counts["asked"]:
            asked, from_ftd, named = self.counts["asked"], self.counts[FTD], self.counts[NAMES]
            lines.append(
                f"  OpenFIGI did not answer for {asked:,} CUSIPs. Their tickers for now: {from_ftd:,} from the SEC's "
                f"fails-to-deliver data, {named:,} matched by issuer name (unverified), "
                f"{asked - from_ftd - named:,} none. The next run asks OpenFIGI again."
            )
        if self.unknown["asked"]:
            asked, from_ftd = self.unknown["asked"], self.unknown[FTD]
            one = from_ftd == 1
            lines.append(
                f"  OpenFIGI does not know {asked:,} CUSIPs. For now {from_ftd:,} "
                f"{'takes its' if one else 'take their'} ticker from the SEC's fails-to-deliver data; "
                f"the next run asks OpenFIGI about {'it' if one else 'them'} again."
            )
        return "\n".join(lines)


def not_found_cusips(con: duckdb.DuckDBPyConnection) -> list[str]:
    """CUSIPs OpenFIGI answered "not found" for, leaving out those with a wrong check digit (never sent)."""
    rows = con.execute(
        "SELECT cusip FROM openfigi WHERE NOT found AND id_type <> ? ORDER BY cusip", [openfigi.STAGE_INVALID]
    ).fetchall()
    return [r[0] for r in rows if openfigi.valid_cusip(r[0])]


def update_tickers(log=print, retry_missing: bool = False, fallback: TickerFallback | None = None) -> dict:
    key = openfigi_api_key()
    with connect() as con:
        con.execute(openfigi.CACHE_DDL)
        if retry_missing:
            con.execute("DELETE FROM openfigi WHERE NOT found")
        # A "not found" with a fails-to-deliver ticker standing in is provisional: ask OpenFIGI again.
        con.execute(
            "DELETE FROM openfigi WHERE NOT found AND cusip IN (SELECT cusip FROM ticker_fallbacks WHERE source = ?)",
            [FTD],
        )
        pending = len(openfigi.pending_cusips(con))
    if not key:
        minutes = pending / (openfigi.WITHOUT_KEY.jobs_per_request * openfigi.WITHOUT_KEY.requests_per_window)
        log(
            f"No OpenFIGI key: {pending:,} CUSIPs at OpenFIGI's keyless rate take about {minutes:,.0f} "
            f"minutes. A free key from openfigi.com, pasted into {ensure_settings_file()}, makes it a few minutes."
        )
    log(f"Mapping CUSIPs to tickers with OpenFIGI ({'with' if key else 'without'} an API key)")
    fallback = fallback or TickerFallback(connect, log)
    client = openfigi.OpenFigiClient(key)
    try:
        counts = openfigi.update(connect, client, log=log, fallback=fallback)
    finally:
        client.close()
    with connect() as con:
        unknown = not_found_cusips(con)
    if unknown:
        fallback.not_found(unknown)
    if fallback.summary():
        log(fallback.summary())
    from thirteenf.model.build import rebuild_after_tickers

    with connect() as con:
        rebuild_after_tickers(con)
        tickers = scalar(con, "SELECT count(*) FROM stocks WHERE ticker IS NOT NULL")
    log(f"  {tickers:,} stocks have a ticker")
    return counts | {"fallback": dict(fallback.counts), "not_found": dict(fallback.unknown)}


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m thirteenf.tickers")
    parser.add_argument("--retry-missing", action="store_true", help="ask again about CUSIPs OpenFIGI did not know")
    args = parser.parse_args()
    update_tickers(retry_missing=args.retry_missing)
    warning = health.warning()
    if warning:
        print(f"Sources: {warning} Details in {health.HEALTH_PATH}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
