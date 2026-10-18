"""The accumulate list: company cash flow from the SEC's XBRL frames, met with the
13F flows. Runs on rows written by hand, on the made-up data set with made-up frames,
and in a browser, so it never skips."""

import json
import re
from datetime import date

import pytest
from conftest import QUIET, FakeFtdSec, ftd_zip_bytes, map_mini_tickers, openfigi_down
from fastapi.testclient import TestClient
from model_rows import PERIOD, cash_flow, model, stock, stock_period
from playwright.sync_api import Page, expect

from thirteenf.db import connect
from thirteenf.ingest import ftd, xbrl
from thirteenf.tickers import TickerFallback, update_tickers
from thirteenf.web import data
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


# --- The list's rules, on rows written by hand (docs/13f-data.md, "The list") ---------------


def _period(month_end: date, prev: date | None, deadline: date, data_through: date) -> data.Period:
    label = f"Q{(month_end.month - 1) // 3 + 1} {month_end.year}"
    return data.Period(month_end, label, prev, deadline, False, data_through, 160, 0.0)


def test_the_list_opens_on_the_latest_period_whose_on_time_filings_are_all_in():
    q2, q3, q4 = date(2024, 6, 30), date(2024, 9, 30), date(2024, 12, 31)
    periods = [
        _period(q2, None, date(2024, 8, 14), date(2024, 11, 30)),
        _period(q3, q2, date(2024, 11, 14), date(2024, 11, 30)),
        _period(q4, q3, date(2025, 2, 14), date(2024, 11, 30)),  # its deadline is still ahead
    ]
    assert data.accumulate_period(periods).period == q3
    # Before any period with one before it is complete, the latest such period.
    early = [periods[0], _period(q3, q2, date(2024, 11, 14), date(2024, 10, 31))]
    assert data.accumulate_period(early).period == q3


# The stock that meets every rule: 150 funds from 140 (+7.1%) while all filers grew 2%, for
# the second period running, money flowing in, and free cash flow of $6B and $7B on a market
# value of $100 x 1B shares: a 6% yield on the lower year.
MEETS = "M00000001"
LEFT_OUT = {
    "S00000001": ({"streak": 1}, {}),  # more funds for one period only
    "T00000001": ({"funds": 141}, {}),  # more funds, but fewer than the tide brought
    "N00000001": ({"net_flow": -1e6}, {}),  # money flowed out
    "P00000001": ({}, {"prior": -1e9}),  # free cash flow negative in the year before
    "Y00000001": ({}, {"free_cash_flow": 4e9, "prior": 4.5e9}),  # a 4% yield
    "B00000001": ({}, {"financial": True}),  # a bank, insurer or lender
    "C00000001": ({}, {"shares_outstanding": 2e9}),  # the cover page counts twice the shares: a split
    "V00000001": ({"value": 1.6e11}, {}),  # funds hold more than the company is worth
    "O00000001": ({}, {"fiscal_end": date(2023, 3, 31)}),  # a fiscal year over 18 months before the period
    "F00000001": ({"funds_prev": 99}, {}),  # under 100 funds before
}


def _criteria_db():
    rows, flows, stocks = [], [], []
    for cusip, (period_rule, cash_rule) in {MEETS: ({}, {}), **LEFT_OUT}.items():
        period_change, cash_change = dict(period_rule), dict(cash_rule)
        funds, funds_prev = period_change.pop("funds", 150), period_change.pop("funds_prev", 140)
        rows.append(
            stock_period(
                cusip,
                funds,
                funds_prev,
                filers_pct=0.02,
                **{"streak": 2, "net_flow": 1e6, "value": 1e9} | period_change,
            )
        )
        fcf, prior = cash_change.pop("free_cash_flow", 6e9), cash_change.pop("prior", 7e9)
        flows.append(cash_flow(cusip, fcf, prior, diluted_shares=1e9, **cash_change))
        stocks.append(stock(cusip, f"Company {cusip[0]}"))
    return model(stocks, rows, flows)


def test_a_stock_is_listed_only_when_every_rule_holds():
    con = _criteria_db()
    rows = data.accumulate(con, PERIOD, minimum=100, min_yield=0.05, min_streak=2)
    assert [r["cusip"] for r in rows] == [MEETS]
    assert rows[0]["fcf_yield"] == pytest.approx(0.06)  # the lower year over the market value
    assert rows[0]["market_value"] == pytest.approx(1e11)
    coverage = data.accumulate_coverage(con, PERIOD, minimum=100)
    assert coverage == {"compared": 10, "with_cash_flow": 8, "financial": 1, "shares_differ": 2}


def test_the_settings_on_the_page_widen_or_narrow_the_list():
    con = _criteria_db()

    def listed(**settings) -> list[str]:
        rules = {"minimum": 100, "min_yield": 0.05, "min_streak": 2} | settings
        return [r["cusip"] for r in data.accumulate(con, PERIOD, **rules)]

    assert listed(min_streak=1) == [MEETS, "S00000001"]  # same yield: by CUSIP
    assert listed(min_yield=0.04) == [MEETS, "Y00000001"]
    assert listed(min_yield=0.07) == []
    assert listed(min_streak=3) == []
    assert listed(minimum=99) == ["F00000001", MEETS]  # the same yield: by CUSIP
    # Ranked by the change against the tide, Y's and M's tie; by yield M's 6% comes first.
    assert listed(min_yield=0.04, by="tide") == [MEETS, "Y00000001"]
    assert listed(min_yield=0.04, by="yield") == [MEETS, "Y00000001"]


# --- The list on the made-up data set ---------------------------------------------------


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
    assert '<span class="tf-ticker">T594</span> <a href=' in html  # OpenFIGI's ticker: no mark
    assert 'title="Ticker ' not in html


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
    html = TestClient(app).get("/accumulate").text
    note = "Ticker from the SEC’s fails-to-deliver data, as of Jan 10, 2025"
    assert _listed(html) == [MSFT]
    assert (
        f'<span class="tf-ticker">T594</span> <span class="tf-tag tf-tag--hold" title="{note}">'
        f'<span aria-hidden="true">FTD</span><span class="sr-only">{note}</span></span> <a href="/stock/{MSFT}">'
    ) in html


def test_the_page_asks_for_update_data_before_cash_flow_exists(mini_db):
    """A database built before this page existed has no cash flow tables."""
    with connect() as con:
        con.execute("DROP TABLE stock_cash_flows")
    html = TestClient(app).get("/accumulate").text
    assert "Run update-data" in html


# --- In the browser --------------------------------------------------------------------


@pytest.mark.ui
def test_a_person_reads_the_list_and_changes_its_settings(accumulate_db, page: Page):
    accumulate_db()
    page.goto("/")
    page.get_by_role("navigation", name="Main").get_by_role("link", name="Accumulate").click()
    table = page.locator("section").filter(has=page.get_by_role("heading", name=re.compile("^Stocks to accumulate")))
    expect(page.get_by_role("heading", level=1)).to_contain_text("Q4 2024")
    expect(table.locator("tbody a[href^='/stock/']")).to_have_count(1)
    expect(table.locator("tbody tr").first).to_contain_text("6.0%")
    expect(page.get_by_text("not advice", exact=False).first).to_be_visible()

    page.get_by_label("Periods with more funds").fill("1")
    page.get_by_role("button", name="Update").click()
    expect(page).to_have_url(re.compile(r"streak=1"))
    hrefs = table.locator("tbody a[href^='/stock/']").evaluate_all("els => els.map(e => e.getAttribute('href'))")
    assert hrefs == [f"/stock/{AMZN}", f"/stock/{MSFT}"]  # 8% before 6%

    table.get_by_role("link").filter(has_text=re.compile("Amazon", re.I)).first.click()
    expect(page).to_have_url(re.compile(f"/stock/{AMZN}$"))
