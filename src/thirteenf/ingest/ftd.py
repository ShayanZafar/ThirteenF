"""The SEC's fails-to-deliver data: the fallback for a CUSIP's ticker when OpenFIGI cannot answer.

Twice a month the SEC publishes every security with fails to deliver outstanding on
each settlement day, with its CUSIP and trading symbol:
https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data. Each
cnsfailsYYYYMM[ab].zip ("a" the first half of the month, "b" the second) holds one
cnsfailsYYYYMM[ab].txt: latin-1, pipe-delimited, the header
SETTLEMENT DATE|CUSIP|SYMBOL|QUANTITY (FAILS)|DESCRIPTION|PRICE, about 58,000 rows,
and two trailer lines, "Trailer record count N" and "Trailer total quantity of shares N".

Links are read from the page, as for the 13F data sets. The folders in them vary
(older files sit under /files/node/add/data_distribution/), so files are ordered by
the year, month and half in their names, never by path.

The files are fetched only when a ticker run first needs the fallback, and then
only the newest MONTHS months' files not already in data/raw/ftd/, where they are
kept as downloaded. Every request goes through SecClient with has_fallback=True: a
block or a failure stops the fetching at once, and the files already there still
answer. Each file is loaded into raw_ftd as text, as in the file, trailer lines
included, after two checks: the header is the one above, and the rows match the
file's own record count. A CUSIP's ticker is the SYMBOL on its most recent
settlement date.
"""

from __future__ import annotations

import re
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import duckdb

from thirteenf.config import RAW_DIR
from thirteenf.db import scalar
from thirteenf.ingest.sec import SecClient

FTD_PAGE = "https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data"
FTD_DIR = RAW_DIR / "ftd"
SOURCE = "sec-ftd"  # in the source health file: the fallback for tickers
# How many months of files to fetch, newest first: a year and a month.
MONTHS = 13
HEADER = "SETTLEMENT DATE|CUSIP|SYMBOL|QUANTITY (FAILS)|DESCRIPTION|PRICE"
FILE_NAME = re.compile(r"cnsfails(\d{4})(\d{2})([ab])\.zip", re.I)
TRAILER = "Trailer"
RECORD_COUNT = re.compile(r"Trailer record count\s+(\d+)", re.I)

RAW_DDL = """
CREATE TABLE IF NOT EXISTS raw_ftd (
    settlement_date VARCHAR, cusip VARCHAR, symbol VARCHAR, quantity VARCHAR,
    description VARCHAR, price VARCHAR, source_file VARCHAR
)
"""
_COLUMNS = (
    "{'settlement_date': 'VARCHAR', 'cusip': 'VARCHAR', 'symbol': 'VARCHAR', "
    "'quantity': 'VARCHAR', 'description': 'VARCHAR', 'price': 'VARCHAR'}"
)


class NoLinks(RuntimeError):
    """The page links no fails-to-deliver files: it has changed."""


@dataclass(frozen=True)
class FtdFile:
    name: str
    url: str
    month: str  # YYYYMM
    half: str  # a: the first half of the month, b: the second


def parse_links(html: str, base_url: str = FTD_PAGE) -> list[FtdFile]:
    """Every cnsfails zip linked from the page, oldest first by the date in its name."""
    found: dict[str, FtdFile] = {}
    for href in re.findall(r"""href=["']([^"']+?\.zip)["']""", html, re.I):
        name = href.rsplit("/", 1)[-1]
        match = FILE_NAME.fullmatch(name)
        if match:
            year, month, half = match.groups()
            found[name.lower()] = FtdFile(name, urljoin(base_url, href), year + month, half.lower())
    return sorted(found.values(), key=lambda f: (f.month, f.half))


def newest(files: list[FtdFile], months: int = MONTHS) -> list[FtdFile]:
    """The files of the `months` calendar months up to the newest one listed, oldest first."""
    if not files:
        return []
    last = max(f.month for f in files)
    first = int(last[:4]) * 12 + int(last[4:]) - months  # months since year 0, counting from 0
    start = f"{first // 12:04d}{first % 12 + 1:02d}"
    return [f for f in files if f.month >= start]


def download_new(client: SecClient, log: Callable[[str], None] = print, folder: Path | None = None) -> int:
    """Download the newest MONTHS months' files not already in `folder`. Returns how many.

    Raises SecUnavailable at once when the SEC blocks or fails (the caller has another
    source), httpx.HTTPStatusError when it refuses a request, and NoLinks when the
    page lists no files."""
    folder = folder or FTD_DIR
    folder.mkdir(parents=True, exist_ok=True)
    files = newest(parse_links(client.get_text(FTD_PAGE, source=SOURCE, has_fallback=True)))
    if not files:
        raise NoLinks(f"No fails-to-deliver files are linked from {FTD_PAGE}")
    missing = [f for f in files if not (folder / f.name).exists()]
    for f in missing:
        log(f"    {f.name}: downloading")
        client.download(f.url, folder / f.name, source=SOURCE, has_fallback=True)
    return len(missing)


def _read_csv(path: Path) -> str:
    # quote='' and escape='': fields are taken byte for byte; null_padding keeps the
    # one-field trailer lines; strict mode refuses any other line that is not six fields.
    quoted = path.as_posix().replace("'", "''")  # a temporary folder under a name such as O'Brien
    return (
        f"read_csv('{quoted}', delim='|', header=true, quote='', escape='', columns={_COLUMNS}, "
        "encoding='latin-1', null_padding=true, auto_detect=false)"
    )


def _read_text(path: Path) -> tuple[str, int, int | None]:
    """The header, the lines after it (blank ones aside, as the CSV reader skips them),
    and the record count its trailer gives, if it has one."""
    with open(path, encoding="latin-1", newline="") as f:
        header = f.readline().strip()
        lines, counted = 0, None
        for line in f:
            if line.strip():
                lines += 1
                match = RECORD_COUNT.fullmatch(line.strip())
                if match:
                    counted = int(match.group(1))
    return header, lines, counted


def load_file(con: duckdb.DuckDBPyConnection, path: Path) -> int:
    """Load one zip into raw_ftd, replacing any rows it had. Returns the data rows.

    Raises ValueError, and loads nothing, when the file does not read as the module
    docstring says: one .txt inside, the documented header, every line read, and as
    many data rows as its trailer counts."""
    con.execute(RAW_DDL)
    with tempfile.TemporaryDirectory(prefix="thirteenf-ftd-", ignore_cleanup_errors=True) as work:
        with zipfile.ZipFile(path) as archive:
            members = [n for n in archive.namelist() if n.lower().endswith(".txt")]
            if len(members) != 1:
                raise ValueError(f"expected one .txt file inside, found {len(members)}")
            text_path = Path(archive.extract(members[0], work))
        header, lines, counted = _read_text(text_path)
        if header != HEADER:
            raise ValueError(f"unexpected header {header[:80]!r}")
        con.execute("BEGIN TRANSACTION")
        try:
            con.execute("DELETE FROM raw_ftd WHERE source_file = ?", [path.name])
            con.execute(f"INSERT INTO raw_ftd SELECT *, ? FROM {_read_csv(text_path)}", [path.name])
            rows = scalar(con, "SELECT count(*) FROM raw_ftd WHERE source_file = ?", [path.name])
            if rows != lines:
                raise ValueError(f"loaded {rows:,} lines but the file has {lines:,}")
            data_rows = scalar(
                con,
                f"""
                SELECT count(*) FROM raw_ftd
                WHERE source_file = ? AND NOT coalesce(starts_with(settlement_date, '{TRAILER}'), false)
                """,
                [path.name],
            )
            if counted is not None and counted != data_rows:
                raise ValueError(f"{data_rows:,} rows, but its trailer counts {counted:,}")
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
    return data_rows


def load_new(con: duckdb.DuckDBPyConnection, folder: Path | None = None, log: Callable[[str], None] = print) -> int:
    """Load the zips in `folder` that raw_ftd does not hold yet. Returns how many were loaded.

    A file that does not read as documented is left out, with a line saying why; the
    others still answer."""
    folder = folder or FTD_DIR
    con.execute(RAW_DDL)
    loaded = {r[0] for r in con.execute("SELECT DISTINCT source_file FROM raw_ftd").fetchall()}
    count = 0
    for path in sorted(folder.glob("*.zip")) if folder.exists() else []:
        if path.name in loaded or not FILE_NAME.fullmatch(path.name):
            continue
        try:
            rows = load_file(con, path)
        except (ValueError, zipfile.BadZipFile, duckdb.Error) as err:
            log(f"    {path.name}: not loaded ({str(err).splitlines()[0]})")
            continue
        log(f"    {path.name}: {rows:,} rows")
        count += 1
    return count


def latest_symbols(con: duckdb.DuckDBPyConnection) -> dict[str, tuple[str, date]]:
    """Every CUSIP in raw_ftd with the SYMBOL on its most recent settlement date, and that date."""
    con.execute(RAW_DDL)
    rows = con.execute(
        """
        SELECT DISTINCT ON (cusip) cusip, symbol, as_of FROM (
            SELECT upper(trim(cusip)) AS cusip, trim(symbol) AS symbol,
                   try_strptime(settlement_date, '%Y%m%d')::DATE AS as_of
            FROM raw_ftd
            WHERE nullif(trim(symbol), '') IS NOT NULL AND nullif(trim(cusip), '') IS NOT NULL
        )
        WHERE as_of IS NOT NULL
        ORDER BY cusip, as_of DESC, symbol
        """
    ).fetchall()
    return {cusip: (symbol, as_of) for cusip, symbol, as_of in rows}
