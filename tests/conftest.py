import csv
import json
from datetime import date

import duckdb
import httpx
import minidata
import pytest

import thirteenf.db
import thirteenf.tickers
import thirteenf.web.data
from thirteenf.config import DB_PATH, REFERENCE_CSV
from thirteenf.db import connect
from thirteenf.ingest import load, openfigi
from thirteenf.model import build
from thirteenf.model.periods import quarter_end

QUIET = lambda *_: None


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


@pytest.fixture
def mini_db(tmp_path, monkeypatch):
    """The made-up data set (tests/minidata.py), loaded and built, in a database of its own."""
    monkeypatch.setattr(thirteenf.db, "DB_PATH", tmp_path / "mini.duckdb")
    monkeypatch.setattr(thirteenf.web.data, "DB_PATH", tmp_path / "mini.duckdb")  # what the pages read
    with connect() as con:
        load.ensure_load_log(con)
        for path in minidata.write_zips(tmp_path / "raw"):
            load.load_zip(con, path, log=QUIET, work_root=tmp_path / "work")
    build.build_all(log=QUIET)
    return tmp_path / "mini.duckdb"


def fake_openfigi(request: httpx.Request) -> httpx.Response:
    """OpenFIGI for the made-up securities: QQQ is an ETF, the rest common stock ticked T + 3 digits."""
    out = []
    for job in json.loads(request.content):
        if job["idType"] != "ID_CUSIP" or job["idValue"] not in minidata.SECURITIES:
            out.append({"warning": "No identifier found."})
            continue
        etf = job["idValue"] == minidata.QQQ
        ticker = "QQQ" if etf else f"T{job['idValue'][:3]}"
        out.append({"data": [{"ticker": ticker, "exchCode": "US", "securityType": "ETP" if etf else "Common Stock"}]})
    return httpx.Response(200, json=out)


def map_mini_tickers(monkeypatch) -> None:
    """Run the ticker step against fake_openfigi, as python -m thirteenf.tickers would."""
    real_client = openfigi.OpenFigiClient
    monkeypatch.setattr(thirteenf.tickers, "openfigi_api_key", lambda: "test-key")
    monkeypatch.setattr(
        openfigi,
        "OpenFigiClient",
        lambda key: real_client(key, transport=httpx.MockTransport(fake_openfigi), sleep=lambda _: None),
    )
    thirteenf.tickers.update_tickers(log=QUIET)
