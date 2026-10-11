"""The SEC's fails-to-deliver data, the first fallback for tickers: links, downloads and
loading, against made-up files and a fake SEC (no network, no real waiting)."""

from datetime import date

import duckdb
import httpx
import pytest
from conftest import FakeFtdSec, ftd_page, ftd_zip_bytes, write_ftd_zip

from thirteenf import health
from thirteenf.ingest import ftd, sec

ROWS = [
    ("20260902", "037833100", "AAPL", "1500", "APPLE INC", "230.10"),
    ("20260903", "B38564108", "EURN", "172729", "EURONAV NV ANTWERPEN (BELGIUM)", "10.31"),
    ("20260904", "F21107101", "GLE", "100", "SOCIÉTÉ GÉNÉRALE", "."),
]
BLOCK_PAGE = "<html><h1>Request Rate Threshold Exceeded</h1></html>"


@pytest.fixture(autouse=True)
def user_agent(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "ThirteenF tests@example.com")


def test_links_are_ordered_by_the_date_in_their_names_not_their_folders():
    html = (
        '<a href="/files/data/fails-deliver-data/cnsfails202609a.zip">Sep 2026, first half</a>'
        '<a href="/files/node/add/data_distribution/cnsfails202001b.zip">Jan 2020, second half</a>'
        "<a href='https://www.sec.gov/files/data/fails-deliver-data/cnsfails202608b.zip'>Aug 2026</a>"
        '<a href="/files/node/add/data_distribution/cnsfails202001a.zip">Jan 2020</a>'
        '<a href="/files/data/fails-deliver-data/cnsfails202608a.zip">Aug 2026</a>'
        '<a href="/files/data/fails-deliver-data/cnsfails202608a.zip">the same file again</a>'
        '<a href="/files/data/form-13f-data-sets/01jun2026-31aug2026_form13f.zip">not a fails file</a>'
    )
    found = ftd.parse_links(html)
    assert [f.name for f in found] == [
        "cnsfails202001a.zip",
        "cnsfails202001b.zip",
        "cnsfails202608a.zip",
        "cnsfails202608b.zip",
        "cnsfails202609a.zip",
    ]
    assert found[0].url == "https://www.sec.gov/files/node/add/data_distribution/cnsfails202001a.zip"
    assert sorted(found, key=lambda f: f.url)[-1].month == "202001"  # why paths are never the order


def test_the_newest_thirteen_months_are_wanted():
    months = [f"{y}{m:02d}" for y in range(2009, 2027) for m in range(1, 13) if f"{y}{m:02d}" <= "202609"]
    names = [f"cnsfails{m}{half}.zip" for m in months for half in "ab"][:-1]  # Sep 2026's second half is not out
    wanted = ftd.newest(ftd.parse_links(ftd_page(*reversed(names))))
    assert wanted[0].name == "cnsfails202509a.zip" and wanted[-1].name == "cnsfails202609a.zip"
    assert len(wanted) == 25
    # Calendar months, counted back from the newest file, whatever the page leaves out.
    assert [f.name for f in ftd.newest(ftd.parse_links(ftd_page("cnsfails201912b.zip", "cnsfails202609a.zip")))] == [
        "cnsfails202609a.zip"
    ]
    assert ftd.newest([]) == []


def test_a_file_loads_as_it_is(tmp_path):
    path = write_ftd_zip(tmp_path, "cnsfails202609a.zip", ROWS)
    con = duckdb.connect()
    assert ftd.load_file(con, path) == 3
    rows = con.execute("SELECT * FROM raw_ftd ORDER BY rowid").fetchall()
    assert rows[0] == ("20260902", "037833100", "AAPL", "1500", "APPLE INC", "230.10", "cnsfails202609a.zip")
    assert rows[2][4] == "SOCIÉTÉ GÉNÉRALE" and rows[2][5] == "."  # latin-1 read as latin-1; text kept as it is
    assert rows[3][0] == "Trailer record count 3" and rows[4][0].startswith("Trailer total quantity of shares")
    assert ftd.load_file(con, path) == 3  # loading it again replaces its rows
    assert con.execute("SELECT count(*) FROM raw_ftd").fetchone()[0] == 5


@pytest.mark.parametrize("member", ["cnsfails202509a", "CNSFAILS202509A.TXT"])
def test_a_file_whose_data_file_has_no_extension_loads_too(tmp_path, member):
    # All of the SEC's 2025 and early-2026 zips hold "cnsfails202509a" with no .txt (seen Oct 11, 2026).
    path = write_ftd_zip(tmp_path, "cnsfails202509a.zip", ROWS, member=member)
    assert ftd.load_file(duckdb.connect(), path) == 3


def test_a_zip_holding_some_other_file_is_left_out(tmp_path):
    path = write_ftd_zip(tmp_path, "cnsfails202509a.zip", ROWS, member="readme.txt")
    with pytest.raises(ValueError, match=r"expected one cnsfails202509a or cnsfails202509a\.txt inside, found 0"):
        ftd.load_file(duckdb.connect(), path)


def test_the_symbol_on_the_most_recent_settlement_date_wins(tmp_path):
    folder = tmp_path / "ftd"
    write_ftd_zip(
        folder,
        "cnsfails202608b.zip",
        [
            ("20260828", "30303M102", "FB", "10", "META PLATFORMS", "1"),
            ("20260828", "037833100", "AAPL", "10", "APPLE", "1"),
        ],
    )
    write_ftd_zip(
        folder,
        "cnsfails202609a.zip",
        [
            ("20260902", "30303M102", "META", "10", "META PLATFORMS", "1"),
            ("20260903", "88160R101", "", "10", "TESLA", "1"),
        ],
    )
    con = duckdb.connect()
    logged: list[str] = []
    assert ftd.load_new(con, folder, log=logged.append) == 2
    assert logged == ["    cnsfails202608b.zip: 2 rows", "    cnsfails202609a.zip: 2 rows"]
    assert ftd.load_new(con, folder, log=logged.append) == 0  # each file is loaded once
    symbols = ftd.latest_symbols(con)
    assert symbols["30303M102"] == ("META", date(2026, 9, 2))
    assert symbols["037833100"] == ("AAPL", date(2026, 8, 28))
    assert "88160R101" not in symbols  # no symbol, no answer


@pytest.mark.parametrize(
    "rows, kwargs, problem",
    [
        (ROWS, {"header": "DATE|CUSIP|SYMBOL|QUANTITY|DESCRIPTION|PRICE"}, "unexpected header"),
        (ROWS, {"count": 4}, "3 rows, but its trailer counts 4"),
        ([*ROWS, ("20260905", "123456789", "XYZ", "5", "PIPE | INC", "1")], {}, "CSV Error"),
    ],
)
def test_a_file_that_does_not_read_as_documented_is_left_out(tmp_path, rows, kwargs, problem):
    folder = tmp_path / "ftd"
    write_ftd_zip(folder, "cnsfails202609a.zip", rows, **kwargs)
    write_ftd_zip(folder, "cnsfails202609b.zip", ROWS)
    con = duckdb.connect()
    logged: list[str] = []
    assert ftd.load_new(con, folder, log=logged.append) == 1
    assert logged[0].startswith("    cnsfails202609a.zip: not loaded (") and problem in logged[0]
    assert con.execute("SELECT DISTINCT source_file FROM raw_ftd").fetchall() == [("cnsfails202609b.zip",)]


def test_only_the_newest_files_not_here_yet_are_downloaded(tmp_path):
    folder = tmp_path / "ftd"
    write_ftd_zip(folder, "cnsfails202609a.zip", ROWS)
    names = ["cnsfails202001a.zip", "cnsfails202508b.zip", "cnsfails202509a.zip", "cnsfails202608b.zip"]
    fake = FakeFtdSec({name: ftd_zip_bytes(name, ROWS) for name in [*names, "cnsfails202609a.zip"]})
    client = fake.client()
    logged: list[str] = []
    assert ftd.download_new(client, log=logged.append, folder=folder) == 2
    client.close()
    assert fake.seen == ["fails-deliver-data", "cnsfails202509a.zip", "cnsfails202608b.zip"]
    assert logged == ["    cnsfails202509a.zip: downloading", "    cnsfails202608b.zip: downloading"]
    assert sorted(p.name for p in folder.iterdir()) == [
        "cnsfails202509a.zip",
        "cnsfails202608b.zip",
        "cnsfails202609a.zip",
    ]
    assert (folder / "cnsfails202509a.zip").read_bytes() == fake.files["cnsfails202509a.zip"]  # kept as downloaded
    assert health.load()["sources"]["sec-ftd"]["ok"] == 3
    assert all(s == pytest.approx(sec.MIN_SECONDS_BETWEEN_REQUESTS) for s in fake.slept)  # pacing only


@pytest.mark.parametrize(
    "refuse, raised, outcome",
    [
        (lambda: httpx.Response(403, text=BLOCK_PAGE), sec.SecBlocked, "throttled"),
        (lambda: httpx.Response(429, headers={"Retry-After": "600"}), sec.SecBlocked, "throttled"),
        (lambda: httpx.Response(503), sec.SecUnavailable, "failed"),
        (httpx.ConnectError("Connection reset by peer"), sec.SecUnavailable, "failed"),
    ],
)
def test_a_refusing_sec_is_left_at_once(tmp_path, refuse, raised, outcome):
    fake = FakeFtdSec({}, refuse=refuse)
    with pytest.raises(raised):
        ftd.download_new(fake.client(), folder=tmp_path / "ftd")
    assert fake.seen == ["fails-deliver-data"] and fake.slept == []
    assert health.load()["sources"]["sec-ftd"][outcome] == 1


def test_a_page_without_links_says_so(tmp_path):
    fake = FakeFtdSec({}, page="<html>Fails-to-deliver data has moved</html>")
    with pytest.raises(ftd.NoLinks):
        ftd.download_new(fake.client(), folder=tmp_path / "ftd")
