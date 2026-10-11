"""Find and download the SEC's Form 13F data set zips, through the client every SEC download uses.

Links are read from the data sets page rather than built by hand: the folder
in the link has changed between releases.

SecClient waits only where nothing else can answer (the owner's rules, Oct 11, 2026):

- Requests are paced just under the SEC's published limit of 10 a second, for
  every caller: going over it gets the computer blocked.
- For a caller with no other source (the 13F data sets, the XBRL frames), a failed
  connection (a DNS blip, a dropped connection, a timeout) or a 5xx is asked again
  after about 1, 2 and 4 seconds, MAX_ATTEMPTS tries in all, then a RuntimeError
  says what to do. A block, a 429 or the 403 page the SEC serves when it pauses a
  client ("Request Rate Threshold", "Undeclared Automated Tool"), is waited out:
  as long as Retry-After says, else BLOCK_SECONDS, the 10 minutes the SEC
  documents, at most MAX_BLOCK_WAITS times per client, which is per run, then the
  RuntimeError.
- A caller with another source for the same data (the fails-to-deliver files, a
  ticker fallback) passes has_fallback=True: a block raises SecBlocked and a
  failure SecUnavailable at once, nothing is retried or waited out, and the
  caller turns to its next source.
- A 404 or any other 4xx is not retried: it raises httpx.HTTPStatusError, which
  the XBRL download relies on.

Every answer is recorded in the source health file (thirteenf.health) under the
caller's source name.
"""

from __future__ import annotations

import math
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

from thirteenf import health
from thirteenf.config import RAW_DIR, sec_user_agent

DATA_SETS_PAGE = "https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets"
# The first filing window this app loads. It holds the Q2 2024 filings.
FIRST_WINDOW_START = date(2024, 6, 1)
# The SEC publishes a limit of 10 requests per second; stay just under it.
MIN_SECONDS_BETWEEN_REQUESTS = 0.11
# A failed connection or a 5xx: tries in all, and the first wait (it doubles: 1, 2, 4 s),
# each plus up to RETRY_JITTER seconds.
MAX_ATTEMPTS = 4
RETRY_BASE = 1.0
RETRY_JITTER = 0.5
# A block: how long the SEC documents it lasts, how many to wait out in one run, and
# the most a Retry-After header is trusted for.
BLOCK_SECONDS = 600.0
MAX_BLOCK_WAITS = 2
MAX_RETRY_AFTER = 3600.0
# What the SEC's block page says (an HTTP 403; any other 403 is final).
THROTTLE_PHRASES = ("Request Rate Threshold", "Undeclared Automated Tool")
SOURCE = "sec"  # in the source health file: the SEC's 13F data sets

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


def _refused(response: httpx.Response) -> bool:
    """Whether the SEC failed (5xx) or paused us (429, its block page): worth another try.

    A failed connection is always worth another; the callers catch that themselves."""
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


class _Retry(Exception):
    """One attempt failed in a way worth another try."""

    def __init__(self, what: str, retry_after: float | None = None) -> None:
        super().__init__(what)
        self.what = what  # "HTTP 503", "connection failed (ConnectError)", "HTTP 403"
        self.retry_after = retry_after


class _Failed(_Retry):
    """A failed connection or a 5xx: asked again within seconds."""


class _Blocked(_Retry):
    """A 429 or the SEC's block page: it has paused requests from this computer."""


def _failure(outcome: httpx.Response | httpx.TransportError) -> _Retry:
    if isinstance(outcome, httpx.TransportError):
        return _Failed(f"connection failed ({type(outcome).__name__})")
    if outcome.status_code >= 500:
        return _Failed(f"HTTP {outcome.status_code}")
    return _Blocked(f"HTTP {outcome.status_code}", _retry_after_seconds(outcome))


class SecUnavailable(RuntimeError):
    """The SEC failed to answer a caller that has another source to turn to (has_fallback=True)."""


class SecBlocked(SecUnavailable):
    """The SEC paused requests from this computer, and the caller has another source to turn to."""


def _failed_message(attempts: int, failure: _Retry) -> str:
    return (
        f"The SEC failed to answer {attempts} times (last: {failure.what}). "
        "Check your connection and run the update again; it carries on from the finished downloads."
    )


def _blocked_message(blocks: int, block: _Retry) -> str:
    return (
        f"The SEC paused requests from this computer {blocks} times in this run (last: {block.what}). "
        "Run the update again later; it carries on from the finished downloads. "
        "If this keeps happening, check SEC_USER_AGENT."
    )


def _duration(seconds: float) -> str:
    """10 minutes, 1 minute, 45 seconds."""
    if seconds >= 60:
        minutes = math.ceil(seconds / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    whole = math.ceil(seconds)
    return f"{whole} second{'s' if whole != 1 else ''}"


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
        self.blocks_waited = 0  # blocks waited out so far; a run shares one client

    def _wait_turn(self) -> None:
        if self._last_request is not None:
            pause = MIN_SECONDS_BETWEEN_REQUESTS - (self._clock() - self._last_request)
            if pause > 0:
                self._sleep(pause)
        self._last_request = self._clock()

    def _request[T](
        self, attempt_once: Callable[[], T], source: str, has_fallback: bool, missing_ok: bool = False
    ) -> T:
        """Call attempt_once until it returns, waiting only as the module docstring says.

        attempt_once raises _Failed or _Blocked for a failure worth another try; anything
        else propagates at once. Each answer goes to the source health file."""
        failures = 0
        while True:
            self._wait_turn()
            try:
                result = attempt_once()
            except _Blocked as block:
                health.record(source, "throttled", f"paused requests ({block.what})")
                if has_fallback:
                    raise SecBlocked(f"The SEC paused requests from this computer ({block.what})") from None
                self._wait_out(block)
                continue
            except _Failed as failure:
                health.record(source, "failed", failure.what)
                if has_fallback:
                    raise SecUnavailable(f"The SEC failed to answer ({failure.what})") from failure.__cause__
                failures += 1
                if failures == MAX_ATTEMPTS:
                    raise RuntimeError(_failed_message(failures, failure)) from failure.__cause__
                self._pause(failure, failures)
                continue
            except httpx.HTTPStatusError as err:
                # A 404 is an answer where the caller expects some (a frame nobody has reported yet).
                missing = missing_ok and err.response.status_code == 404
                health.record(source, "ok" if missing else "failed", f"HTTP {err.response.status_code}")
                raise
            health.record(source, "ok")
            return result

    def _wait_out(self, block: _Retry) -> None:
        """Wait as long as the SEC said (else BLOCK_SECONDS), at most MAX_BLOCK_WAITS times per client."""
        if self.blocks_waited == MAX_BLOCK_WAITS:
            raise RuntimeError(_blocked_message(self.blocks_waited + 1, block))
        self.blocks_waited += 1
        seconds = BLOCK_SECONDS if block.retry_after is None else block.retry_after
        self._log(
            f"SEC paused requests from this computer; waiting {_duration(seconds)}, then carrying on (Ctrl+C stops)"
        )
        self._sleep(seconds)

    def _pause(self, failure: _Retry, failures: int) -> None:
        """A short wait before the next try: 1, 2, 4 seconds, each plus up to RETRY_JITTER of jitter."""
        pause = RETRY_BASE * 2 ** (failures - 1) + random.uniform(0, RETRY_JITTER)
        self._log(f"  SEC: {failure.what}, asking again in {pause:.0f} s (attempt {failures + 1} of {MAX_ATTEMPTS})")
        self._sleep(pause)

    def get_text(self, url: str, *, source: str = SOURCE, has_fallback: bool = False, missing_ok: bool = False) -> str:
        """The page's text. source names the data in the health file; has_fallback and the
        rest of the policy are in the module docstring. missing_ok counts a 404 as an answer."""

        def once() -> str:
            try:
                response = self._client.get(url)
            except httpx.TransportError as err:
                raise _failure(err) from err
            if _refused(response):
                raise _failure(response)
            response.raise_for_status()
            return response.text

        return self._request(once, source, has_fallback, missing_ok)

    def download(self, url: str, dest: Path, *, source: str = SOURCE, has_fallback: bool = False) -> None:
        """Stream to a .part file and rename when complete, so a stopped download never looks finished.

        A failure before or during the body deletes the .part file; the next try (none with
        has_fallback) downloads the whole file again."""
        part = dest.with_suffix(dest.suffix + ".part")

        def once() -> int:
            try:
                with self._client.stream("GET", url) as response:
                    if _refused(response):
                        raise _failure(response)
                    response.raise_for_status()
                    return self._save(response, part, dest.name)
            except httpx.TransportError as err:
                part.unlink(missing_ok=True)
                raise _failure(err) from err

        total = self._request(once, source, has_fallback)
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


def download_all(log=print, client: SecClient | None = None) -> list[Path]:
    """Download every wanted zip not already in data/raw/. Existing zips are never touched.

    A run passes its one client to every SEC download, so pacing and the block limit cover them all."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    own = client is None
    sec = client or SecClient(log=log)
    try:
        data_sets = wanted(parse_data_sets(sec.get_text(DATA_SETS_PAGE)))
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
                sec.download(data_set.url, dest)
            paths.append(dest)
        return paths
    finally:
        if own:
            sec.close()
