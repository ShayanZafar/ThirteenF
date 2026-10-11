"""Find and download the SEC's Form 13F data set zips.

Links are read from the data sets page rather than built by hand: the folder
in the link has changed between releases.

SecClient asks again when the SEC does not answer: a connection that fails (a
DNS blip, a dropped connection, a timeout), a 429 or 5xx, or the 403 page the
SEC serves when it throttles a client (it then blocks for about 10 minutes). It
waits as long as the Retry-After header says, else 2, 4, 8... seconds, up to
MAX_ATTEMPTS tries and MAX_TOTAL_WAIT seconds of waiting, then gives up with a
RuntimeError that says what to do. A 404 or any other 4xx is not retried: it
raises httpx.HTTPStatusError as before, which the XBRL download relies on.
"""

from __future__ import annotations

import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin

import httpx

from thirteenf.config import RAW_DIR, sec_user_agent

DATA_SETS_PAGE = "https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets"
# The first filing window this app loads. It holds the Q2 2024 filings.
FIRST_WINDOW_START = date(2024, 6, 1)
# The SEC asks for fewer than 10 requests per second; stay well under.
MIN_SECONDS_BETWEEN_REQUESTS = 0.25
# The retry policy: how many times to ask in all, the most to wait between two
# tries without a Retry-After header, the most a Retry-After header is trusted
# for, and the waiting after which the next failure is the last.
MAX_ATTEMPTS = 5
MAX_BACKOFF = 60.0
MAX_RETRY_AFTER = 300.0
MAX_TOTAL_WAIT = 180.0
# What the SEC's throttling page says (an HTTP 403; any other 403 is final).
THROTTLE_PHRASES = ("Request Rate Threshold", "Undeclared Automated Tool")

WINDOW_NAME = re.compile(r"(\d{2}[a-z]{3}\d{4})-(\d{2}[a-z]{3}\d{4})_form13f\.zip$", re.I)


@dataclass(frozen=True)
class DataSet:
    name: str
    url: str
    start: date
    end: date


def _parse_day(text: str) -> date:
    return datetime.strptime(text.lower(), "%d%b%Y").date()


def parse_data_sets(html: str, base_url: str = DATA_SETS_PAGE) -> list[DataSet]:
    """Every three-month filing window linked from the page, oldest first."""
    found: dict[str, DataSet] = {}
    for href in re.findall(r'href="([^"]+?_form13f\.zip)"', html, re.I):
        name = href.rsplit("/", 1)[-1]
        match = WINDOW_NAME.search(name)
        if not match:
            continue  # quarter-named zips (2023q4_form13f.zip) predate this app
        found[name] = DataSet(
            name=name,
            url=urljoin(base_url, href),
            start=_parse_day(match.group(1)),
            end=_parse_day(match.group(2)),
        )
    return sorted(found.values(), key=lambda d: d.start)


def _should_retry(response: httpx.Response) -> bool:
    """Whether to ask again: the SEC was busy (429, 5xx) or it throttled us (its 403 page).

    A failed connection is always asked again; the callers catch that themselves."""
    status = response.status_code
    if status == 429 or status >= 500:
        return True
    if status != 403:
        return False
    response.read()  # a streaming download has not read the body yet
    body = response.text.casefold()
    return any(phrase.casefold() in body for phrase in THROTTLE_PHRASES)


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """The Retry-After header as seconds from now, clamped to 0..MAX_RETRY_AFTER; None when absent or unreadable."""
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        seconds = float(int(value))
    except ValueError:
        try:
            when = parsedate_to_datetime(value)
        except ValueError:
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        seconds = (when - datetime.now(UTC)).total_seconds()
    return min(max(seconds, 0.0), MAX_RETRY_AFTER)


class _TryAgain(Exception):
    """One attempt failed in a way worth another try."""

    def __init__(self, what: str, retry_after: float | None = None) -> None:
        super().__init__(what)
        self.what = what  # "throttled (HTTP 403)", "HTTP 503", "connection failed (ConnectError)"
        self.retry_after = retry_after

    @classmethod
    def after(cls, outcome: httpx.Response | httpx.TransportError) -> _TryAgain:
        if isinstance(outcome, httpx.TransportError):
            return cls(f"connection failed ({type(outcome).__name__})")
        status = outcome.status_code
        what = f"throttled (HTTP {status})" if status in (403, 429) else f"HTTP {status}"
        return cls(what, _retry_after_seconds(outcome))


def _gave_up(attempts: int, failure: _TryAgain) -> str:
    return (
        f"The SEC refused or failed to answer {attempts} times (last: {failure.what}). "
        "It throttles for about 10 minutes; run the update again later. "
        "If this keeps happening, check SEC_USER_AGENT."
    )


class SecClient:
    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        log: Callable[[str], None] = print,
    ) -> None:
        self._client = httpx.Client(
            headers={"User-Agent": sec_user_agent(), "Accept-Encoding": "gzip, deflate"},
            follow_redirects=True,
            timeout=httpx.Timeout(60.0, read=300.0),
            transport=transport,
        )
        self._sleep, self._clock, self._log = sleep, clock, log
        self._last_request: float | None = None

    def _wait_turn(self) -> None:
        if self._last_request is not None:
            pause = MIN_SECONDS_BETWEEN_REQUESTS - (self._clock() - self._last_request)
            if pause > 0:
                self._sleep(pause)
        self._last_request = self._clock()

    def _retrying[T](self, attempt_once: Callable[[], T]) -> T:
        """Call attempt_once until it returns, waiting between tries (the policy is in the module docstring).

        attempt_once raises _TryAgain for a failure worth another try; anything else propagates at once."""
        attempt, waited = 0, 0.0
        while True:
            attempt += 1
            self._wait_turn()
            try:
                return attempt_once()
            except _TryAgain as failure:
                if attempt == MAX_ATTEMPTS or waited > MAX_TOTAL_WAIT:
                    raise RuntimeError(_gave_up(attempt, failure)) from failure.__cause__
                waited += self._pause(failure, attempt)

    def _pause(self, failure: _TryAgain, attempt: int) -> float:
        """Wait before the next try: as long as the SEC said, else 2, 4, 8... seconds plus up to 1 s of jitter."""
        pause = failure.retry_after
        if pause is None:
            pause = min(MAX_BACKOFF, 2.0**attempt) + random.random()
        self._log(f"  SEC: {failure.what}, waiting {pause:.0f} s (attempt {attempt + 1} of {MAX_ATTEMPTS})")
        self._sleep(pause)
        return pause

    def get_text(self, url: str) -> str:
        def once() -> str:
            try:
                response = self._client.get(url)
            except httpx.TransportError as err:
                raise _TryAgain.after(err) from err
            if _should_retry(response):
                raise _TryAgain.after(response)
            response.raise_for_status()
            return response.text

        return self._retrying(once)

    def download(self, url: str, dest: Path) -> None:
        """Stream to a .part file and rename when complete, so a stopped download never looks finished.

        A failure before or during the body deletes the .part file and downloads the whole file again."""
        part = dest.with_suffix(dest.suffix + ".part")

        def once() -> int:
            try:
                with self._client.stream("GET", url) as response:
                    if _should_retry(response):
                        raise _TryAgain.after(response)
                    response.raise_for_status()
                    return self._save(response, part, dest.name)
            except httpx.TransportError as err:
                part.unlink(missing_ok=True)
                raise _TryAgain.after(err) from err

        total = self._retrying(once)
        if total and part.stat().st_size != total:
            raise OSError(f"{dest.name}: got {part.stat().st_size} bytes, expected {total}")
        part.replace(dest)

    def _save(self, response: httpx.Response, part: Path, name: str) -> int:
        """Write the body to the .part file, reporting progress. Returns the Content-Length (0 when not sent)."""
        total = int(response.headers.get("Content-Length", 0))
        done = 0
        next_report = 0.0
        with open(part, "wb") as out:
            for chunk in response.iter_bytes(1 << 20):
                out.write(chunk)
                done += len(chunk)
                if total and done / total >= next_report:
                    self._log(f"  {name}: {done / 1e6:,.0f} of {total / 1e6:,.0f} MB")
                    next_report += 0.25
        return total

    def close(self) -> None:
        self._client.close()


def wanted(data_sets: list[DataSet]) -> list[DataSet]:
    return [d for d in data_sets if d.start >= FIRST_WINDOW_START]


def download_all(log=print) -> list[Path]:
    """Download every wanted zip not already in data/raw/. Existing zips are never touched."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    client = SecClient(log=log)
    try:
        data_sets = wanted(parse_data_sets(client.get_text(DATA_SETS_PAGE)))
        if not data_sets:
            raise RuntimeError(f"No 13F data set links found on {DATA_SETS_PAGE}")
        log(f"{len(data_sets)} filing windows from {data_sets[0].name} to {data_sets[-1].name}")
        paths = []
        for data_set in data_sets:
            dest = RAW_DIR / data_set.name
            if dest.exists():
                log(f"  {data_set.name}: already downloaded")
            else:
                log(f"  {data_set.name}: downloading from {data_set.url}")
                client.download(data_set.url, dest)
            paths.append(dest)
        return paths
    finally:
        client.close()
