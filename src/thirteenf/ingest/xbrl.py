"""Download and load the SEC's company financial data (XBRL frames) for cash flow.

Each frame is one financial-statement line for every company in one calendar
period, as reported in 10-K and 10-Q filings: https://www.sec.gov/search-filings/edgar-application-programming-interfaces.
A few frames cover every company, so a full refresh is about 60 requests.
The files are kept in data/raw/xbrl/ as downloaded and loaded as they are;
the model (thirteenf.model.build) derives free cash flow from them.

company_tickers.json maps the SEC's company numbers (CIK) to tickers, which is
how a company's financials meet its stock in the 13F data.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import duckdb
import httpx

from thirteenf.config import RAW_DIR
from thirteenf.db import scalar

if TYPE_CHECKING:
    from thirteenf.ingest.sec import SecClient

XBRL_DIR = RAW_DIR / "xbrl"
FRAMES_URL = "https://data.sec.gov/api/xbrl/frames/{taxonomy}/{tag}/{unit}/{period}.json"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
TICKERS_FILE = "company_tickers.json"
# The first fiscal year read. Frames name a fiscal year by the calendar year it
# mostly falls in, so CY2025 holds Apple's year to September 2025 and
# Microsoft's to June 2025. Starting in 2023 gives every company two full years.
FIRST_YEAR = 2023

# Annual lines: (measure, taxonomy, tag, unit). Within a measure the first tag a
# company reports wins: most report capital spending as purchases of property,
# plant and equipment, some (Amazon, Nvidia) as productive assets.
ANNUAL_CONCEPTS = [
    ("operating_cash_flow", "us-gaap", "NetCashProvidedByUsedInOperatingActivities", "USD"),
    ("operating_cash_flow", "us-gaap", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations", "USD"),
    ("capex", "us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment", "USD"),
    ("capex", "us-gaap", "PaymentsToAcquireProductiveAssets", "USD"),
    ("diluted_shares", "us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding", "shares"),
    ("diluted_shares", "us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic", "shares"),
    # Banks and insurers: their operating cash flow carries deposits, loans and
    # premiums, so free cash flow does not measure what it measures elsewhere.
    ("financial", "us-gaap", "InterestAndDividendIncomeOperating", "USD"),
    ("financial", "us-gaap", "PremiumsEarnedNet", "USD"),
    # Lenders such as consumer finance companies report none of those lines, yet
    # their operating cash flow collects loan interest while the loans they make
    # sit in investing. A company whose loan interest and fees are a large part of
    # its revenue is treated the same way (thirteenf.model.build.LENDER_SHARE).
    ("loan_income", "us-gaap", "InterestAndFeeIncomeLoansAndLeases", "USD"),
    ("loan_income", "us-gaap", "InterestAndFeeIncomeLoansConsumer", "USD"),
    ("revenue", "us-gaap", "Revenues", "USD"),
    ("revenue", "us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax", "USD"),
]
# Point-in-time lines, read for recent quarter ends. Shares outstanding from each
# filing's cover page check the diluted share count: a split since the fiscal
# year end changes one, not the other.
INSTANT_CONCEPTS = [
    ("shares_outstanding", "dei", "EntityCommonStockSharesOutstanding", "shares"),
    ("financial", "us-gaap", "Deposits", "USD"),
]
# How many recent quarter ends to read them for.
INSTANT_QUARTERS = 5

RAW_DDL = """
CREATE TABLE IF NOT EXISTS raw_xbrl_frames (
    source_file VARCHAR, taxonomy VARCHAR, tag VARCHAR, unit VARCHAR, frame VARCHAR,
    accn VARCHAR, cik BIGINT, entity_name VARCHAR, loc VARCHAR,
    period_start DATE, period_end DATE, val DOUBLE
);
CREATE TABLE IF NOT EXISTS raw_sec_tickers (cik BIGINT, ticker VARCHAR, title VARCHAR)
"""


def frame_names(today: date) -> list[tuple[str, str, str, str]]:
    """Every frame to read: (taxonomy, tag, unit, period), annual ones from FIRST_YEAR."""
    names = [
        (t, tag, unit, f"CY{year}") for year in range(FIRST_YEAR, today.year + 1) for _, t, tag, unit in ANNUAL_CONCEPTS
    ]
    year, quarter = today.year, (today.month - 1) // 3 + 1
    for _ in range(INSTANT_QUARTERS):
        names += [(t, tag, unit, f"CY{year}Q{quarter}I") for _, t, tag, unit in INSTANT_CONCEPTS]
        year, quarter = (year, quarter - 1) if quarter > 1 else (year - 1, 4)
    return names


def file_name(taxonomy: str, tag: str, unit: str, period: str) -> str:
    return f"{taxonomy}_{tag}_{unit}_{period}.json"


SOURCE = "sec-xbrl"  # in the source health file: the SEC's XBRL frames, for company cash-flow data


def sec_fetch(
    log: Callable[[str], None] = print, client: SecClient | None = None
) -> tuple[Callable[[str], str | None], Callable[[], None]]:
    """A fetch that returns a URL's text, or None when the SEC has no such frame yet.

    The close it returns closes the client only when this made it."""
    from thirteenf.ingest.sec import SecClient

    own = client is None
    sec = client or SecClient(log=log)

    def fetch(url: str) -> str | None:
        try:
            return sec.get_text(url, source=SOURCE, missing_ok=True)
        except httpx.HTTPStatusError as err:
            if err.response.status_code == 404:
                return None
            raise

    return fetch, (sec.close if own else lambda: None)


def download_all(
    fetch: Callable[[str], str | None] | None = None,
    today: date | None = None,
    log=print,
    client: SecClient | None = None,
) -> int:
    """Download every frame and the ticker list into data/raw/xbrl/. Frames grow as
    companies file, so each run fetches them again. Returns how many files were written."""
    close = None
    if fetch is None:
        fetch, close = sec_fetch(log, client)
    XBRL_DIR.mkdir(parents=True, exist_ok=True)
    log("Downloading company cash flow data from the SEC (XBRL frames)")
    written = 0
    try:
        jobs = [(TICKERS_FILE, TICKERS_URL)] + [
            (file_name(*name), FRAMES_URL.format(taxonomy=name[0], tag=name[1], unit=name[2], period=name[3]))
            for name in frame_names(today or date.today())
        ]
        for name, url in jobs:
            text = fetch(url)
            if text is None:
                continue  # a year or quarter nobody has reported yet
            part = XBRL_DIR / (name + ".part")
            part.write_text(text, encoding="utf-8")
            part.replace(XBRL_DIR / name)
            written += 1
    finally:
        if close:
            close()
    log(f"  {written} files in {XBRL_DIR}")
    return written


def load_frame(con: duckdb.DuckDBPyConnection, path: Path) -> int:
    """Replace one frame file's rows in raw_xbrl_frames."""
    con.execute("DELETE FROM raw_xbrl_frames WHERE source_file = ?", [path.name])
    before = scalar(con, "SELECT count(*) FROM raw_xbrl_frames")
    # Read by DuckDB, not row by row from Python: a frame holds thousands of companies.
    con.execute(
        """
        INSERT INTO raw_xbrl_frames
        SELECT ?, taxonomy, tag, uom, ccp, d.accn, d.cik, d.entityName, d.loc,
               try_cast(d.start AS DATE), CAST(d."end" AS DATE), CAST(d.val AS DOUBLE)
        FROM (
            SELECT taxonomy, tag, uom, ccp, unnest(data) AS d
            FROM read_json(?, columns = {
                taxonomy: 'VARCHAR', tag: 'VARCHAR', uom: 'VARCHAR', ccp: 'VARCHAR',
                data: 'STRUCT(accn VARCHAR, cik BIGINT, "entityName" VARCHAR, loc VARCHAR,
                              start VARCHAR, "end" VARCHAR, val DOUBLE)[]'
            })
        )
        """,
        [path.name, str(path)],
    )
    return scalar(con, "SELECT count(*) FROM raw_xbrl_frames") - before


def load_tickers(con: duckdb.DuckDBPyConnection, path: Path) -> int:
    """Replace raw_sec_tickers with company_tickers.json: {"0": {"cik_str", "ticker", "title"}, ...}."""
    con.execute("DELETE FROM raw_sec_tickers")
    con.execute(
        """
        INSERT INTO raw_sec_tickers
        SELECT CAST(v->>'cik_str' AS BIGINT), v->>'ticker', v->>'title'
        FROM (SELECT unnest(json_extract(CAST(content AS JSON), '$.*')) AS v FROM read_text(?))
        """,
        [str(path)],
    )
    return scalar(con, "SELECT count(*) FROM raw_sec_tickers")


def load_all(con: duckdb.DuckDBPyConnection, folder: Path | None = None, log=print) -> int:
    """Load every downloaded frame and the ticker list. Returns the rows loaded."""
    folder = folder or XBRL_DIR
    con.execute(RAW_DDL)
    if not folder.exists():
        return 0
    total = 0
    for path in sorted(folder.glob("*.json")):
        total += load_tickers(con, path) if path.name == TICKERS_FILE else load_frame(con, path)
    log(f"Loaded company cash flow data: {total:,} rows")
    return total
