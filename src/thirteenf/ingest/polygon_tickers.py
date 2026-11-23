"""Polygon's ticker list, looked up by CUSIP: the last ticker fallback, for widely held stocks.

OpenFIGI, the SEC's fails-to-deliver data and the issuer-name match leave some stocks with
no ticker, or only an unverified one, and a stock without a verified ticker gets no company
financials, no prices and no place on the Accumulate list. Polygon's reference endpoint
(/v3/reference/tickers?cusip=...) answers by CUSIP with a free key, but its free plan allows
5 requests a minute, so only the stocks that matter are asked: held by MIN_FUNDS or more
funds in the latest period, most held first, at most MAX_PER_RUN a run.

Polygon does not return the CUSIP it matched (its licence), so an answer is checked before it
is used: exactly one ticker, a stock market listing, and a company name whose first word
matches the name funds filed. A filter Polygon ignored would answer with its whole list, which
fails that check. Every answer is kept in polygon_cusips: a ticker found is reused without
asking again, a miss is asked again after RETRY_AFTER (or with --retry-missing). A ticker found
goes to ticker_fallbacks as source "polygon", provisional like the other fallbacks.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import duckdb
import httpx

from thirteenf import health
from thirteenf.ingest import issuer_names, openfigi
from thirteenf.ingest.prices import MinutePacer

SOURCE = "polygon"  # health and ticker_fallbacks name it like the price source: one service, one key
URL = "https://api.polygon.io/v3/reference/tickers"
REQUESTS_PER_MINUTE = 5
MIN_FUNDS = 100  # the Accumulate list's default minimum: a stock below it cannot be picked anyway
MAX_PER_RUN = 60  # about 12 minutes at the free plan's pace
RETRY_AFTER = timedelta(days=30)
TIMEOUT = 30.0

FOUND, NOT_FOUND, NAME_DIFFERS, AMBIGUOUS = "found", "not found", "name differs", "ambiguous"

CACHE_DDL = """
CREATE TABLE IF NOT EXISTS polygon_cusips (
    cusip    VARCHAR PRIMARY KEY,
    outcome  VARCHAR NOT NULL,   -- found, not found, name differs, ambiguous
    ticker   VARCHAR,            -- found: Polygon's ticker
    name     VARCHAR,            -- Polygon's company name, when it answered with one
    asked_at TIMESTAMP NOT NULL
)
"""


class PolygonTickersDown(RuntimeError):
    """Polygon refused or failed: the rest of the stocks wait for the next run."""


class PolygonTickers:
    """Polygon's ticker reference, one CUSIP per request, paced to the free plan."""

    def __init__(
        self,
        api_key: str,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"}, timeout=TIMEOUT, transport=transport
        )
        self._pacer = MinutePacer(REQUESTS_PER_MINUTE, clock, sleep)

    def lookup(self, cusip: str) -> list[dict]:
        """Polygon's active stock listings for the CUSIP (empty when it knows none). Raises PolygonTickersDown."""
        self._pacer.wait()
        try:
            response = self._client.get(URL, params={"cusip": cusip, "market": "stocks", "limit": 10})
        except httpx.TransportError as err:
            health.record(SOURCE, "failed", type(err).__name__)
            raise PolygonTickersDown(f"Polygon: {type(err).__name__}") from err
        if response.status_code == 429:
            health.record(SOURCE, "throttled", "429")
            raise PolygonTickersDown("Polygon refused (429)")
        try:
            body = response.json() if response.text.lstrip().startswith("{") else {}
        except ValueError:
            body = {}
        if response.status_code != 200 or body.get("status") not in ("OK", "DELAYED"):
            health.record(SOURCE, "failed", f"HTTP {response.status_code}")
            raise PolygonTickersDown(
                f"Polygon's ticker list answered HTTP {response.status_code}: {str(body.get('error') or body.get('message') or '')[:80]}"
            )
        health.record(SOURCE, "ok")
        return [r for r in body.get("results") or [] if isinstance(r, dict) and r.get("ticker")]

    def close(self) -> None:
        self._client.close()


def first_word(name: str | None) -> str:
    """A company name's first word for the check, written as issuer_names.normalize writes names:
    'The Walt Disney Co' gives WALT, 'U.S. Bancorp' US."""
    text = issuer_names.STATE_MARK.sub("", (name or "").upper())
    text = issuer_names.INITIALS.sub(r"\1", text.replace("&", " AND ").replace("'", "").replace("’", ""))
    words = re.findall(r"[A-Z0-9]+", text)
    if words[:1] == ["THE"]:
        words = words[1:]
    return words[0] if words else ""


def judge(listings: list[dict], name_filed: str) -> tuple[str, str | None, str | None]:
    """The outcome for one CUSIP's answer: (outcome, ticker, Polygon's name)."""
    tickers = {r["ticker"] for r in listings}
    if not tickers:
        return NOT_FOUND, None, None
    if len(tickers) > 1:
        return AMBIGUOUS, None, "; ".join(sorted(str(r.get("name", "")) for r in listings))[:200]
    listing = listings[0]
    name = str(listing.get("name") or "")
    if not first_word(name) or first_word(name) != first_word(name_filed):
        return NAME_DIFFERS, None, name
    return FOUND, str(listing["ticker"]), name


def candidates(con: duckdb.DuckDBPyConnection, now: datetime, minimum: int = MIN_FUNDS) -> list[tuple[str, str]]:
    """Stocks held by `minimum`+ funds in the latest period with no ticker or only an issuer-name
    match, most held first, leaving out those Polygon missed within RETRY_AFTER: (cusip, name filed)."""
    con.execute(CACHE_DDL)
    cutoff = now.astimezone(UTC).replace(tzinfo=None) - RETRY_AFTER
    return [
        (r[0], r[1])
        for r in con.execute(
            """
            SELECT s.cusip, s.name_filed
            FROM stocks s JOIN stock_periods sp ON sp.cusip = s.cusip
            WHERE sp.period = (SELECT max(period) FROM stock_periods) AND sp.funds_holding >= ?
              AND s.kind = 'stock' AND (s.ticker IS NULL OR s.ticker_source = 'issuer-name')
              AND s.cusip NOT IN (SELECT cusip FROM polygon_cusips WHERE outcome <> ? AND asked_at > ?)
            ORDER BY sp.funds_holding DESC, s.cusip
            """,
            [minimum, FOUND, cutoff],
        ).fetchall()
    ]


def _store_fallback(con: duckdb.DuckDBPyConnection, cusip: str, ticker: str, name: str | None, when: datetime) -> None:
    con.execute(openfigi.CACHE_DDL)
    con.execute("DELETE FROM ticker_fallbacks WHERE cusip = ?", [cusip])
    con.execute("INSERT INTO ticker_fallbacks VALUES (?, ?, ?, NULL, ?, ?)", [cusip, ticker, SOURCE, name, when])


def fill(
    open_db: Callable[[], duckdb.DuckDBPyConnection],
    client: PolygonTickers,
    log: Callable[[str], None] = print,
    now: datetime | None = None,
    max_per_run: int = MAX_PER_RUN,
    minimum: int = MIN_FUNDS,
) -> dict[str, int]:
    """Give the widely held stocks without a verified ticker Polygon's, where it has one. A ticker
    Polygon gave before is put back without asking. Returns counts by outcome, and "reused"."""
    now = now or datetime.now(UTC)
    when = now.astimezone(UTC).replace(tzinfo=None)
    with open_db() as con:
        wanted = candidates(con, now, minimum)
        cached = {
            r[0]: (r[1], r[2])
            for r in con.execute("SELECT cusip, ticker, name FROM polygon_cusips WHERE outcome = ?", [FOUND]).fetchall()
        }
    counts = {"reused": 0, FOUND: 0, NOT_FOUND: 0, NAME_DIFFERS: 0, AMBIGUOUS: 0, "left": 0}
    ask = []
    for cusip, name_filed in wanted:
        if cusip in cached:  # OpenFIGI's "not found" can clear a fallback; Polygon's answer still stands
            with open_db() as con:
                _store_fallback(con, cusip, cached[cusip][0], cached[cusip][1], when)
            counts["reused"] += 1
        else:
            ask.append((cusip, name_filed))
    counts["left"] = max(0, len(ask) - max_per_run)
    ask = ask[:max_per_run]
    if ask:
        log(
            f"  Asking Polygon's ticker list about {len(ask):,} widely held stocks without a verified ticker "
            f"(about {len(ask) / REQUESTS_PER_MINUTE:,.0f} minutes at its free plan's pace)"
        )
    for i, (cusip, name_filed) in enumerate(ask):
        try:
            listings = client.lookup(cusip)
        except PolygonTickersDown as err:
            counts["left"] += len(ask) - i
            log(f"    {err}; the rest wait for the next run")
            break
        outcome, ticker, name = judge(listings, name_filed)
        counts[outcome] += 1
        with open_db() as con:
            con.execute(CACHE_DDL)
            con.execute("DELETE FROM polygon_cusips WHERE cusip = ?", [cusip])
            con.execute("INSERT INTO polygon_cusips VALUES (?, ?, ?, ?, ?)", [cusip, outcome, ticker, name, when])
            if ticker:
                _store_fallback(con, cusip, ticker, name, when)
        if outcome == NAME_DIFFERS:
            log(f"    {cusip} ({name_filed}): Polygon names it {name!r}, so its ticker is not used")
    return counts


def summary(counts: dict[str, int]) -> str:
    """One line on what Polygon's ticker list did this run; "" when it was not needed."""
    asked = counts[FOUND] + counts[NOT_FOUND] + counts[NAME_DIFFERS] + counts[AMBIGUOUS]
    if not asked and not counts["reused"] and not counts["left"]:
        return ""
    parts = [f"{counts[FOUND]:,} of {asked:,} asked found"]
    if counts["reused"]:
        parts.append(f"{counts['reused']:,} kept from an earlier run")
    misses = counts[NOT_FOUND] + counts[NAME_DIFFERS] + counts[AMBIGUOUS]
    if misses:
        parts.append(f"{misses:,} not found or not matching (asked again in {RETRY_AFTER.days} days)")
    if counts["left"]:
        parts.append(f"{counts['left']:,} left for the next run")
    return "  Polygon's ticker list: " + ", ".join(parts) + "."
