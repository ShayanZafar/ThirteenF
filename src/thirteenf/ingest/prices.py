"""Daily prices and volume for the stocks the app recommends or watches.

13F says where funds' money moved a quarter ago; daily prices say whether the
market has priced that in since. Stooq is the primary source (docs/sources.md):
one CSV per symbol, Date,Open,High,Low,Close,Volume, adjusted for splits, with a
free key. Tiingo is the fallback for a symbol Stooq lacks, or for the rest of a
run once Stooq says its daily limit is reached; its free plan allows 50 symbols
an hour, so a run asks it about at most that many and leaves the rest for the
next run. Neither source is waited for: a refusal or a failure moves on at once.

Each answer is kept as downloaded in data/raw/prices/<source>/<symbol>.<ext> and
loaded as it is into raw_prices, replacing the symbol's earlier rows; which
source answered for each symbol, and when, is in price_fetches. A symbol is
fetched again once its last fetch is REFRESH_AFTER old. Symbols are the app's
own key for a ticker: letters and digits in capitals with a hyphen for anything
else (BRK/B and BRK-B both read BRK-B), spelled the way each source wants.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import httpx

from thirteenf import health
from thirteenf.config import RAW_DIR
from thirteenf.db import scalar

PRICES_DIR = RAW_DIR / "prices"
STOOQ = "stooq"
TIINGO = "tiingo"
MARKET = "SPY"  # the market, for "has the price moved more than the market": an S&P 500 ETF
HISTORY_YEARS = 3  # how far back the first fetch of a symbol reaches
REFRESH_AFTER = timedelta(hours=20)  # a symbol fetched more recently is not asked for again
TIMEOUT = 30.0

RAW_DDL = """
CREATE TABLE IF NOT EXISTS raw_prices (
    symbol VARCHAR, day DATE, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE,
    source VARCHAR, source_file VARCHAR
);
CREATE TABLE IF NOT EXISTS price_fetches (
    symbol VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, fetched_at TIMESTAMP NOT NULL, rows INTEGER NOT NULL
)
"""


class PriceSourceDown(RuntimeError):
    """The source refused (a 429, its limit message) or failed (a 5xx, a dropped connection,
    an answer that is not price data): the caller moves to the next source for the rest of the run."""


class PriceLimitReached(PriceSourceDown):
    """The source's published limit is reached for now: not asked again this run."""


def symbol_key(ticker: str) -> str:
    """The app's symbol for a ticker: capitals, letters and digits, a hyphen for anything else."""
    return "".join(ch if ch.isalnum() else "-" for ch in ticker.strip().upper()).strip("-")


def _since(today: date) -> date:
    return today.replace(year=today.year - HISTORY_YEARS)


class Stooq:
    """Stooq's historical data download, one CSV per symbol. The key is passed as `apikey`
    (Oct 26, 2026); the CSV header is checked, so a changed answer is a failure, not bad data."""

    name = STOOQ
    URL = "https://stooq.com/q/d/l/"
    HEADER = "Date,Open,High,Low,Close,Volume"
    NO_DATA = ("no data", "brak danych")
    extension = "csv"

    def __init__(self, api_key: str, transport: httpx.BaseTransport | None = None) -> None:
        self.api_key = api_key
        self._client = httpx.Client(timeout=TIMEOUT, transport=transport, follow_redirects=True)

    def fetch(self, symbol: str, today: date) -> str | None:
        """The symbol's CSV, or None when Stooq has no data for it. Raises PriceSourceDown."""
        params = {"s": f"{symbol.lower()}.us", "i": "d", "d1": _since(today).strftime("%Y%m%d"), "apikey": self.api_key}
        try:
            response = self._client.get(self.URL, params=params)
        except httpx.TransportError as err:
            health.record(self.name, "failed", type(err).__name__)
            raise PriceSourceDown(f"Stooq: {type(err).__name__}") from err
        text = response.text.strip()
        if response.status_code == 429:
            health.record(self.name, "throttled", "429")
            raise PriceLimitReached("Stooq refused (429)")
        if response.status_code != 200:
            health.record(self.name, "failed", f"HTTP {response.status_code}")
            raise PriceSourceDown(f"Stooq answered HTTP {response.status_code}")
        first = text.splitlines()[0].strip() if text else ""
        if first == self.HEADER:
            health.record(self.name, "ok")
            return text + "\n"
        if text.lower() in self.NO_DATA:
            health.record(self.name, "ok")
            return None
        if "limit" in text.lower():  # "Przekroczony dzienny limit wywolan": the daily limit is reached
            health.record(self.name, "throttled", first[:80])
            raise PriceLimitReached(f"Stooq: {first[:80]}")
        health.record(self.name, "failed", first[:80] or "empty answer")
        raise PriceSourceDown(f"Stooq did not answer with price data: {first[:80] or 'an empty answer'!r}")

    def close(self) -> None:
        self._client.close()


class Tiingo:
    """Tiingo's end-of-day prices, one JSON array per symbol, adjusted for splits and
    dividends (adjClose, adjVolume). The free plan allows SYMBOLS_PER_HOUR symbols an hour;
    a run never sends more, and never waits for the hour to pass."""

    name = TIINGO
    URL = "https://api.tiingo.com/tiingo/daily/{symbol}/prices"
    SYMBOLS_PER_HOUR = 50
    extension = "json"

    def __init__(
        self,
        api_key: str,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = httpx.Client(headers={"Authorization": f"Token {api_key}"}, timeout=TIMEOUT, transport=transport)
        self._clock = clock
        self._sent: deque[float] = deque()

    def fetch(self, symbol: str, today: date) -> str | None:
        now = self._clock()
        while self._sent and now - self._sent[0] >= 3600:
            self._sent.popleft()
        if len(self._sent) >= self.SYMBOLS_PER_HOUR:
            raise PriceLimitReached(f"Tiingo's free plan allows {self.SYMBOLS_PER_HOUR} symbols an hour")
        self._sent.append(now)
        url = self.URL.format(symbol=symbol.upper())
        try:
            response = self._client.get(url, params={"startDate": _since(today).isoformat(), "format": "json"})
        except httpx.TransportError as err:
            health.record(self.name, "failed", type(err).__name__)
            raise PriceSourceDown(f"Tiingo: {type(err).__name__}") from err
        if response.status_code == 404:
            health.record(self.name, "ok")
            return None
        if response.status_code == 429:
            health.record(self.name, "throttled", "429")
            raise PriceLimitReached("Tiingo refused (429)")
        if response.status_code != 200 or not response.text.lstrip().startswith("["):
            health.record(self.name, "failed", f"HTTP {response.status_code}")
            raise PriceSourceDown(f"Tiingo answered HTTP {response.status_code}")
        health.record(self.name, "ok")
        return response.text

    def close(self) -> None:
        self._client.close()


Provider = Stooq | Tiingo


@dataclass
class Fetched:
    symbol: str
    source: str
    path: Path | None  # None when the source has no data for the symbol


def fetch_symbol(providers: list[Provider], symbol: str, today: date, folder: Path, log) -> Fetched | None:
    """Ask each provider still up, in order, for one symbol, and keep the answer as a file.

    A provider that refuses or fails is dropped from the list for the rest of the run,
    with a line saying why; one that has no data for the symbol leaves it to the next.
    Returns None when no provider is left."""
    no_data = None
    for provider in list(providers):
        try:
            text = provider.fetch(symbol, today)
        except PriceSourceDown as err:
            providers.remove(provider)
            log(f"    {err}; {'moving to ' + providers[0].name if providers else 'stopping'} for the rest of the run")
            continue
        if text is None:
            no_data = Fetched(symbol, provider.name, None)
            continue
        target = folder / provider.name / f"{symbol}.{provider.extension}"
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_suffix(target.suffix + ".part")
        part.write_text(text, encoding="utf-8")
        part.replace(target)
        return Fetched(symbol, provider.name, target)
    return no_data


def _quoted(path: Path) -> str:
    return path.as_posix().replace("'", "''")


def load_file(con: duckdb.DuckDBPyConnection, fetched: Fetched, fetched_at: datetime) -> int:
    """Replace the symbol's rows in raw_prices with the file's, and note the fetch. Returns the rows."""
    con.execute(RAW_DDL)
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute("DELETE FROM raw_prices WHERE symbol = ?", [fetched.symbol])
        if fetched.path is not None and fetched.source == STOOQ:
            con.execute(
                f"""
                INSERT INTO raw_prices
                SELECT ?, "Date", "Open", "High", "Low", "Close", "Volume", ?, ?
                FROM read_csv('{_quoted(fetched.path)}', header=true, columns={{
                    'Date': 'DATE', 'Open': 'DOUBLE', 'High': 'DOUBLE', 'Low': 'DOUBLE',
                    'Close': 'DOUBLE', 'Volume': 'DOUBLE'}}, auto_detect=false)
                """,
                [fetched.symbol, fetched.source, fetched.path.name],
            )
        elif fetched.path is not None:
            con.execute(
                f"""
                INSERT INTO raw_prices
                SELECT ?, CAST(date AS DATE), adjOpen, adjHigh, adjLow, adjClose, adjVolume, ?, ?
                FROM read_json('{_quoted(fetched.path)}', columns={{
                    'date': 'VARCHAR', 'adjOpen': 'DOUBLE', 'adjHigh': 'DOUBLE', 'adjLow': 'DOUBLE',
                    'adjClose': 'DOUBLE', 'adjVolume': 'DOUBLE'}})
                """,
                [fetched.symbol, fetched.source, fetched.path.name],
            )
        rows = scalar(con, "SELECT count(*) FROM raw_prices WHERE symbol = ?", [fetched.symbol])
        con.execute("DELETE FROM price_fetches WHERE symbol = ?", [fetched.symbol])
        con.execute(
            "INSERT INTO price_fetches VALUES (?, ?, ?, ?)",
            [fetched.symbol, fetched.source, fetched_at.replace(tzinfo=None), rows],
        )
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    return rows


def due(con: duckdb.DuckDBPyConnection, symbols: list[str], now: datetime) -> list[str]:
    """The symbols to fetch this run: never fetched first, then the oldest fetches, leaving
    out those fetched within REFRESH_AFTER."""
    con.execute(RAW_DDL)
    last = dict(con.execute("SELECT symbol, fetched_at FROM price_fetches").fetchall())
    cutoff = now.replace(tzinfo=None) - REFRESH_AFTER
    wanted = [s for s in dict.fromkeys(symbols) if s not in last or last[s] <= cutoff]
    return sorted(wanted, key=lambda s: (s in last, last.get(s), s))


def update(
    open_db: Callable[[], duckdb.DuckDBPyConnection],
    providers: list[Provider],
    symbols: list[str],
    log=print,
    now: datetime | None = None,
    folder: Path | None = None,
) -> dict[str, int]:
    """Fetch and load the symbols due, down the provider chain. Returns counts of what happened."""
    now = now or datetime.now(UTC)
    folder = folder or PRICES_DIR
    with open_db() as con:
        todo = due(con, symbols, now)
    counts = {"wanted": len(symbols), "due": len(todo), "fetched": 0, "no_data": 0, "left": 0}
    chain = list(providers)
    for i, symbol in enumerate(todo):
        fetched = fetch_symbol(chain, symbol, now.date(), folder, log)
        if fetched is None:
            counts["left"] = len(todo) - i
            break
        with open_db() as con:
            rows = load_file(con, fetched, now)
        counts["fetched" if fetched.path else "no_data"] += 1
        if fetched.path is None:
            log(f"    {symbol}: no price data at {fetched.source}")
        elif rows == 0:
            log(f"    {symbol}: {fetched.source} answered with no rows")
    return counts
