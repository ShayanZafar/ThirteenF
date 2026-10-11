"""Map CUSIPs to tickers with the OpenFIGI API, cached in DuckDB.

Every CUSIP in the data is looked up once, in up to three passes, each only for
the CUSIPs the pass before did not match:

1. the CUSIP on the US composite listing (a CINS code, for foreign issuers);
2. the CUSIP on any exchange, then its share class on the US composite listing;
3. the FIGI filers wrote in INFOTABLE, where there is one, as a FIGI and then
   as a share class on the US composite listing (some filers write that one).

Answers are kept in the `openfigi` table with OpenFIGI's response as returned,
so later runs only ask about new CUSIPs.

OpenFIGI is the primary source for tickers (docs/sources.md). Requests are paced
to its published limits and nothing else: a batch it refuses (429) or fails (a
5xx, a failed connection), and a job it answers with an error, go at once to the
fallback the caller passes (thirteenf.tickers: the SEC's fails-to-deliver data,
then an issuer-name match), and the next batch asks OpenFIGI again. Fallback
tickers are kept in `ticker_fallbacks` as provisional: those CUSIPs stay unanswered
here, so later runs ask OpenFIGI again, and its answer, stored, replaces them.
"""

from __future__ import annotations

import json
import time
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

import duckdb
import httpx

from thirteenf import health

API = "https://api.openfigi.com/v3/mapping"
SOURCE = "openfigi"  # in the source health file: the primary source for tickers


@dataclass(frozen=True)
class Limits:
    """OpenFIGI's mapping limits (openfigi.com/api/documentation)."""

    jobs_per_request: int
    requests_per_window: int
    window_seconds: float


WITH_KEY = Limits(jobs_per_request=100, requests_per_window=25, window_seconds=6.0)
WITHOUT_KEY = Limits(jobs_per_request=10, requests_per_window=25, window_seconds=60.0)

CACHE_DDL = """
CREATE TABLE IF NOT EXISTS openfigi (
    cusip            VARCHAR PRIMARY KEY,
    id_type          VARCHAR NOT NULL,   -- ID_CUSIP, or ID_BB_GLOBAL from the filers' FIGI
    id_value         VARCHAR NOT NULL,
    found            BOOLEAN NOT NULL,
    ticker           VARCHAR,
    name             VARCHAR,
    exch_code        VARCHAR,
    security_type    VARCHAR,
    security_type2   VARCHAR,
    market_sector    VARCHAR,
    figi             VARCHAR,
    composite_figi   VARCHAR,
    share_class_figi VARCHAR,
    response         VARCHAR NOT NULL,   -- OpenFIGI's answer for this job, as returned
    fetched_at       TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS ticker_fallbacks (
    cusip      VARCHAR PRIMARY KEY,
    ticker     VARCHAR NOT NULL,
    source     VARCHAR NOT NULL,   -- sec-ftd or issuer-name; provisional until OpenFIGI answers
    as_of      DATE,               -- sec-ftd: the settlement date the symbol was reported on
    detail     VARCHAR,            -- issuer-name: the SEC's name for the company
    fetched_at TIMESTAMP NOT NULL
)
"""


class BatchError(RuntimeError):
    """OpenFIGI's answer did not line up with the jobs sent."""


class OpenFigiUnavailable(RuntimeError):
    """OpenFIGI refused (429) or failed (a 5xx, a failed connection, an unreadable answer) a request."""


# OpenFIGI's error for an identifier it rejects outright; asking again never helps.
REJECTED = "Invalid idValue format."
# The error a job gets when its whole batch was refused or failed.
UNANSWERED = "OpenFIGI did not answer"


def valid_cusip(cusip: str) -> bool:
    """Whether a CUSIP's ninth character is its check digit. Filers' typos and
    placeholders (000000001) fail, and OpenFIGI rejects them unseen."""
    if len(cusip) != 9 or not cusip[8].isdigit():
        return False
    total = 0
    for i, ch in enumerate(cusip[:8]):
        if ch.isdigit():
            v = int(ch)
        elif "A" <= ch <= "Z":
            v = ord(ch) - ord("A") + 10
        elif ch in "*@#":
            v = 36 + "*@#".index(ch)
        else:
            return False
        if i % 2:
            v *= 2
        total += v // 10 + v % 10
    return (10 - total % 10) % 10 == int(cusip[8])


class OpenFigiClient:
    def __init__(
        self,
        api_key: str = "",
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limits = WITH_KEY if api_key else WITHOUT_KEY
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["X-OPENFIGI-APIKEY"] = api_key
        self._client = httpx.Client(headers=headers, timeout=60.0, transport=transport)
        self._sleep, self._clock = sleep, clock
        self._sent: deque[float] = deque()

    def _wait_turn(self) -> None:
        """At most `requests_per_window` requests in any `window_seconds`."""
        window = self.limits.window_seconds
        now = self._clock()
        while self._sent and now - self._sent[0] >= window:
            self._sent.popleft()
        if len(self._sent) >= self.limits.requests_per_window:
            self._sleep(self._sent[0] + window - now + 0.05)
            now = self._clock()
            self._sent.popleft()
        self._sent.append(now)

    def map(self, jobs: list[dict]) -> list[dict]:
        """One mapping request, paced to OpenFIGI's published limits.

        A refusal (429) or a failure (a 5xx, a failed connection, an answer that is not
        JSON) raises OpenFigiUnavailable at once: nothing is retried or waited out, the
        caller turns to the next source, and its next request asks OpenFIGI again. Any
        other 4xx raises httpx.HTTPStatusError. Every answer goes to the source health file."""
        if len(jobs) > self.limits.jobs_per_request:
            raise ValueError(f"{len(jobs)} jobs; OpenFIGI takes {self.limits.jobs_per_request} per request")
        self._wait_turn()
        try:
            response = self._client.post(API, json=jobs)
        except httpx.TransportError as err:
            raise self._unavailable("failed", f"connection failed ({type(err).__name__})") from err
        status = response.status_code
        if status == 429:
            raise self._unavailable("throttled", "HTTP 429")
        if status >= 500:
            raise self._unavailable("failed", f"HTTP {status}")
        if status >= 400:
            health.record(SOURCE, "failed", f"HTTP {status}")
            response.raise_for_status()
        try:
            results = response.json()
        except ValueError as err:
            raise self._unavailable("failed", "an answer that is not JSON") from err
        health.record(SOURCE, "ok")
        if not isinstance(results, list) or len(results) != len(jobs):
            raise BatchError(f"OpenFIGI answered {json.dumps(results)[:200]} to {len(jobs)} jobs")
        return results

    @staticmethod
    def _unavailable(outcome: str, what: str) -> OpenFigiUnavailable:
        health.record(SOURCE, outcome, what)
        return OpenFigiUnavailable(what)

    def close(self) -> None:
        self._client.close()


def choose(listings: list[dict]) -> dict:
    """The US composite listing, else the first one."""
    return next((d for d in listings if d.get("exchCode") == "US"), listings[0])


def _literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, datetime):
        return f"TIMESTAMP '{value.isoformat(sep=' ')}'"
    return "'" + str(value).replace("'", "''") + "'"


def _store(con: duckdb.DuckDBPyConnection, rows: list[tuple]) -> None:
    """Insert or replace cache rows in one statement. OpenFIGI's answer replaces a
    provisional ticker from a fallback for the same CUSIP."""
    if not rows:
        return
    cusips = ", ".join(_literal(r[0]) for r in rows)
    con.execute(f"DELETE FROM openfigi WHERE cusip IN ({cusips})")
    values = ", ".join("(" + ", ".join(_literal(v) for v in row) + ")" for row in rows)
    con.execute(f"INSERT INTO openfigi VALUES {values}")
    con.execute(f"DELETE FROM ticker_fallbacks WHERE cusip IN ({cusips})")


def _row(cusip: str, job: dict, result: dict, fetched_at: datetime) -> tuple | None:
    """A cache row for one answer, or None for an error (asked again next run)."""
    if result.get("data"):
        d = choose(result["data"])
        return (
            cusip,
            job["idType"],
            job["idValue"],
            True,
            d.get("ticker"),
            d.get("name"),
            d.get("exchCode"),
            d.get("securityType"),
            d.get("securityType2"),
            d.get("marketSector"),
            d.get("figi"),
            d.get("compositeFIGI"),
            d.get("shareClassFIGI"),
            json.dumps(result, separators=(",", ":")),
            fetched_at,
        )
    if "warning" in result or "data" in result or result.get("error") == REJECTED:
        return (
            cusip,
            job["idType"],
            job["idValue"],
            False,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            json.dumps(result, separators=(",", ":")),
            fetched_at,
        )
    return None  # an error: not cached


def _ask(client: OpenFigiClient, batch: list[tuple[str, dict]]) -> list[tuple[tuple[str, dict], dict]]:
    """Each job with its answer. A batch OpenFIGI answers oddly is asked again in halves;
    every job of a batch it refuses or fails gets an UNANSWERED error."""
    try:
        return list(zip(batch, client.map([job for _, job in batch]), strict=True))
    except OpenFigiUnavailable as refused:
        return [(item, {"error": f"{UNANSWERED}: {refused}"}) for item in batch]
    except BatchError:
        if len(batch) == 1:
            return [(batch[0], {"error": "OpenFIGI could not answer this job"})]
        middle = len(batch) // 2
        return _ask(client, batch[:middle]) + _ask(client, batch[middle:])


def _batches(items: list, size: int) -> Iterable[list]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def pending_cusips(con: duckdb.DuckDBPyConnection) -> list[str]:
    """CUSIPs in the data that OpenFIGI has not been asked about."""
    con.execute(CACHE_DDL)
    return [
        r[0]
        for r in con.execute(
            """
            SELECT s.cusip FROM securities s
            ANTI JOIN openfigi o ON o.cusip = s.cusip
            ORDER BY s.latest_period DESC, s.cusip
            """
        ).fetchall()
    ]


# How far a CUSIP got, for the ones not found yet (the id_type of its cache row):
STAGE_INVALID = "INVALID_CUSIP"  # a wrong check digit: never sent
STAGE_ANY = "ANY_EXCHANGE"  # no listing with a share class on any exchange
STAGE_DONE = "FILER_FIGI_AS_SHARE_CLASS"  # every pass tried; nothing found


def cusip_job(cusip: str, us_only: bool = True) -> dict:
    """A lookup by CUSIP. Codes that start with a letter are CINS codes (foreign issuers)."""
    job = {"idType": "ID_CINS" if cusip[:1].isalpha() else "ID_CUSIP", "idValue": cusip}
    if us_only:
        job["exchCode"] = "US"
    return job


def _not_found(con: duckdb.DuckDBPyConnection, stages: tuple[str, ...], with_filer_figi: bool = False) -> list[tuple]:
    """Cached CUSIPs not found yet at the given stages, with the FIGI filers wrote."""
    marks = ", ".join(_literal(stage) for stage in stages)
    figi_rule = "AND s.figi LIKE 'BBG%' AND length(s.figi) = 12" if with_filer_figi else ""
    return con.execute(
        f"""
        SELECT o.cusip, s.figi FROM openfigi o
        JOIN securities s ON s.cusip = o.cusip
        WHERE NOT o.found AND o.id_type IN ({marks}) {figi_rule}
        ORDER BY s.latest_period DESC, o.cusip
        """
    ).fetchall()


def unanswered(result: dict) -> bool:
    """Whether OpenFIGI failed to answer a job (an error other than rejecting the identifier)."""
    return "error" in result and result["error"] != REJECTED


class _Run:
    """Asks OpenFIGI batch by batch and stores each batch's rows, counting as it goes.
    The CUSIPs of jobs OpenFIGI did not answer go to `fallback` at once."""

    def __init__(
        self, open_db: Callable, client: OpenFigiClient, log: Callable, fallback: Callable[[list[str]], None] | None
    ) -> None:
        self.open_db, self.client, self.log, self.fallback = open_db, client, log, fallback
        self.counts = {"asked": 0, "found": 0, "errors": 0, "refused_batches": 0}

    def ask_all(self, work: list[tuple[str, dict]], label: str, handle: Callable, report: bool = True) -> None:
        if not work:
            return
        limits = self.client.limits
        size = limits.jobs_per_request
        requests = -(-len(work) // size)
        minutes = requests / limits.requests_per_window * limits.window_seconds / 60
        self.log(f"  {label}: {len(work):,} to ask in {requests:,} requests (about {max(minutes, 0.1):.0f} min)")
        before = self.counts["found"]
        for n, batch in enumerate(_batches(work, size), start=1):
            answered = _ask(self.client, batch)
            self.counts["asked"] += len(batch)
            rows = handle(answered, datetime.now(UTC).replace(tzinfo=None))
            if rows:
                with self.open_db() as con:
                    _store(con, rows)
                self.counts["found"] += sum(1 for row in rows if row[3])
            self._fall_back(answered)
            if n % 50 == 0 and n < requests:
                self.log(f"    {n:,} of {requests:,} requests, {self.counts['found'] - before:,} found so far")
        if report:
            self.log(f"    {self.counts['found'] - before:,} found")

    def _fall_back(self, answered: list) -> None:
        refused = next((r["error"] for _, r in answered if str(r.get("error", "")).startswith(UNANSWERED)), None)
        if refused:
            if not self.counts["refused_batches"]:
                self.log(f"    {refused}. Its CUSIPs go to the next source, and the next request asks OpenFIGI again")
            self.counts["refused_batches"] += 1
        missed = sorted({cusip for (cusip, _), result in answered if unanswered(result)})
        if missed and self.fallback:
            self.fallback(missed)

    def answers(self, answered: list, fetched_at: datetime) -> list[tuple]:
        rows = []
        for (cusip, job), result in answered:
            row = _row(cusip, job, result, fetched_at)
            if row is None:
                self.counts["errors"] += 1  # a passing error: asked again next run
            else:
                rows.append(row)
        return rows


def _store_invalid(open_db: Callable, cusips: list[str], log: Callable) -> None:
    """Cache CUSIPs with a wrong check digit as not found, without sending them."""
    if not cusips:
        return
    fetched_at = datetime.now(UTC).replace(tzinfo=None)
    note = json.dumps({"error": "Not sent: the CUSIP's check digit is wrong."})
    with open_db() as con:
        for batch in _batches(cusips, 1000):
            _store(con, [(c, STAGE_INVALID, c, False) + (None,) * 9 + (note, fetched_at) for c in batch])
    log(f"  {len(cusips):,} CUSIPs have a wrong check digit (filers' typos and placeholders); not sent")


def update(
    open_db: Callable, client: OpenFigiClient, log=print, fallback: Callable[[list[str]], None] | None = None
) -> dict:
    """Look up every CUSIP not cached yet; see the module docstring for the passes.

    open_db() returns a DuckDB connection to use as a context manager. It is held
    only to read the work and to store each batch, never while waiting on
    OpenFIGI, so the app keeps working during a long run. Answers are stored batch
    by batch, so a run that stops picks up where it left off. fallback(cusips)
    gets the CUSIPs of every batch OpenFIGI did not answer, as soon as it fails."""
    run = _Run(open_db, client, log, fallback)
    counts, ask_all, answers = run.counts, run.ask_all, run.answers

    # Pass 1: CUSIPs never asked about, on the US composite listing.
    with open_db() as con:
        cusips = pending_cusips(con)
    _store_invalid(open_db, [c for c in cusips if not valid_cusip(c)], log)
    ask_all([(c, cusip_job(c)) for c in cusips if valid_cusip(c)], "CUSIPs on the US listing", answers)

    # Pass 2: the same CUSIPs on any exchange, then their share class on the US listing.
    with open_db() as con:
        unmatched = [c for c, _ in _not_found(con, ("ID_CUSIP", "ID_CINS"))]
    share_classes: list[tuple[str, dict]] = []

    def any_exchange(answered: list, fetched_at: datetime) -> list[tuple]:
        rows = []
        for (cusip, job), result in answered:
            listings = result.get("data") or []
            figi = next((d["shareClassFIGI"] for d in listings if d.get("shareClassFIGI")), None)
            if figi:
                share_classes.append(
                    (cusip, {"idType": "ID_BB_GLOBAL_SHARE_CLASS_LEVEL", "idValue": figi, "exchCode": "US"})
                )
            elif unanswered(result):
                counts["errors"] += 1
            else:
                response = json.dumps(result, separators=(",", ":"))
                rows.append((cusip, STAGE_ANY, job["idValue"], False) + (None,) * 9 + (response, fetched_at))
        return rows

    ask_all(
        [(c, cusip_job(c, us_only=False)) for c in unmatched],
        "unmatched CUSIPs on any exchange",
        any_exchange,
        report=False,
    )
    ask_all(share_classes, "their share classes on the US listing", answers)

    # Pass 3: the FIGI filers wrote, for what is still unmatched.
    with open_db() as con:
        figi_work = [
            (c, {"idType": "ID_BB_GLOBAL", "idValue": figi})
            for c, figi in _not_found(
                con, (STAGE_INVALID, STAGE_ANY, "ID_BB_GLOBAL_SHARE_CLASS_LEVEL"), with_filer_figi=True
            )
        ]
    ask_all(figi_work, "FIGIs filers wrote", answers)

    # Some filers write the share-class FIGI: try it on the US listing.
    with open_db() as con:
        class_work = [
            (c, {"idType": "ID_BB_GLOBAL_SHARE_CLASS_LEVEL", "idValue": figi, "exchCode": "US"})
            for c, figi in _not_found(con, ("ID_BB_GLOBAL",), with_filer_figi=True)
        ]

    def last_try(answered: list, fetched_at: datetime) -> list[tuple]:
        rows = answers(answered, fetched_at)
        return [row if row[3] else (row[0], STAGE_DONE, *row[2:]) for row in rows]

    ask_all(class_work, "filers' FIGIs as share classes on the US listing", last_try)
    return counts
