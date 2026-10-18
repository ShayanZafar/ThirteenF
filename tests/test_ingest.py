"""Phase 1: download and load the SEC data."""

import zipfile
from datetime import date

import duckdb
import httpx
import minidata
import pytest
from conftest import QUIET
from playwright.sync_api import Page, expect

import thirteenf.db
import thirteenf.web.data
from thirteenf.ingest import load, sec
from thirteenf.model import build

TEST_STOCKS = {
    "SHOP": "82509L107",
    "AAPL": "037833100",
    "MSFT": "594918104",
    "NVDA": "67066G104",
    "AMZN": "023135106",
    "GOOGL": "02079K305",
    "META": "30303M102",
    "TSLA": "88160R101",
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
    assert [d.name for d in sec.wanted(found)] == ["01jun2024-31aug2024_form13f.zip", "01jun2026-31aug2026_form13f.zip"]


def _tiny_zip(path):
    tables = {
        "SUBMISSION.tsv": "ACCESSION_NUMBER\tFILING_DATE\tSUBMISSIONTYPE\tCIK\tPERIODOFREPORT\n"
        "0001-24-000001\t31-JUL-2024\t13F-HR\t0000000001\t30-JUN-2024\n",
        "COVERPAGE.tsv": "ACCESSION_NUMBER\tISAMENDMENT\tAMENDMENTTYPE\tREPORTTYPE\tFILINGMANAGER_NAME\n"
        '0001-24-000001\tN\t\t13F HOLDINGS REPORT\tTest "Quoted" Manager\n',
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
    rows = con.execute("SELECT source_zip, count(*), min(row_count) FROM load_log GROUP BY 1 ORDER BY 1").fetchall()
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


@pytest.mark.ui
def test_each_refresh_brings_the_newest_period_to_the_pages(tmp_path, monkeypatch, page: Page):
    """Before the first update every page says how to load the data; then each run of the
    update's 13F steps (download from the SEC, played by a stand-in serving the made-up zips;
    load; build) brings the newest filing window to the pages the person has open."""
    data_dir = tmp_path / "data"
    for module in (thirteenf.db, thirteenf.web.data):
        monkeypatch.setattr(module, "DB_PATH", data_dir / "thirteenf.duckdb")
    monkeypatch.setattr(sec, "RAW_DIR", data_dir / "raw")
    monkeypatch.setattr(load, "RAW_DIR", data_dir / "raw")
    monkeypatch.setattr(load, "DATA_DIR", data_dir)
    monkeypatch.setenv("SEC_USER_AGENT", "ThirteenF tests@example.com")
    zips = {path.name: path.read_bytes() for path in minidata.write_zips(tmp_path / "published")}
    published: list[str] = []  # the zips the SEC's page links so far

    def the_sec(request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        if name.endswith(".zip"):
            return httpx.Response(200, content=zips[name]) if name in published else httpx.Response(404)
        folder = "/files/structureddata/data/form-13f-data-sets/"
        return httpx.Response(200, text="".join(f'<a href="{folder}{n}">{n}</a>' for n in published))

    def update_data() -> None:
        client = sec.SecClient(transport=httpx.MockTransport(the_sec), sleep=lambda _: None, log=QUIET)
        sec.download_all(log=QUIET, client=client)
        load.load_all(log=QUIET)
        build.build_all(log=QUIET)

    heading = page.get_by_role("heading", level=1)
    page.goto("/")
    expect(heading).to_have_text("ThirteenF")
    expect(page.get_by_text("The SEC’s Form 13F data has not been loaded yet.")).to_be_visible()
    expect(page.locator("code")).to_have_text("python -m thirteenf.ingest")

    published += list(zips)[:2]  # Q2 and Q3 2024
    update_data()
    page.reload()
    expect(heading).to_have_text("Your watchlist, Q3 2024")
    expect(page.locator(".app-stamps")).to_contain_text("As of Sep 30, 2024")
    expect(page.locator(".app-stamps")).to_contain_text("filed through Nov 30, 2024")

    published.append(list(zips)[2])  # the SEC publishes the December to February window
    update_data()
    page.get_by_role("navigation", name="Main").get_by_role("link", name="Biggest changes").click()
    expect(heading).to_have_text("Biggest changes in funds holding, Q4 2024")
    page.get_by_role("navigation", name="Main").get_by_role("link", name="Overview").click()
    expect(heading).to_have_text("Your watchlist, Q4 2024")
    expect(page.locator(".app-stamps")).to_contain_text("filed through Feb 28, 2025")
    assert sorted(p.name for p in (data_dir / "raw").glob("*.zip")) == sorted(zips)
