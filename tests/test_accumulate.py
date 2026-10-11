"""The accumulate list: company cash flow from the SEC's XBRL frames, met with the
13F flows. Runs on the made-up data set, with made-up frames, so it never skips."""

import json
import re
from datetime import date

import pytest
from conftest import QUIET, FakeFtdSec, ftd_zip_bytes, map_mini_tickers, openfigi_down
from fastapi.testclient import TestClient

from thirteenf.db import connect
from thirteenf.ingest import ftd, xbrl
from thirteenf.tickers import TickerFallback, update_tickers
from thirteenf.web.app import app

AAPL, MSFT, NVDA, AMZN = "037833100", "594918104", "67066G104", "023135106"
# CIK: (ticker as the SEC writes it, OCF, capex tag, capex, diluted shares), the
# same in both fiscal years. Prices
# in minidata: AAPL 200, MSFT 400, AMZN 180, so with 1B shares:
# AAPL 10% (but funds flat), MSFT 6% (up two periods), AMZN 8% (up one period).
COMPANIES = {
    320193: ("T037", 25e9, "PaymentsToAcquirePropertyPlantAndEquipment", 5e9, 1e9),
    789019: ("T594", 30e9, "PaymentsToAcquirePropertyPlantAndEquipment", 6e9, 1e9),
    1018724: ("T023", 20e9, "PaymentsToAcquireProductiveAssets", 5.6e9, 1e9),
}


def _frame(taxonomy, tag, unit, period, facts):
    return json.dumps(
        {
            "taxonomy": taxonomy,
            "tag": tag,
            "ccp": period,
            "uom": unit,
            "data": [
                {
                    "accn": f"0000{cik}-24-000001",
                    "cik": cik,
                    "entityName": f"Company {cik}",
                    "loc": "US-WA",
                    "end": end,
                    "val": val,
                }
                | ({"start": "2023-10-01"} if not period.endswith("I") else {})
                for cik, end, val in facts
            ],
        }
    )


def _url(tag, unit, period, taxonomy="us-gaap"):
    return xbrl.FRAMES_URL.format(taxonomy=taxonomy, tag=tag, unit=unit, period=period)


def _sec(
    cover_shares: dict[int, float],
    diluted: dict[int, float],
    financial: list[int],
    loans: dict[int, tuple[float, float | None]],
) -> dict[str, str]:
    """URL -> body for every file the SEC has; anything else is a 404. Each company
    reports the same two fiscal years, to September 2023 and September 2024.
    `loans` is CIK -> (loan interest and fees, revenue or None) for each year."""
    pages = {
        xbrl.TICKERS_URL: json.dumps(
            {str(n): {"cik_str": cik, "ticker": c[0], "title": f"Company {cik}"} for n, (cik, c) in enumerate(COMPANIES.items())}
        ),
        _url("EntityCommonStockSharesOutstanding", "shares", "CY2024Q4I", "dei"): _frame(
            "dei", "EntityCommonStockSharesOutstanding", "shares", "CY2024Q4I",
            [(k, "2024-12-31", v) for k, v in cover_shares.items()],
        ),
    }  # fmt: skip
    for year in (2023, 2024):
        end, period = f"{year}-09-30", f"CY{year}"
        ocf = "NetCashProvidedByUsedInOperatingActivities"
        pages[_url(ocf, "USD", period)] = _frame(
            "us-gaap", ocf, "USD", period, [(k, end, c[1]) for k, c in COMPANIES.items()]
        )
        shares = "WeightedAverageNumberOfDilutedSharesOutstanding"
        pages[_url(shares, "shares", period)] = _frame(
            "us-gaap", shares, "shares", period, [(k, end, diluted.get(k, c[4])) for k, c in COMPANIES.items()]
        )
        capex: dict[str, list] = {}
        for cik, (_, _, tag, value, _) in COMPANIES.items():
            capex.setdefault(tag, []).append((cik, end, value))
        for tag, facts in capex.items():
            pages[_url(tag, "USD", period)] = _frame("us-gaap", tag, "USD", period, facts)
        if financial:
            pages[_url("PremiumsEarnedNet", "USD", period)] = _frame(
                "us-gaap", "PremiumsEarnedNet", "USD", period, [(k, end, 1e9) for k in financial]
            )
        if loans:
            tag = "InterestAndFeeIncomeLoansConsumer"
            pages[_url(tag, "USD", period)] = _frame(
                "us-gaap", tag, "USD", period, [(k, end, v[0]) for k, v in loans.items()]
            )
            revenue = [(k, end, v[1]) for k, v in loans.items() if v[1] is not None]
            pages[_url("Revenues", "USD", period)] = _frame("us-gaap", "Revenues", "USD", period, revenue)
    return pages


@pytest.fixture
def accumulate_db(mini_db, tmp_path, monkeypatch):
    """The made-up 13F data with tickers and made-up company financials. Returns
    a function that loads the SEC files with the given cover-page share counts."""

    def setup(
        cover_shares: dict[int, float] | None = None,
        diluted: dict[int, float] | None = None,
        financial=(),
        loans: dict[int, tuple[float, float | None]] | None = None,
    ) -> list[str]:
        pages = _sec(
            {789019: 1e9} if cover_shares is None else cover_shares, diluted or {}, list(financial), loans or {}
        )
        asked: list[str] = []

        def fetch(url: str) -> str | None:
            asked.append(url)
            return pages.get(url)

        monkeypatch.setattr(xbrl, "XBRL_DIR", tmp_path / "raw" / "xbrl")
        assert xbrl.download_all(fetch=fetch, today=date(2025, 1, 15), log=QUIET) == len(pages)
        with connect() as con:
            xbrl.load_all(con, log=QUIET)
        map_mini_tickers(monkeypatch)  # the ticker step rebuilds the cash flow tables
        return asked

    return setup


def _listed(html: str) -> list[str]:
    table = html.split("Stocks to accumulate", 1)[1].split("</table>", 1)[0]
    return re.findall(r'href="/stock/([0-9A-Z]{9})"', table)


def test_download_asks_for_every_frame_and_skips_missing_ones(accumulate_db):
    asked = accumulate_db()
    assert xbrl.TICKERS_URL in asked
    assert any("/CY2025.json" in u for u in asked)  # not reported yet: a 404, skipped
    assert sum("EntityCommonStockSharesOutstanding" in u for u in asked) == xbrl.INSTANT_QUARTERS


def test_free_cash_flow_takes_the_first_capex_tag_reported(accumulate_db):
    accumulate_db()
    with connect(read_only=True) as con:
        rows = dict(con.execute("SELECT cusip, free_cash_flow FROM stock_cash_flows").fetchall())
    assert rows == {AAPL: 20e9, MSFT: 24e9, AMZN: pytest.approx(14.4e9)}  # NVDA has no SEC ticker match


def test_the_list_holds_stocks_funds_keep_moving_into(accumulate_db):
    accumulate_db()
    html = TestClient(app).get("/accumulate").text
    assert "Accumulate list, Q4 2024" in html
    assert _listed(html) == [MSFT]  # AAPL's funds are flat, AMZN is up one period only
    assert "6.0%" in html


def test_a_shorter_streak_lets_amazon_in_ranked_by_yield(accumulate_db):
    accumulate_db()
    client = TestClient(app)
    assert _listed(client.get("/accumulate", params={"streak": 1}).text) == [AMZN, MSFT]
    assert _listed(client.get("/accumulate", params={"streak": 1, "yield": 7}).text) == [AMZN]
    assert _listed(client.get("/accumulate", params={"streak": 1, "by": "tide"}).text) == [MSFT, AMZN]


def test_share_counts_that_disagree_leave_a_stock_out(accumulate_db):
    accumulate_db({789019: 4e9})  # four times the diluted count: a split since the fiscal year
    html = TestClient(app).get("/accumulate").text
    assert _listed(html) == []
    assert "No stock meets the criteria" in html


def test_funds_holding_more_than_the_company_is_worth_leave_a_stock_out(accumulate_db):
    accumulate_db(cover_shares={}, diluted={789019: 1e6})  # a share count off by 1,000
    assert _listed(TestClient(app).get("/accumulate").text) == []


def test_banks_and_insurers_are_left_out(accumulate_db):
    accumulate_db(financial=[789019])
    html = TestClient(app).get("/accumulate").text
    assert _listed(html) == []
    assert "Leaves out 1 bank, insurer or lender" in html


@pytest.mark.parametrize(
    ("loan_income", "revenue", "listed"),
    [
        (20e9, 60e9, False),  # a third of revenue: a lender, like Enova or World Acceptance
        (5e9, 60e9, True),  # a small lending arm, like a carmaker's
        (5e9, None, False),  # loan interest and no revenue line: a lender
    ],
)
def test_lenders_are_left_out(accumulate_db, loan_income, revenue, listed):
    accumulate_db(loans={789019: (loan_income, revenue)})
    html = TestClient(app).get("/accumulate").text
    assert _listed(html) == ([MSFT] if listed else [])
    assert f"Leaves out {0 if listed else 1} " in html


def test_an_unverified_ticker_brings_no_company_figures(accumulate_db, monkeypatch, tmp_path):
    """With OpenFIGI down, Microsoft's ticker comes from the SEC's fails-to-deliver data
    and Amazon's from its issuer name. Only the first reaches the company's cash flow."""
    accumulate_db()
    with connect() as con:
        con.execute("DELETE FROM openfigi")  # as if OpenFIGI had never answered
        con.execute("UPDATE raw_sec_tickers SET title = 'AMAZON COM INC' WHERE ticker = 'T023'")
    monkeypatch.setenv("SEC_USER_AGENT", "ThirteenF tests@example.com")
    monkeypatch.setattr(ftd, "FTD_DIR", tmp_path / "ftd")
    name = "cnsfails202501a.zip"
    sec = FakeFtdSec({name: ftd_zip_bytes(name, [("20250110", MSFT, "T594", "10", "MICROSOFT CORP", "400.00")])})
    openfigi_down(monkeypatch, [])
    update_tickers(log=QUIET, fallback=TickerFallback(connect, QUIET, sec.client))
    with connect(read_only=True) as con:
        sources = dict(con.execute("SELECT cusip, ticker_source FROM stocks WHERE ticker IS NOT NULL").fetchall())
        matched = {r[0] for r in con.execute("SELECT cusip FROM stock_cash_flows").fetchall()}
    assert sources == {MSFT: "sec-ftd", AMZN: "issuer-name"}
    assert matched == {MSFT}


def test_the_page_asks_for_update_data_before_cash_flow_exists(mini_db):
    """A database built before this page existed has no cash flow tables."""
    with connect() as con:
        con.execute("DROP TABLE stock_cash_flows")
    html = TestClient(app).get("/accumulate").text
    assert "Run update-data" in html
