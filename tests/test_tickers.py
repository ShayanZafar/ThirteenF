"""Phase 6: tickers and search. For any stock, its ticker, its name and its CUSIP all open its page."""

import pytest
from fastapi.testclient import TestClient

from thirteenf.web.app import app

pytestmark = pytest.mark.data

# (ticker as people write it, a name as people type it, CUSIP)
STOCKS = [
    ("AAPL", "Apple", "037833100"),
    ("SHOP", "Shopify", "82509L107"),
    ("NVDA", "NVIDIA", "67066G104"),
    ("BRK.B", "Berkshire Hathaway Inc Del Cl B", "084670702"),
    ("HON", "Honeywell Intl", "438516205"),
    ("XOM", "Exxon Mobil", "30233Q108"),
    ("TSLA", "Tesla", "88160R101"),
]


@pytest.fixture(scope="module")
def client(con):
    mapped = con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = 'openfigi'"
    ).fetchone()[0] and con.execute("SELECT count(*) FROM stocks WHERE ticker IS NOT NULL").fetchone()[0]
    if not mapped:
        pytest.skip("No tickers yet: run python -m thirteenf.tickers")
    return TestClient(app)


def _opens(client, query: str) -> str | None:
    """The stock page a search lands on: by redirect, or as the first result."""
    response = client.get("/stock", params={"q": query}, follow_redirects=False)
    if response.status_code == 303:
        return response.headers["location"].split("?")[0].rsplit("/", 1)[-1]
    first = response.text.split('href="/stock/', 2)
    return first[1][:9] if len(first) > 1 else None


@pytest.mark.parametrize("ticker, name, cusip", STOCKS)
def test_ticker_name_and_cusip_open_the_page(client, ticker, name, cusip):
    assert _opens(client, ticker) == cusip, ticker
    assert _opens(client, ticker.lower()) == cusip, ticker.lower()
    assert _opens(client, name) == cusip, name
    assert _opens(client, cusip) == cusip, cusip
    page = client.get(f"/stock/{cusip}").text
    assert f'<span class="tf-ticker">{ticker}</span>' in page


def test_a_share_class_can_be_named(client):
    assert _opens(client, "Berkshire Hathaway") == "084670702"  # class B: the most widely held
    assert _opens(client, "Berkshire Hathaway class A") == "084670108"


def test_share_class_tickers_match_however_written(client):
    for written in ("BRK.B", "BRK/B", "BRK-B", "brkb"):
        assert _opens(client, written) == "084670702", written


def test_an_earlier_cusip_still_opens_the_stock(client):
    assert _opens(client, "30231G102") == "30233Q108"  # Exxon Mobil before its holding company


def test_suggestions_as_you_type(client):
    found = client.get("/api/suggest", params={"q": "nvda"}).json()
    assert found and found[0]["ticker"] == "NVDA" and found[0]["cusip"] == "67066G104"
    assert client.get("/api/suggest", params={"q": "nvidia"}).json()[0]["ticker"] == "NVDA"
    # A prefix suggests every ticker that starts with it; an exact ticker ranks first.
    prefixed = client.get("/api/suggest", params={"q": "nvd"}).json()
    assert "NVDA" in [s["ticker"] for s in prefixed]
    assert client.get("/api/suggest", params={"q": "apple"}).json()[0]["ticker"] == "AAPL"
    assert client.get("/api/suggest", params={"q": ""}).json() == []
    assert len(client.get("/api/suggest", params={"q": "a"}).json()) <= 8
