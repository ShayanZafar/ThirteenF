"""Map CUSIPs to tickers with the OpenFIGI API, cached in DuckDB.

Every CUSIP in the data is looked up once, in up to three passes, each only for
the CUSIPs the pass before did not match:

1. the CUSIP on the US composite listing (a CINS code, for foreign issuers);
2. the CUSIP on any exchange, then its share class on the US composite listing;
3. the FIGI filers wrote in INFOTABLE, where there is one, as a FIGI and then
   as a share class on the US composite listing (some filers write that one).

Answers are kept in the `openfigi` table with OpenFIGI's response as returned,
so later runs only ask about new CUSIPs.
"""

from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable

import duckdb
import httpx

API = "https://api.openfigi.com/v3/mapping"


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
)
"""


class BatchError(RuntimeError):
    """OpenFIGI's answer did not line up with the jobs sent."""


# OpenFIGI's error for an identifier it rejects outright; asking again never helps.
REJECTED = "Invalid idValue format."


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
        """One mapping request. Waits and retries when OpenFIGI says to slow down."""
        if len(jobs) > self.limits.jobs_per_request:
            raise ValueError(f"{len(jobs)} jobs; OpenFIGI takes {self.limits.jobs_per_request} per request")
        for attempt in range(1, 7):
            self._wait_turn()
            response = self._client.post(API, json=jobs)
            if response.status_code == 429 or response.status_code >= 500:
                reset = float(response.headers.get("ratelimit-reset") or self.limits.window_seconds)
                self._sleep(max(reset, 1.0) * (1 if response.status_code == 429 else attempt))
                continue
            response.raise_for_status()
            results = response.json()
            if not isinstance(results, list) or len(results) != len(jobs):
                raise BatchError(f"OpenFIGI answered {json.dumps(results)[:200]} to {len(jobs)} jobs")
            return results
        raise RuntimeError("OpenFIGI kept refusing requests; try again later")

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
    """Insert or replace cache rows in one statement."""
    if not rows:
        return
    con.execute("DELETE FROM openfigi WHERE cusip IN (" + ", ".join(_literal(r[0]) for r in rows) + ")")
    values = ", ".join("(" + ", ".join(_literal(v) for v in row) + ")" for row in rows)
    con.execute(f"INSERT INTO openfigi VALUES {values}")


def _row(cusip: str, job: dict, result: dict, fetched_at: datetime) -> tuple | None:
    """A cache row for one answer, or None for an error (asked again next run)."""
    if "data" in result and result["data"]:
        d = choose(result["data"])
        return (
            cusip, job["idType"], job["idValue"], True,
            d.get("ticker"), d.get("name"), d.get("exchCode"), d.get("securityType"),
            d.get("securityType2"), d.get("marketSector"), d.get("figi"), d.get("compositeFIGI"),
            d.get("shareClassFIGI"), json.dumps(result, separators=(",", ":")), fetched_at,
        )
    if "warning" in result or "data" in result or result.get("error") == REJECTED:
        return (
            cusip, job["idType"], job["idValue"], False,
            None, None, None, None, None, None, None, None, None,
            json.dumps(result, separators=(",", ":")), fetched_at,
        )
    return None  # an error: not cached


def _ask(client: OpenFigiClient, batch: list[tuple[str, dict]]) -> list[tuple[tuple[str, dict], dict]]:
    """Each job with its answer. A batch OpenFIGI answers oddly is asked again in halves."""
    try:
        return list(zip(batch, client.map([job for _, job in batch])))
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


def update(open_db: Callable, client: OpenFigiClient, log=print) -> dict:
    """Look up every CUSIP not cached yet; see the module docstring for the passes.

    open_db() returns a DuckDB connection to use as a context manager. It is held
    only to read the work and to store each batch, never while waiting on
    OpenFIGI, so the app keeps working during a long run. Answers are stored batch
    by batch, so a run that stops picks up where it left off."""
    counts = {"asked": 0, "found": 0, "errors": 0}
    size = client.limits.jobs_per_request

    def ask_all(work: list[tuple[str, dict]], label: str, handle: Callable, report: bool = True) -> None:
        if not work:
            return
        requests = -(-len(work) // size)
        minutes = requests / client.limits.requests_per_window * client.limits.window_seconds / 60
        log(f"  {label}: {len(work):,} to ask in {requests:,} requests (about {max(minutes, 0.1):.0f} min)")
        before = counts["found"]
        for n, batch in enumerate(_batches(work, size), start=1):
            answered = _ask(client, batch)
            counts["asked"] += len(batch)
            rows = handle(answered, datetime.now(timezone.utc).replace(tzinfo=None))
            if rows:
                with open_db() as con:
                    _store(con, rows)
                counts["found"] += sum(1 for row in rows if row[3])
            if n % 50 == 0 and n < requests:
                log(f"    {n:,} of {requests:,} requests, {counts['found'] - before:,} found so far")
        if report:
            log(f"    {counts['found'] - before:,} found")

    def answers(answered: list, fetched_at: datetime) -> list[tuple]:
        rows = []
        for (cusip, job), result in answered:
            row = _row(cusip, job, result, fetched_at)
            if row is None:
                counts["errors"] += 1  # a passing error: asked again next run
            else:
                rows.append(row)
        return rows

    # Pass 1: CUSIPs never asked about, on the US composite listing.
    with open_db() as con:
        cusips = pending_cusips(con)
    invalid = [c for c in cusips if not valid_cusip(c)]
    if invalid:
        fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
        note = json.dumps({"error": "Not sent: the CUSIP's check digit is wrong."})
        with open_db() as con:
            for batch in _batches(invalid, 1000):
                _store(con, [(c, STAGE_INVALID, c, False) + (None,) * 9 + (note, fetched_at) for c in batch])
        log(f"  {len(invalid):,} CUSIPs have a wrong check digit (filers' typos and placeholders); not sent")
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
            elif "error" in result and result["error"] != REJECTED:
                counts["errors"] += 1
            else:
                response = json.dumps(result, separators=(",", ":"))
                rows.append((cusip, STAGE_ANY, job["idValue"], False) + (None,) * 9 + (response, fetched_at))
        return rows

    ask_all([(c, cusip_job(c, us_only=False)) for c in unmatched], "unmatched CUSIPs on any exchange",
            any_exchange, report=False)
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
        return [row if row[3] else (row[0], STAGE_DONE) + row[2:] for row in rows]

    ask_all(class_work, "filers' FIGIs as share classes on the US listing", last_try)
    return counts
