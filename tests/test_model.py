"""Phase 2: holdings model and data checks, against 13f.info's published figures.

13f.info counts filings; the app counts managers, from the SEC's data sets
only. Its counts run 4 to 9% higher (see docs/13f-data.md), so the check is on
the change from one period to the next, which is what every page shows, with
a looser bound on the level.
"""

from datetime import date

import pytest

pytestmark = pytest.mark.data

CHANGE_TOLERANCE_PTS = 2.0
LEVEL_TOLERANCE = 0.11  # worst case: Shopify, Q2 2024, 10.1% under
BIG_SEVEN = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"]
Q2_2026 = date(2026, 6, 30)


def _ours(con, cusip):
    return dict(
        con.execute(
            "SELECT period, funds_holding FROM holders WHERE cusip = ? ORDER BY period", [cusip]
        ).fetchall()
    )


def _by_ticker(reference):
    out = {}
    for row in reference:
        out.setdefault(row["ticker"], []).append(row)
    return {t: sorted(rows, key=lambda r: r["period"]) for t, rows in out.items()}


def test_periods_run_q2_2024_to_q2_2026(con):
    periods = [r[0] for r in con.execute("SELECT period FROM periods ORDER BY period").fetchall()]
    assert periods[0] == date(2024, 6, 30)
    assert periods[-1] >= Q2_2026
    assert len(periods) >= 9


def test_one_current_filing_per_manager_and_period(con):
    dupes = con.execute(
        "SELECT count(*) FROM (SELECT cik, period FROM filings GROUP BY ALL HAVING count(*) > 1)"
    ).fetchone()[0]
    assert dupes == 0


def test_cik_is_one_manager_however_it_is_padded(con):
    # The SEC files CIK 1539994 both as "1539994" and "0001539994".
    ciks = con.execute("SELECT DISTINCT cik FROM submissions WHERE cik = 1539994").fetchall()
    assert ciks == [(1539994,)]


def test_amendments_are_applied(con):
    # Every filing has exactly one base report: an original or a restatement.
    bad = con.execute(
        """
        SELECT count(*) FROM (
            SELECT cik, period FROM filing_parts GROUP BY ALL
            HAVING count(*) FILTER (WHERE role IN ('original', 'restatement')) > 1
        )
        """
    ).fetchone()[0]
    assert bad == 0


@pytest.mark.parametrize("ticker", ["SHOP", *BIG_SEVEN])
def test_funds_holding_tracks_the_reference(con, reference, ticker):
    rows = _by_ticker(reference)[ticker]
    ours = _ours(con, rows[0]["cusip"])
    report = []
    for prev, cur in zip(rows, rows[1:]):
        ref_pct = (cur["filings"] / prev["filings"] - 1) * 100
        our_pct = (ours[cur["period"]] / ours[prev["period"]] - 1) * 100
        report.append((cur["period"], round(ref_pct, 1), round(our_pct, 1)))
        assert abs(our_pct - ref_pct) <= CHANGE_TOLERANCE_PTS, report
    for row in rows:
        level_gap = ours[row["period"]] / row["filings"] - 1
        assert abs(level_gap) <= LEVEL_TOLERANCE, (row["period"], ours[row["period"]], row["filings"])


@pytest.mark.parametrize("ticker", BIG_SEVEN)
def test_q2_2026_share_totals_pass_or_are_flagged(con, reference, ticker):
    """The reference's Q2 2026 share totals jump 46% to 117%. Ours must either
    move in line with value once flagged rows are left out, or be flagged."""
    cusip = _by_ticker(reference)[ticker][0]["cusip"]
    shares_pct, value_pct, gap, check = con.execute(
        "SELECT shares_pct, value_pct, shares_vs_value_pts, share_check FROM stock_periods WHERE cusip = ? AND period = ?",
        [cusip, Q2_2026],
    ).fetchone()
    flagged = con.execute(
        """
        SELECT manager_name, shares, value, round(price_ratio, 4), reason
        FROM price_check WHERE cusip = ? AND period = ? AND left_out
        ORDER BY shares DESC
        """,
        [cusip, Q2_2026],
    ).fetchall()
    print(f"\n{ticker} Q2 2026: shares {shares_pct:+.1%}, value {value_pct:+.1%}, gap {gap:+.1f} pts, check {check}")
    for name, shares, value, ratio, reason in flagged:
        print(f"  left out: {name}: {shares:,} sh, ${value:,} ({reason}, {ratio}x median)")
    assert check in ("ok", "outran")
    if check == "ok":
        assert abs(gap) < 25
        assert shares_pct < 0.25  # nothing like the reference's 46% to 117% jump


def test_shares_match_the_reference_where_it_is_consistent(con, reference):
    """Where the reference's own share total agrees with its value (implied
    price within 5% of ours), our share total lands within 6% of it. This
    leaves out the reference's suspect totals, such as Q2 2026."""
    compared = 0
    for row in reference:
        shares, value = con.execute(
            "SELECT shares, value FROM holders WHERE cusip = ? AND period = ?", [row["cusip"], row["period"]]
        ).fetchone()
        if abs((row["value"] / row["shares"]) / (value / shares) - 1) > 0.05:
            continue
        compared += 1
        assert abs(shares / row["shares"] - 1) < 0.06, (row["ticker"], row["period"], shares, row["shares"])
    assert compared >= 55


def test_filers_total_jumps_at_year_end(con):
    rows = dict(con.execute("SELECT period, filers FROM filers_total").fetchall())
    assert rows[date(2024, 12, 31)] > rows[date(2024, 9, 30)] * 1.05
    assert rows[date(2025, 12, 31)] > rows[date(2025, 9, 30)] * 1.05


def test_changes_add_up(con):
    """Funds holding now = funds holding before + opened - sold out - not yet filed."""
    bad = con.execute(
        """
        SELECT count(*)
        FROM stock_periods sp JOIN changes c USING (cusip, period)
        WHERE sp.funds_prev IS NOT NULL
          AND sp.funds_holding <> sp.funds_prev + c.opened - c.sold_out - c.not_yet_filed
        """
    ).fetchone()[0]
    assert bad == 0


def test_price_check_lists_manager_names(con):
    missing = con.execute("SELECT count(*) FROM price_check WHERE manager_name IS NULL").fetchone()[0]
    assert missing == 0


def test_a_cusip_change_folds_the_old_cusip_into_the_new(con):
    """Honeywell moved its holders from 438516106 to 438516205 in Q2 2026,
    one new share for every two old ones."""
    stock, ratio = con.execute("SELECT stock, ratio FROM stock_keys WHERE cusip = '438516106'").fetchone()
    assert stock == "438516205"
    assert abs(ratio - 0.5) < 0.01
    before = con.execute(
        "SELECT funds_holding FROM holders WHERE cusip = '438516205' AND period = DATE '2026-03-31'"
    ).fetchone()[0]
    old_cusip_before = con.execute(
        "SELECT funds FROM cusip_holders WHERE cusip = '438516106' AND period = DATE '2026-03-31'"
    ).fetchone()[0]
    assert before >= old_cusip_before
    assert con.execute("SELECT count(*) FROM holders WHERE cusip = '438516106'").fetchone()[0] == 0


def test_coincidences_are_not_cusip_changes(con):
    """Funds that left these acquired companies opened other new CUSIPs in the
    same quarter, but their shares do not convert at one ratio."""
    for cusip in ["127097103", "48203R104", "68339B104", "83125X103"]:  # Coterra, Juniper, ON24, Sleep Number
        assert con.execute("SELECT stock FROM stock_keys WHERE cusip = ?", [cusip]).fetchone()[0] == cusip


def test_every_stock_is_its_own_key(con):
    chained_twice = con.execute(
        "SELECT count(*) FROM stock_keys k JOIN stock_keys s ON s.cusip = k.stock WHERE s.stock <> s.cusip"
    ).fetchone()[0]
    assert chained_twice == 0
