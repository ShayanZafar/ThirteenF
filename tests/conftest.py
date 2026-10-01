import csv
from datetime import date

import duckdb
import pytest

from thirteenf.config import DB_PATH, REFERENCE_CSV
from thirteenf.model.periods import quarter_end


@pytest.fixture(scope="session")
def con():
    """Read-only connection to the loaded data. Data tests skip until ingest has run."""
    if not DB_PATH.exists():
        pytest.skip("No data yet: run python -m thirteenf.ingest")
    connection = duckdb.connect(str(DB_PATH), read_only=True)
    connection.execute("SET enable_progress_bar = false")
    yield connection
    connection.close()


def _period(text: str) -> date:
    return quarter_end(int(text[:4]), int(text[-1]))


@pytest.fixture(scope="session")
def reference() -> list[dict]:
    """13f.info's published figures for the eight test stocks."""
    with open(REFERENCE_CSV, newline="") as f:
        return [
            {
                "ticker": row["ticker"],
                "cusip": row["cusip"],
                "period": _period(row["period"]),
                "filings": int(row["filings"]),
                "shares": int(row["shares_excl_options"]),
                "value": int(row["value_excl_options_usd"]),
            }
            for row in csv.DictReader(f)
        ]
