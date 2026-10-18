import csv
import io
import json
import socket
import threading
import time
import zipfile
from datetime import date
from pathlib import Path

import duckdb
import httpx
import minidata
import pytest
import uvicorn

import thirteenf.config
import thirteenf.db
import thirteenf.tickers
import thirteenf.web.data
from thirteenf import health
from thirteenf.config import DB_PATH, REFERENCE_CSV
from thirteenf.ingest import ftd, load, openfigi
from thirteenf.ingest.sec import SecClient
from thirteenf.model import build
from thirteenf.model.periods import quarter_end
from thirteenf.web.app import app

QUIET = lambda *_: None


def ftd_zip_bytes(
    name: str, rows: list[tuple], header: str = ftd.HEADER, count: int | None = None, member: str | None = None
) -> bytes:
    """A fails-to-deliver zip as the SEC writes it: one latin-1, pipe-delimited .txt with
    CRLF line ends and two trailer lines (`count` overrides the record count it gives, `member`
    the name of the file inside, which is the zip's name with .txt unless given)."""
    lines = [header, *("|".join(row) for row in rows)]
    lines += [
        f"Trailer record count {len(rows) if count is None else count}",
        f"Trailer total quantity of shares {sum(int(row[3]) for row in rows)}",
    ]
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr(member or name.replace(".zip", ".txt"), ("\r\n".join(lines) + "\r\n").encode("latin-1"))
    return out.getvalue()


def write_ftd_zip(folder: Path, name: str, rows: list[tuple], **kwargs) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(ftd_zip_bytes(name, rows, **kwargs))
    return path


def ftd_page(*names: str) -> str:
    """The fails-to-deliver page linking `names`, the 2020 ones in the older folder, as on sec.gov."""
    folders = {True: "/files/node/add/data_distribution/", False: "/files/data/fails-deliver-data/"}
    return "".join(f'<li><a href="{folders[n.startswith("cnsfails2020")]}{n}">{n}</a></li>' for n in names)


class FakeFtdSec:
    """The SEC's fails-to-deliver page and zips (name -> bytes) behind SecClient, on a fake
    transport and a fake clock. `refuse`, when given, answers every request instead: a
    function that makes a response, or an exception to raise."""

    def __init__(self, files: dict[str, bytes], page: str | None = None, refuse=None):
        self.files, self.refuse = files, refuse
        self.page = ftd_page(*files) if page is None else page
        self.seen: list[str] = []
        self.slept: list[float] = []
        self.now = 1000.0

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request.url.path.rsplit("/", 1)[-1])
        if isinstance(self.refuse, Exception):
            raise self.refuse
        if self.refuse:
            return self.refuse()
        if request.url.path.endswith(".zip"):
            name = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(200, content=self.files[name]) if name in self.files else httpx.Response(404)
        return httpx.Response(200, text=self.page)

    def _sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    def client(self) -> SecClient:
        return SecClient(
            transport=httpx.MockTransport(self._handle), sleep=self._sleep, clock=lambda: self.now, log=QUIET
        )


@pytest.fixture(autouse=True)
def source_health(tmp_path, monkeypatch):
    """Every test records how sources answer in a folder of its own, never in data/."""
    monkeypatch.setattr(health, "HEALTH_PATH", tmp_path / "source-health.json")
    monkeypatch.setattr(health, "EVENTS_PATH", tmp_path / "source-health-events.json")


@pytest.fixture(autouse=True)
def own_watchlist_file(tmp_path, monkeypatch):
    """Every test reads and writes a watchlist of its own, started from the example list,
    never yours in data/ (a test can point it elsewhere)."""
    monkeypatch.setattr(thirteenf.config, "WATCHLIST_PATH", tmp_path / "watchlist.csv")


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
    with thirteenf.db.connect() as con:
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


REAL_OPENFIGI_CLIENT = openfigi.OpenFigiClient  # the helpers below replace it with fakes


def map_mini_tickers(monkeypatch) -> None:
    """Run the ticker step against fake_openfigi, as python -m thirteenf.tickers would."""
    monkeypatch.setattr(thirteenf.tickers, "openfigi_api_key", lambda: "test-key")
    monkeypatch.setattr(
        openfigi,
        "OpenFigiClient",
        lambda key: REAL_OPENFIGI_CLIENT(key, transport=httpx.MockTransport(fake_openfigi), sleep=lambda _: None),
    )
    thirteenf.tickers.update_tickers(log=QUIET)


def openfigi_down(monkeypatch, slept: list[float], refusal: str = "dropped") -> None:
    """Every OpenFIGI request is refused or fails: "429", "503", or "dropped" (the connection
    drops). Any sleep the client asks for goes to `slept`."""

    def down(request: httpx.Request) -> httpx.Response:
        if refusal == "dropped":
            raise httpx.ConnectError("Connection reset by peer", request=request)
        return httpx.Response(int(refusal), headers={"ratelimit-reset": "60"})

    monkeypatch.setattr(thirteenf.tickers, "openfigi_api_key", lambda: "test-key")
    monkeypatch.setattr(
        openfigi,
        "OpenFigiClient",
        lambda key: REAL_OPENFIGI_CLIENT(key, transport=httpx.MockTransport(down), sleep=slept.append),
    )


# --- The browser tests (marked ui) ------------------------------------------------


@pytest.fixture(scope="session")
def app_url():
    """The app served over HTTP on a free port, in a thread of the test process, for the
    browser tests. It reads the database and watchlist each test sets up (mini_db and the
    monkeypatched paths), since those are module globals the server looks up per request."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", lifespan="off"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:  # the test's own wait for its server, never the app's
        if not thread.is_alive() or time.monotonic() > deadline:
            raise RuntimeError("The app did not start for the browser tests")
        time.sleep(0.01)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)
    sock.close()


@pytest.fixture(scope="session")
def browser():
    """Headless Chromium, through Playwright, for the whole run."""
    from playwright.sync_api import Error, sync_playwright

    with sync_playwright() as playwright:
        try:
            chromium = playwright.chromium.launch()
        except Error as err:
            raise RuntimeError(
                "The browser tests need Chromium: run .venv/bin/python -m playwright install chromium "
                "(.venv\\Scripts\\python -m playwright install chromium on Windows)"
            ) from err
        yield chromium
        chromium.close()


@pytest.fixture
def page(browser, app_url):
    """A fresh browser tab on the running app: page.goto("/changes") opens that page."""
    context = browser.new_context(base_url=app_url, accept_downloads=True)
    tab = context.new_page()
    tab.set_default_timeout(10_000)
    yield tab
    context.close()
