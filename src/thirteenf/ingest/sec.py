"""Find and download the SEC's Form 13F data set zips.

Links are read from the data sets page rather than built by hand: the folder
in the link has changed between releases.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urljoin

import httpx

from thirteenf.config import RAW_DIR, sec_user_agent

DATA_SETS_PAGE = "https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets"
# The first filing window this app loads. It holds the Q2 2024 filings.
FIRST_WINDOW_START = date(2024, 6, 1)
# The SEC asks for fewer than 10 requests per second; stay well under.
MIN_SECONDS_BETWEEN_REQUESTS = 0.25

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


class SecClient:
    def __init__(self) -> None:
        self._client = httpx.Client(
            headers={"User-Agent": sec_user_agent(), "Accept-Encoding": "gzip, deflate"},
            follow_redirects=True,
            timeout=httpx.Timeout(60.0, read=300.0),
        )
        self._last_request = 0.0

    def _wait_turn(self) -> None:
        pause = MIN_SECONDS_BETWEEN_REQUESTS - (time.monotonic() - self._last_request)
        if pause > 0:
            time.sleep(pause)
        self._last_request = time.monotonic()

    def get_text(self, url: str) -> str:
        self._wait_turn()
        response = self._client.get(url)
        response.raise_for_status()
        return response.text

    def download(self, url: str, dest: Path, log=print) -> None:
        """Stream to a .part file and rename when complete, so a stopped download never looks finished."""
        self._wait_turn()
        part = dest.with_suffix(dest.suffix + ".part")
        with self._client.stream("GET", url) as response:
            response.raise_for_status()
            total = int(response.headers.get("Content-Length", 0))
            done = 0
            next_report = 0.0
            with open(part, "wb") as out:
                for chunk in response.iter_bytes(1 << 20):
                    out.write(chunk)
                    done += len(chunk)
                    if total and done / total >= next_report:
                        log(f"  {dest.name}: {done / 1e6:,.0f} of {total / 1e6:,.0f} MB")
                        next_report += 0.25
        if total and part.stat().st_size != total:
            raise IOError(f"{dest.name}: got {part.stat().st_size} bytes, expected {total}")
        part.replace(dest)

    def close(self) -> None:
        self._client.close()


def wanted(data_sets: list[DataSet]) -> list[DataSet]:
    return [d for d in data_sets if d.start >= FIRST_WINDOW_START]


def download_all(log=print) -> list[Path]:
    """Download every wanted zip not already in data/raw/. Existing zips are never touched."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    client = SecClient()
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
                client.download(data_set.url, dest, log=log)
            paths.append(dest)
        return paths
    finally:
        client.close()
