"""Build the holdings model from the raw SEC tables, as defined in docs/13f-data.md.

Every table here is derived; dropping them all and running build_all() again
rebuilds them from raw_* exactly.

  periods        quarter ends covered by the loaded filing windows
  submissions    every filing, parsed, one row per accession
  filing_parts   the accessions that make up each manager's current filing
  filings        one current filing per manager (CIK) per period
  managers       manager names
  positions      manager x CUSIP x period: shares and value, with the implied-price check
  price_check    the positions flagged by the implied-price check
  cusip_holders  per CUSIP and period: funds holding (used to find CUSIP changes)
  cusip_changes  CUSIPs replaced by another: most funds moved across at one exchange ratio
  stock_keys     each CUSIP's stock (its latest CUSIP) and the ratio to today's shares
  holders        per stock and period: funds holding, shares held, value
  filers_total   per period: managers that filed holdings
  changes        per stock and period: managers that opened, added, trimmed, sold out or held
  stock_periods  per stock and period: changes against last period, the tide and the market median
  securities     per CUSIP: the name and class filers use, and its stock
  stocks         per stock: the name of whichever of its CUSIPs most funds report

A stock is identified by its current CUSIP. When a company changes its CUSIP
(a reverse split, a new holding company, a move abroad), the old CUSIP's
history is folded into the new one, with shares converted at the exchange ratio.
"""

from __future__ import annotations

import re
import time
from datetime import date, datetime

import duckdb

from thirteenf.db import connect
from thirteenf.model import periods as P

# Implied-price check: flag a position whose value / shares is this many times
# above or below the median across all managers holding the CUSIP that period.
PRICE_FACTOR = 3.0
# Managers that still file VALUE in thousands (the rule before 2023) show an
# implied price about this many times below the median; their shares are kept.
VALUE_THOUSANDS = 1000
# Shares-against-value check: flag a share total that moves this many
# percentage points beyond its value from one period to the next.
SHARES_VS_VALUE_PTS = 25.0
# Market median: stocks held by at least this many funds in both periods.
MEDIAN_MIN_FUNDS = 100
# CUSIP changes. Funds that left an old CUSIP (held by at least CHANGE_MIN_FUNDS
# funds) opened a new CUSIP, and at least half of the new CUSIP's new holders
# came from the old one. In a real change every holding converts at one ratio and
# keeps its value, so at least CHANGE_SAME_RATIO of the funds that moved sit
# within 5% of the median share ratio, and their positions keep between 1/10 and
# 10 times their value (a contingent value right is worth far less than the stock).
# Coincidences, such as index funds dropping one stock and adding another, fail
# those tests. Either most of the funds that left moved (a completed change), or
# at least CHANGE_PARTIAL_MOVED moved at a tighter CHANGE_PARTIAL_SAME (a change
# still under way at quarter end, such as Exxon's new holding company in 2026).
CHANGE_MIN_FUNDS = 20
CHANGE_MIN_MOVED = 20
CHANGE_SAME_RATIO = 0.2
CHANGE_PARTIAL_MOVED = 50
CHANGE_PARTIAL_SAME = 0.5
CHANGE_VALUE_RANGE = (0.1, 10)

WINDOW = re.compile(r"(\d{2}[a-z]{3}\d{4})-(\d{2}[a-z]{3}\d{4})_form13f\.zip$", re.I)


def _day(text: str) -> date:
    return datetime.strptime(text.lower(), "%d%b%Y").date()


def build_periods(con: duckdb.DuckDBPyConnection) -> None:
    zips = [r[0] for r in con.execute("SELECT DISTINCT source_zip FROM load_log").fetchall()]
    windows = sorted((_day(m.group(1)), _day(m.group(2))) for z in zips if (m := WINDOW.search(z)))
    if not windows:
        raise RuntimeError("load_log has no filing windows; run python -m thirteenf.ingest")
    first_start, last_end = windows[0][0], windows[-1][1]
    first = P.first_full_period(first_start)
    # The latest period anyone has filed holdings for, within the loaded windows.
    last = con.execute(
        """
        SELECT max(period) FROM submissions
        WHERE role = 'original' AND period >= ? AND period <= ?
        """,
        [first, last_end],
    ).fetchone()[0]
    rows = []
    for seq, period in enumerate(P.periods_between(first, last), start=1):
        deadline = P.filing_deadline(period)
        rows.append(
            (
                period,
                seq,
                P.label(period),
                P.previous_quarter_end(period) if seq > 1 else None,
                deadline,
                deadline <= last_end,
                last_end,
            )
        )
    con.execute(
        """
        CREATE OR REPLACE TABLE periods (
            period DATE PRIMARY KEY, seq INTEGER, label VARCHAR, prev_period DATE,
            deadline DATE, complete BOOLEAN, data_through DATE
        )
        """
    )
    con.executemany("INSERT INTO periods VALUES (?, ?, ?, ?, ?, ?, ?)", rows)


SQL_SUBMISSIONS = """
CREATE OR REPLACE TABLE submissions AS
SELECT DISTINCT ON (s.ACCESSION_NUMBER)
    s.ACCESSION_NUMBER                               AS accession,
    CAST(s.CIK AS BIGINT)                            AS cik,
    strptime(s.PERIODOFREPORT, '%d-%b-%Y')::DATE     AS period,
    strptime(s.FILING_DATE, '%d-%b-%Y')::DATE        AS filing_date,
    s.SUBMISSIONTYPE                                 AS submission_type,
    c.AMENDMENTTYPE                                  AS amendment_type,
    TRY_CAST(c.AMENDMENTNO AS INTEGER)               AS amendment_no,
    c.REPORTTYPE                                     AS report_type,
    c.FILINGMANAGER_NAME                             AS manager_name,
    TRY_CAST(sp.TABLEENTRYTOTAL AS BIGINT)           AS table_entry_total,
    TRY_CAST(sp.TABLEVALUETOTAL AS BIGINT)           AS table_value_total,
    -- A 13F-HR is the original even when its cover page says otherwise;
    -- a 13F-HR/A without a type replaces the report, like a restatement.
    CASE
        WHEN s.SUBMISSIONTYPE = '13F-HR' THEN 'original'
        WHEN s.SUBMISSIONTYPE = '13F-HR/A' AND c.AMENDMENTTYPE = 'NEW HOLDINGS' THEN 'new holdings'
        WHEN s.SUBMISSIONTYPE = '13F-HR/A' THEN 'restatement'
        ELSE 'notice'
    END                                              AS role,
    -- VALUE was in thousands of dollars before January 3, 2023.
    CASE WHEN strptime(s.FILING_DATE, '%d-%b-%Y')::DATE < DATE '2023-01-03' THEN 1000 ELSE 1 END
                                                     AS value_multiplier,
    s.source_zip
FROM raw_submission s
LEFT JOIN raw_coverpage c USING (ACCESSION_NUMBER, source_zip)
LEFT JOIN raw_summarypage sp USING (ACCESSION_NUMBER, source_zip)
ORDER BY s.ACCESSION_NUMBER, s.source_zip DESC
"""

# Current filing per manager and period: the latest restatement, or the
# original if there is none, plus any later NEW HOLDINGS amendments.
SQL_FILING_PARTS = """
CREATE OR REPLACE TABLE filing_parts AS
WITH held AS (
    SELECT * FROM submissions
    WHERE role <> 'notice' AND period IN (SELECT period FROM periods)
),
base AS (
    SELECT DISTINCT ON (cik, period) cik, period, accession, filing_date
    FROM held
    WHERE role IN ('restatement', 'original')
    ORDER BY cik, period, (role = 'restatement') DESC, filing_date DESC, accession DESC
)
SELECT h.cik, h.period, h.accession, h.role, h.filing_date, h.value_multiplier
FROM held h
LEFT JOIN base b ON b.cik = h.cik AND b.period = h.period
WHERE h.accession = b.accession
   OR (h.role = 'new holdings'
       AND (b.accession IS NULL OR (h.filing_date, h.accession) > (b.filing_date, b.accession)))
"""

SQL_FILINGS = """
CREATE OR REPLACE TABLE filings AS
WITH lines AS (
    SELECT i.ACCESSION_NUMBER AS accession, count(*) AS lines
    FROM raw_infotable i
    WHERE i.ACCESSION_NUMBER IN (SELECT accession FROM filing_parts)
    GROUP BY 1
)
SELECT
    fp.cik,
    fp.period,
    arg_max(fp.accession, fp.role <> 'new holdings')   AS base_accession,
    count(*) - 1                                        AS new_holdings_amendments,
    bool_or(fp.role = 'restatement')                    AS restated,
    max(fp.filing_date)                                 AS filing_date,
    min(fp.filing_date)                                 AS first_filing_date,
    coalesce(sum(l.lines), 0)                           AS lines,
    arg_max(s.manager_name, (fp.filing_date, fp.accession)) AS manager_name
FROM filing_parts fp
JOIN submissions s USING (accession)
LEFT JOIN lines l USING (accession)
GROUP BY fp.cik, fp.period
"""

SQL_MANAGERS = """
CREATE OR REPLACE TABLE managers AS
SELECT cik, arg_max(manager_name, (filing_date, accession)) AS name
FROM submissions
GROUP BY cik
"""

# Shares: SH rows without PUTCALL (no options, no bond principal). Value: the same rows.
# Then the implied-price check against the median across managers.
SQL_POSITIONS = f"""
CREATE OR REPLACE TABLE positions AS
WITH rows AS (
    SELECT fp.cik, fp.period, upper(trim(i.CUSIP)) AS cusip,
           CAST(i.SSHPRNAMT AS BIGINT) AS shares,
           CAST(i.VALUE AS BIGINT) * fp.value_multiplier AS value
    FROM filing_parts fp
    JOIN raw_infotable i ON i.ACCESSION_NUMBER = fp.accession
    WHERE i.SSHPRNAMTTYPE = 'SH' AND coalesce(trim(i.PUTCALL), '') = ''
),
summed AS (
    SELECT cik, period, cusip, sum(shares)::BIGINT AS shares, sum(value)::BIGINT AS value, count(*) AS lines
    FROM rows
    GROUP BY ALL
),
priced AS (
    SELECT *, CASE WHEN shares > 0 THEN value::DOUBLE / shares END AS implied_price
    FROM summed
),
medians AS (
    SELECT cusip, period, median(implied_price) AS median_price
    FROM priced WHERE shares > 0
    GROUP BY ALL
),
ratios AS (
    SELECT p.*, m.median_price,
           CASE WHEN p.shares > 0 AND m.median_price > 0 THEN p.implied_price / m.median_price END AS price_ratio
    FROM priced p
    LEFT JOIN medians m USING (cusip, period)
),
checked AS (
    SELECT *,
        coalesce(price_ratio > {PRICE_FACTOR} OR price_ratio < 1 / {PRICE_FACTOR}, false) AS off_median,
        -- Some managers still file VALUE in thousands, as before 2023: their
        -- implied price is about 1/1000 of the median while their shares are right.
        coalesce(price_ratio * {VALUE_THOUSANDS} BETWEEN 1 / {PRICE_FACTOR} AND {PRICE_FACTOR}, false)
            AS value_in_thousands
    FROM ratios
)
SELECT * EXCLUDE (off_median),
       off_median AND NOT value_in_thousands AS price_flag,
       CASE WHEN value_in_thousands THEN value * {VALUE_THOUSANDS} ELSE value END::BIGINT AS value_checked
FROM checked
"""

SQL_PRICE_CHECK = """
CREATE OR REPLACE TABLE price_check AS
SELECT p.cusip, p.period, p.cik, f.manager_name, p.shares, p.value,
       p.implied_price, p.median_price, p.price_ratio,
       CASE WHEN p.value_in_thousands THEN 'value in thousands'
            WHEN p.implied_price > p.median_price THEN 'price above median'
            ELSE 'price below median' END AS reason,
       p.price_flag AS left_out
FROM positions p
JOIN filings f USING (cik, period)
WHERE p.price_flag OR p.value_in_thousands
"""

SQL_CUSIP_HOLDERS = """
CREATE OR REPLACE TABLE cusip_holders AS
SELECT cusip, period, count(DISTINCT cik) AS funds
FROM positions
WHERE shares > 0
GROUP BY ALL
"""

SQL_CUSIP_CHANGES = f"""
CREATE OR REPLACE TABLE cusip_changes AS
WITH shrunk AS (   -- CUSIPs that lost funds
    SELECT p.period, p.prev_period, b.cusip
    FROM periods p
    JOIN cusip_holders b ON b.period = p.prev_period
    LEFT JOIN cusip_holders a ON a.period = p.period AND a.cusip = b.cusip
    WHERE b.funds >= {CHANGE_MIN_FUNDS} AND coalesce(a.funds, 0) <= b.funds - {CHANGE_MIN_MOVED}
),
grown AS (         -- CUSIPs that at least doubled their funds, or are new
    SELECT p.period, p.prev_period, a.cusip
    FROM periods p
    JOIN cusip_holders a ON a.period = p.period
    LEFT JOIN cusip_holders b ON b.period = p.prev_period AND b.cusip = a.cusip
    WHERE p.prev_period IS NOT NULL AND a.funds >= {CHANGE_MIN_MOVED} AND coalesce(b.funds, 0) <= a.funds * 0.5
),
departed AS (      -- funds that held a shrunk CUSIP, filed again, and no longer hold it
    SELECT s.period, s.cusip, x.cik, x.shares, x.value_checked AS value
    FROM shrunk s
    JOIN positions x ON x.period = s.prev_period AND x.cusip = s.cusip AND x.shares > 0
    SEMI JOIN filings f ON f.period = s.period AND f.cik = x.cik AND f.lines > 0
    ANTI JOIN positions y ON y.period = s.period AND y.cik = x.cik AND y.cusip = s.cusip AND y.shares > 0
),
arrived AS (       -- funds that hold a grown CUSIP and did not before
    SELECT g.period, g.cusip, x.cik, x.shares, x.value_checked AS value
    FROM grown g
    JOIN positions x ON x.period = g.period AND x.cusip = g.cusip AND x.shares > 0
    ANTI JOIN positions y ON y.period = g.prev_period AND y.cik = x.cik AND y.cusip = g.cusip AND y.shares > 0
),
departed_count AS (SELECT period, cusip, count(*) AS departed FROM departed GROUP BY ALL),
arrived_count AS (SELECT period, cusip, count(*) AS arrived FROM arrived GROUP BY ALL),
moves AS (
    SELECT d.period, d.cusip AS old_cusip, a.cusip AS new_cusip, d.cik,
           a.shares::DOUBLE / d.shares AS ratio,
           a.value::DOUBLE / NULLIF(d.value, 0) AS value_ratio
    FROM departed d
    JOIN arrived a ON a.period = d.period AND a.cik = d.cik AND a.cusip <> d.cusip
),
pairs AS (
    SELECT period, old_cusip, new_cusip, count(*) AS moved,
           median(ratio) AS exchange_ratio, median(value_ratio) AS value_ratio
    FROM moves GROUP BY ALL
    HAVING count(*) >= {CHANGE_MIN_MOVED}
),
scored AS (
    SELECT pr.period, pr.old_cusip, pr.new_cusip, pr.moved, pr.exchange_ratio, pr.value_ratio,
           avg(CASE WHEN abs(m.ratio / pr.exchange_ratio - 1) <= 0.05 THEN 1.0 ELSE 0.0 END) AS same_ratio
    FROM pairs pr
    JOIN moves m USING (period, old_cusip, new_cusip)
    GROUP BY ALL
)
SELECT DISTINCT ON (s.period, s.old_cusip)
    s.period, s.old_cusip, s.new_cusip, s.moved, d.departed, a.arrived,
    s.exchange_ratio, s.same_ratio, s.value_ratio, s.moved < 0.5 * d.departed AS partial
FROM scored s
JOIN departed_count d ON d.period = s.period AND d.cusip = s.old_cusip
JOIN arrived_count a ON a.period = s.period AND a.cusip = s.new_cusip
WHERE s.moved >= 0.5 * a.arrived
  AND s.value_ratio BETWEEN {CHANGE_VALUE_RANGE[0]} AND {CHANGE_VALUE_RANGE[1]}
  AND ((s.moved >= 0.5 * d.departed AND s.same_ratio >= {CHANGE_SAME_RATIO})
       OR (s.moved >= {CHANGE_PARTIAL_MOVED} AND s.same_ratio >= {CHANGE_PARTIAL_SAME}))
ORDER BY s.period, s.old_cusip, (left(s.new_cusip, 6) = left(s.old_cusip, 6)) DESC, s.moved DESC
"""


def build_stock_keys(con: duckdb.DuckDBPyConnection) -> None:
    """Follow each CUSIP through its changes to the stock's current CUSIP."""
    successor: dict[str, tuple[str, float]] = {}
    for old, new, ratio in con.execute(
        "SELECT old_cusip, new_cusip, exchange_ratio FROM cusip_changes ORDER BY period, old_cusip"
    ).fetchall():
        successor.setdefault(old, (new, ratio))
    chained = []
    for cusip in successor:
        stock, ratio, seen = cusip, 1.0, {cusip}
        while stock in successor:
            nxt, step = successor[stock]
            if nxt in seen:
                break
            seen.add(nxt)
            stock, ratio = nxt, ratio * step
        chained.append((cusip, stock, ratio))
    con.execute("CREATE OR REPLACE TEMP TABLE chained (cusip VARCHAR, stock VARCHAR, ratio DOUBLE)")
    if chained:
        quote = lambda text: "'" + text.replace("'", "''") + "'"
        values = ", ".join(f"({quote(c)}, {quote(k)}, {float(r)!r})" for c, k, r in chained)
        con.execute(f"INSERT INTO chained VALUES {values}")
    con.execute(
        """
        CREATE OR REPLACE TABLE stock_keys AS
        SELECT h.cusip, coalesce(c.stock, h.cusip) AS stock, coalesce(c.ratio, 1.0) AS ratio
        FROM (SELECT DISTINCT cusip FROM cusip_holders) h
        LEFT JOIN chained c USING (cusip)
        """
    )


# Stocks reported under more than one CUSIP. Every other CUSIP is its own stock
# and passes straight through, which keeps the per-stock steps fast.
LINKED = "(SELECT cusip FROM stock_keys WHERE stock IN (SELECT stock FROM stock_keys WHERE cusip <> stock))"

_HOLDER_COLUMNS = """
    count(DISTINCT cik)                                         AS funds_holding,
    sum(shares)::BIGINT                                         AS shares_filed,
    sum(value)::BIGINT                                          AS value_filed,
    sum(shares) FILTER (WHERE NOT price_flag)::BIGINT           AS shares,
    sum(value_checked) FILTER (WHERE NOT price_flag)::BIGINT    AS value,
    count(*) FILTER (WHERE price_flag)                          AS flagged_rows,
    count(*) FILTER (WHERE value_in_thousands)                  AS thousands_rows,
    coalesce(sum(shares) FILTER (WHERE price_flag), 0)::BIGINT  AS flagged_shares,
"""

# Per stock: every CUSIP it was reported under, with shares in today's terms.
SQL_HOLDERS = f"""
CREATE OR REPLACE TABLE holders AS
SELECT cusip, period, {_HOLDER_COLUMNS}
    any_value(median_price) AS median_price,
    1::BIGINT AS cusips
FROM positions
WHERE shares > 0 AND cusip NOT IN {LINKED}
GROUP BY ALL
UNION ALL
SELECT cusip, period, {_HOLDER_COLUMNS}
    median(implied_price) AS median_price,
    count(DISTINCT reported_cusip) AS cusips
FROM (
    SELECT k.stock AS cusip, p.cusip AS reported_cusip, p.period, p.cik,
           p.shares * k.ratio AS shares, p.value, p.value_checked,
           p.price_flag, p.value_in_thousands, p.implied_price / k.ratio AS implied_price
    FROM positions p
    JOIN stock_keys k ON k.cusip = p.cusip
    WHERE p.shares > 0 AND p.cusip IN {LINKED}
)
GROUP BY ALL
"""

SQL_FILERS_TOTAL = """
CREATE OR REPLACE TABLE filers_total AS
SELECT p.period, count(f.cik) FILTER (WHERE f.lines > 0) AS filers,
       count(f.cik) AS filings
FROM periods p
LEFT JOIN filings f USING (period)
GROUP BY p.period
"""

# Per manager, between a period and the one before it. A manager that held
# shares last period and has not filed for this one is "not yet filed", never "sold out".
SQL_CHANGES = f"""
CREATE OR REPLACE TABLE changes AS
WITH cur AS (
    SELECT cusip, period, cik, shares::DOUBLE AS shares, false AS converted
    FROM positions
    WHERE shares > 0 AND cusip NOT IN {LINKED}
    UNION ALL
    SELECT k.stock AS cusip, p.period, p.cik, sum(p.shares * k.ratio) AS shares,
           bool_or(k.cusip <> k.stock) AS converted
    FROM positions p
    JOIN stock_keys k ON k.cusip = p.cusip
    WHERE p.shares > 0 AND p.cusip IN {LINKED}
    GROUP BY ALL
),
now AS (
    SELECT c.cik, c.cusip, c.shares, p.period FROM cur c JOIN periods p ON c.period = p.period
    WHERE p.prev_period IS NOT NULL
),
before AS (
    SELECT c.cik, c.cusip, c.shares, c.converted, p.period FROM cur c JOIN periods p ON c.period = p.prev_period
),
pairs AS (
    SELECT coalesce(n.period, b.period) AS period, coalesce(n.cusip, b.cusip) AS cusip,
           coalesce(n.cik, b.cik) AS cik, b.shares AS prev_shares, n.shares AS shares,
           -- Shares converted from an old CUSIP rarely match to the share: within 1% is held.
           CASE WHEN b.converted THEN abs(n.shares - b.shares) <= 0.01 * b.shares
                ELSE n.shares = b.shares END AS same
    FROM now n FULL OUTER JOIN before b ON n.period = b.period AND n.cik = b.cik AND n.cusip = b.cusip
),
filed AS (SELECT cik, period FROM filings WHERE lines > 0)
SELECT
    pairs.cusip, pairs.period,
    count(*) FILTER (WHERE prev_shares IS NULL AND shares IS NOT NULL)           AS opened,
    count(*) FILTER (WHERE prev_shares IS NOT NULL AND NOT same AND shares > prev_shares) AS added,
    count(*) FILTER (WHERE prev_shares IS NOT NULL AND same)                     AS held,
    count(*) FILTER (WHERE prev_shares IS NOT NULL AND NOT same AND shares < prev_shares) AS trimmed,
    count(*) FILTER (WHERE prev_shares IS NOT NULL AND shares IS NULL AND filed.cik IS NOT NULL) AS sold_out,
    count(*) FILTER (WHERE prev_shares IS NOT NULL AND shares IS NULL AND filed.cik IS NULL)     AS not_yet_filed
FROM pairs
LEFT JOIN filed ON filed.cik = pairs.cik AND filed.period = pairs.period
GROUP BY ALL
"""

SQL_STOCK_PERIODS = f"""
CREATE OR REPLACE TABLE stock_periods AS
WITH tide AS (
    SELECT p.period, p.seq, p.prev_period, ft.filers,
           ft.filers::DOUBLE / NULLIF(prev.filers, 0) - 1 AS filers_pct
    FROM periods p
    JOIN filers_total ft USING (period)
    LEFT JOIN filers_total prev ON prev.period = p.prev_period
),
base AS (
    SELECT h.cusip, h.period, t.seq, t.prev_period, t.filers, t.filers_pct,
           h.funds_holding, h.shares, h.value, h.shares_filed, h.value_filed,
           h.flagged_rows, h.flagged_shares, h.median_price,
           prev.funds_holding AS funds_prev, prev.shares AS shares_prev, prev.value AS value_prev,
           prev.median_price AS median_price_prev
    FROM holders h
    JOIN tide t USING (period)
    LEFT JOIN holders prev ON prev.cusip = h.cusip AND prev.period = t.prev_period
),
changed AS (
    SELECT *,
        funds_holding - coalesce(funds_prev, 0) AS funds_change,
        CASE WHEN funds_prev > 0 THEN funds_holding::DOUBLE / funds_prev - 1 END AS funds_pct,
        funds_holding::DOUBLE / filers AS share_of_filers,
        CASE WHEN shares_prev > 0 THEN shares::DOUBLE / shares_prev - 1 END AS shares_pct,
        CASE WHEN value_prev > 0 THEN value::DOUBLE / value_prev - 1 END AS value_pct
    FROM base
),
medians AS (
    SELECT period, median(funds_pct) AS market_median_pct, count(*) AS market_median_stocks
    FROM changed
    WHERE funds_holding >= {MEDIAN_MIN_FUNDS} AND funds_prev >= {MEDIAN_MIN_FUNDS}
    GROUP BY period
),
checked AS (
    SELECT c.*, m.market_median_pct, m.market_median_stocks,
        (c.funds_pct - c.filers_pct) * 100 AS vs_tide_pts,
        (c.funds_pct - m.market_median_pct) * 100 AS vs_median_pts,
        c.median_price / NULLIF(c.median_price_prev, 0) - 1 AS price_pct,
        -- Shares should move with value once the price per share is allowed for:
        -- (1 + value change) / (1 + price change). A gap of 25 points or more
        -- means shares outran value. Price moves and splits pass.
        ((1 + c.shares_pct) - (1 + c.value_pct) / (c.median_price / NULLIF(c.median_price_prev, 0))) * 100
            AS shares_vs_value_pts,
        CASE
            WHEN c.shares_pct IS NULL OR c.value_pct IS NULL
                 OR coalesce(c.median_price_prev, 0) <= 0 OR coalesce(c.median_price, 0) <= 0 THEN 'none'
            WHEN abs((1 + c.shares_pct) - (1 + c.value_pct) / (c.median_price / c.median_price_prev)) * 100
                 < {SHARES_VS_VALUE_PTS} THEN 'ok'
            ELSE 'outran'
        END AS share_check
    FROM changed c
    LEFT JOIN medians m USING (period)
),
signed AS (
    SELECT *, CASE WHEN funds_prev IS NULL THEN NULL ELSE sign(funds_change) END AS direction
    FROM checked
),
islands AS (
    SELECT *, seq - row_number() OVER (PARTITION BY cusip, direction ORDER BY seq) AS island
    FROM signed
)
SELECT * EXCLUDE (island),
    CASE WHEN direction IS NULL THEN 0
         ELSE row_number() OVER (PARTITION BY cusip, direction, island ORDER BY seq) END AS streak
FROM islands
"""

# The name and class most filers use for each CUSIP, from its latest period.
# Where some filers write the same name in mixed case ("NVIDIA Corporation"
# for "NVIDIA CORPORATION"), that spelling is kept for display.
SQL_SECURITIES = """
CREATE OR REPLACE TABLE securities AS
WITH latest AS (
    SELECT cusip, max(period) AS period FROM cusip_holders GROUP BY cusip
),
names AS (
    SELECT upper(trim(i.CUSIP)) AS cusip, fp.period, i.NAMEOFISSUER AS name, i.TITLEOFCLASS AS class,
           nullif(trim(i.FIGI), '') AS figi
    FROM filing_parts fp
    JOIN raw_infotable i ON i.ACCESSION_NUMBER = fp.accession
    WHERE i.SSHPRNAMTTYPE = 'SH' AND coalesce(trim(i.PUTCALL), '') = ''
),
recent AS (
    SELECT n.* FROM names n JOIN latest l ON l.cusip = n.cusip AND l.period = n.period
),
counted AS (
    SELECT cusip, trim(name) AS name, count(*) AS n,
           regexp_replace(upper(name), '[^A-Z0-9]', '', 'g') AS name_key
    FROM recent GROUP BY ALL
),
top AS (
    SELECT DISTINCT ON (cusip) cusip, name AS name_filed, name_key
    FROM counted ORDER BY cusip, n DESC, name
),
mixed AS (
    SELECT DISTINCT ON (c.cusip) c.cusip, c.name AS name_mixed
    FROM counted c JOIN top t ON t.cusip = c.cusip AND t.name_key = c.name_key
    WHERE c.name <> upper(c.name)
    ORDER BY c.cusip, c.n DESC, c.name
),
classes AS (
    SELECT cusip, mode(trim(class)) AS title_of_class, mode(figi) AS figi FROM recent GROUP BY cusip
)
SELECT t.cusip, k.stock, t.name_filed, m.name_mixed, c.title_of_class, c.figi, l.period AS latest_period
FROM top t
JOIN latest l USING (cusip)
JOIN stock_keys k USING (cusip)
LEFT JOIN mixed m USING (cusip)
LEFT JOIN classes c USING (cusip)
"""

# A stock's name comes from the CUSIP most funds reported in its latest period:
# while a change of CUSIP is under way, that is often still the old one.
SQL_STOCKS = """
CREATE OR REPLACE TABLE stocks AS
WITH best AS (
    SELECT DISTINCT ON (k.stock) k.stock, k.cusip
    FROM stock_keys k
    JOIN cusip_holders ch USING (cusip)
    ORDER BY k.stock, ch.period DESC, ch.funds DESC, k.cusip
)
SELECT b.stock AS cusip, s.name_filed, s.name_mixed, s.title_of_class, s.figi, b.cusip AS named_from
FROM best b
JOIN securities s ON s.cusip = b.cusip
"""

STEPS = [
    ("submissions", SQL_SUBMISSIONS),
    ("periods", build_periods),
    ("filing_parts", SQL_FILING_PARTS),
    ("filings", SQL_FILINGS),
    ("managers", SQL_MANAGERS),
    ("positions", SQL_POSITIONS),
    ("price_check", SQL_PRICE_CHECK),
    ("cusip_holders", SQL_CUSIP_HOLDERS),
    ("cusip_changes", SQL_CUSIP_CHANGES),
    ("stock_keys", build_stock_keys),
    ("holders", SQL_HOLDERS),
    ("filers_total", SQL_FILERS_TOTAL),
    ("changes", SQL_CHANGES),
    ("stock_periods", SQL_STOCK_PERIODS),
    ("securities", SQL_SECURITIES),
    ("stocks", SQL_STOCKS),
]


def build_all(log=print) -> None:
    with connect() as con:
        log("Building the holdings model")
        for name, step in STEPS:
            started = time.monotonic()
            if callable(step):
                step(con)
            else:
                con.execute(step)
            rows = con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
            log(f"  {name}: {rows:,} rows ({time.monotonic() - started:.1f}s)")
