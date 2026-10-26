"""The pages say when a data source stops answering, and when the 13F data was last fetched.

Decision #25 (docs/decisions.md): while some data need has no reliable source, every page
shows the source health summary as a stale stamp, read from the health file on each
request; the pages with a Source stamp also say when the SEC's 13F data sets last answered.
On the made-up data set, with OpenFIGI and the SEC played by stand-ins."""

from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from conftest import QUIET, FakeFtdSec, openfigi_down
from fastapi.testclient import TestClient
from markupsafe import escape
from playwright.sync_api import Page, expect

from thirteenf import health, tickers
from thirteenf.db import connect
from thirteenf.ingest import ftd
from thirteenf.web import format as fmt
from thirteenf.web.app import app

MSFT = "594918104"
STAMPED = ("/", f"/stock/{MSFT}", "/changes", "/accumulate", "/managers", "/manager/135")
PAGES = ("/stock", *STAMPED)
BLOCK_PAGE = "<html><h1>Request Rate Threshold Exceeded</h1></html>"


def test_every_page_warns_while_a_data_need_has_no_reliable_source(mini_db):
    client = TestClient(app)
    fetched = datetime.now(UTC) - timedelta(days=3)
    health.record("sec", "ok", now=fetched)
    stamp = f"<b>Fetched</b><i>·</i>{fmt.day(fetched.astimezone().date())}<i>·</i>3d"
    for path in PAGES:
        text = client.get(path).text
        assert "<b>Sources</b>" not in text, path  # every source answers
        assert (stamp in text) is (path in STAMPED), path

    for source, outcome in (("openfigi", "failed"), ("sec-ftd", "throttled")):
        for _ in range(5):
            health.record(source, outcome, "down")
    summary = health.load()["summary"]
    assert summary.startswith("No reliable source for tickers:")
    warning = f'<span class="tf-stamp tf-stamp--stale"><b>Sources</b><i>·</i>{escape(summary)}</span>'
    for path in PAGES:
        assert warning in client.get(path).text, path


@pytest.mark.ui
def test_a_person_sees_on_every_page_that_tickers_have_no_reliable_source(mini_db, monkeypatch, tmp_path, page: Page):
    monkeypatch.setenv("SEC_USER_AGENT", "ThirteenF tests@example.com")
    monkeypatch.setattr(ftd, "FTD_DIR", tmp_path / "ftd")
    health.record("sec", "ok")
    openfigi_down(monkeypatch, [])
    fake = FakeFtdSec({}, refuse=lambda: httpx.Response(403, text=BLOCK_PAGE))
    for _ in range(5):
        tickers.update_tickers(log=QUIET, fallback=tickers.TickerFallback(connect, QUIET, fake.client))
    summary = (
        "No reliable source for tickers: OpenFIGI answered 0 of 5 requests in the last 24 hours "
        "and the SEC's fails-to-deliver data 0 of 5."
    )
    for path in PAGES:
        page.goto(path)
        expect(page.locator(".app-sources .tf-stamp--stale")).to_have_text(f"Sources·{summary}")
        if path in STAMPED:
            fetched = page.locator(".app-stamps .tf-stamp").filter(has=page.locator("b").get_by_text("Fetched"))
            expect(fetched).to_have_text(f"Fetched·{fmt.day(date.today())}·0d")
