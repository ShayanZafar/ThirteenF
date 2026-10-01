"""Phase 1: download and load the SEC data."""

import zipfile
from datetime import date

import duckdb
import pytest

from thirteenf.ingest import load, sec

TEST_STOCKS = {
    "SHOP": "82509L107", "AAPL": "037833100", "MSFT": "594918104", "NVDA": "67066G104",
    "AMZN": "023135106", "GOOGL": "02079K305", "META": "30303M102", "TSLA": "88160R101",
}


def test_links_come_from_the_page_in_either_folder():
    html = """
    <a href="/files/datastandardsinnovation/data/form-13f-data-sets/01jun2026-31aug2026_form13f.zip">x</a>
    <a href="/files/structureddata/data/form-13f-data-sets/01mar2024-31may2024_form13f.zip">x</a>
    <a href="/files/structureddata/data/form-13f-data-sets/01jun2024-31aug2024_form13f.zip">x</a>
    <a href="/files/structureddata/data/form-13f-data-sets/2023q4_form13f.zip">x</a>
    """
    found = sec.parse_data_sets(html)
    assert [d.name for d in found] == [
        "01mar2024-31may2024_form13f.zip",
        "01jun2024-31aug2024_form13f.zip",
        "01jun2026-31aug2026_form13f.zip",
    ]
    assert found[-1].url.startswith("https://www.sec.gov/files/datastandardsinnovation/")
    assert found[-1].start == date(2026, 6, 1) and found[-1].end == date(2026, 8, 31)
    assert [d.name for d in sec.wanted(found)] == [
        "01jun2024-31aug2024_form13f.zip", "01jun2026-31aug2026_form13f.zip"
    ]


def _tiny_zip(path):
    tables = {
        "SUBMISSION.tsv": "ACCESSION_NUMBER\tFILING_DATE\tSUBMISSIONTYPE\tCIK\tPERIODOFREPORT\n"
        "0001-24-000001\t31-JUL-2024\t13F-HR\t0000000001\t30-JUN-2024\n",
        "COVERPAGE.tsv": "ACCESSION_NUMBER\tISAMENDMENT\tAMENDMENTTYPE\tREPORTTYPE\tFILINGMANAGER_NAME\n"
        "0001-24-000001\tN\t\t13F HOLDINGS REPORT\tTest \"Quoted\" Manager\n",
        "SUMMARYPAGE.tsv": "ACCESSION_NUMBER\tTABLEENTRYTOTAL\tTABLEVALUETOTAL\n0001-24-000001\t2\t3000\n",
        "INFOTABLE.tsv": "ACCESSION_NUMBER\tINFOTABLE_SK\tNAMEOFISSUER\tCUSIP\tVALUE\tSSHPRNAMT\tSSHPRNAMTTYPE\tPUTCALL\n"
        "0001-24-000001\t1\tAPPLE INC\t037833100\t2000\t10\tSH\t\n"
        "0001-24-000001\t2\tAPPLE INC\t037833100\t1000\t5\tSH\tCall\n",
    }
    with zipfile.ZipFile(path, "w") as z:
        for name, text in tables.items():
            z.writestr(name, text)


def test_loading_the_same_zip_twice_does_not_duplicate_rows(tmp_path):
    zip_path = tmp_path / "01jun2024-31aug2024_form13f.zip"
    _tiny_zip(zip_path)
    con = duckdb.connect(str(tmp_path / "test.duckdb"))
    load.ensure_load_log(con)
    quiet = lambda *_: None

    assert load.load_zip(con, zip_path, log=quiet, work_root=tmp_path / "work")
    assert not load.load_zip(con, zip_path, log=quiet, work_root=tmp_path / "work")
    # Forget the log and load again: rows are replaced, not added.
    con.execute("DELETE FROM load_log")
    assert load.load_zip(con, zip_path, log=quiet, work_root=tmp_path / "work")

    assert con.execute("SELECT count(*) FROM raw_infotable").fetchone()[0] == 2
    assert con.execute("SELECT count(*) FROM raw_submission").fetchone()[0] == 1
    # Fields are kept byte for byte, quotes included.
    assert con.execute("SELECT FILINGMANAGER_NAME FROM raw_coverpage").fetchone()[0] == 'Test "Quoted" Manager'
    assert con.execute("SELECT DISTINCT source_zip FROM raw_infotable").fetchall() == [(zip_path.name,)]
    logged = con.execute("SELECT table_name, row_count FROM load_log ORDER BY 1").fetchall()
    assert logged == [("raw_coverpage", 1), ("raw_infotable", 2), ("raw_submission", 1), ("raw_summarypage", 1)]


@pytest.mark.data
def test_load_log_lists_every_zip_and_table(con):
    rows = con.execute(
        "SELECT source_zip, count(*), min(row_count) FROM load_log GROUP BY 1 ORDER BY 1"
    ).fetchall()
    assert len(rows) >= 9
    for source_zip, tables, fewest_rows in rows:
        assert tables == 4, source_zip
        assert fewest_rows > 0, source_zip


@pytest.mark.data
def test_every_period_has_thousands_of_cusips(con):
    rows = con.execute(
        """
        SELECT p.period, count(DISTINCT upper(trim(i.CUSIP)))
        FROM periods p
        JOIN submissions s ON s.period = p.period
        JOIN raw_infotable i ON i.ACCESSION_NUMBER = s.accession
        GROUP BY 1 ORDER BY 1
        """
    ).fetchall()
    assert len(rows) >= 9
    for period, cusips in rows:
        assert cusips > 5000, period


@pytest.mark.data
@pytest.mark.parametrize("ticker", TEST_STOCKS)
def test_each_test_stock_has_rows_in_all_nine_periods(con, ticker):
    periods = con.execute(
        """
        SELECT count(DISTINCT s.period)
        FROM raw_infotable i JOIN submissions s ON s.accession = i.ACCESSION_NUMBER
        WHERE upper(trim(i.CUSIP)) = ? AND s.period BETWEEN DATE '2024-06-30' AND DATE '2026-06-30'
        """,
        [TEST_STOCKS[ticker]],
    ).fetchone()[0]
    assert periods == 9
