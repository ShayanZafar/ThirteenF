# 13F data: source, definitions and checks

## Source

- Page: https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets
- Documentation: https://www.sec.gov/files/form_13f_readme.pdf. Confirm table and field names against it before writing the loader.
- Since March 2024 each zip covers three months of filing dates: December to February, March to May, June to August, and September to November. Names look like `01jun2026-31aug2026_form13f.zip` (about 95 MB each). Older zips are named by quarter, like `2023q4_form13f.zip`.
- Take the download links from the page. Recent links sit under different folders (`/files/structureddata/...` and `/files/datastandardsinnovation/...`), so hand-built URLs break.
- Identify every request with the `SEC_USER_AGENT` environment variable and stay under 10 requests per second.

## Tables used

Each zip holds tab-separated files joined by `ACCESSION_NUMBER`:

| Table | Use | Key fields |
| --- | --- | --- |
| `SUBMISSION` | One row per filing | `CIK`, `PERIODOFREPORT`, `SUBMISSIONTYPE`, `FILING_DATE` |
| `COVERPAGE` | Manager and report details | `ISAMENDMENT`, `AMENDMENTTYPE`, `REPORTTYPE`, `FILINGMANAGER_NAME` |
| `SUMMARYPAGE` | Filing totals | `TABLEENTRYTOTAL`, `TABLEVALUETOTAL` |
| `INFOTABLE` | One row per holding line | `CUSIP`, `FIGI`, `NAMEOFISSUER`, `TITLEOFCLASS`, `VALUE`, `SSHPRNAMT`, `SSHPRNAMTTYPE`, `PUTCALL` |

Dates are text such as `30-JUN-2026`; parse them.

**Value units:** since January 3, 2023, `VALUE` is in dollars. Before that it was in thousands. Every period in this plan is after the change, but convert anyway if older zips are ever loaded.

## Definitions

**Period.** The quarter end in `PERIODOFREPORT`. Positions describe that day. Filings are due 45 days later, moved to the next business day when that falls on a weekend or holiday (Q2 2026: Aug 14, 2026).

**Current filing per manager and period.** Keep `13F-HR` and `13F-HR/A` filings (drop `13F-NT`, which has no holdings). For each CIK and period: start from the latest amendment whose `AMENDMENTTYPE` is `RESTATEMENT`, or the original filing if there is none, then add any later amendments whose type is `NEW HOLDINGS`.
- A `13F-HR` is always the original, even when its cover page says otherwise (one manager labels its only filing each quarter `NEW HOLDINGS`).
- A `13F-HR/A` with no `AMENDMENTTYPE` replaces the report, like a restatement (its entry count matches the original's).
- Read `CIK` as a number: the SEC writes the same manager both as `1539994` and `0001539994`.
- Read `CUSIP` upper-cased and trimmed; about 71,000 rows arrive in lower case.

**Positions.** Sum `INFOTABLE` rows for each manager, CUSIP and period, because one manager can list the same CUSIP on several lines.
- Shares: rows where `SSHPRNAMTTYPE` is `SH` and `PUTCALL` is empty. `PRN` rows are bond principal; options have `PUTCALL` set. Leave both out.
- Value: the same rows' `VALUE`, in dollars.

**Stocks and CUSIP changes.** A stock is identified by its current CUSIP. When a company replaces its CUSIP (a reverse split, a new holding company, a move abroad), the same funds report the new CUSIP from one period to the next. Treat it as one stock, decided Oct 2, 2026. A new CUSIP replaces an old one (held by at least 20 funds) when at least half of the new CUSIP's new holders are funds that left the old one, and those funds moved like a conversion: at least 20% of them hold new shares within 5% of the median exchange ratio, and their positions keep between 1/10 and 10 times their value. Either at least half of the funds that left the old CUSIP moved, or, for a change still under way at quarter end, at least 50 moved and half of them at the same ratio. At least 20 funds must move. Coincidences, such as index funds dropping one stock and adding another, fail the ratio test; a contingent value right paid in an acquisition fails the value test. The old CUSIP's history then counts toward the new one, with its shares converted at that ratio. Over the eight transitions this finds about 400 changes, among them Honeywell (1 new share for 2 old, Q2 2026), Exxon Mobil's new holding company (Q2 2026, under way), DuPont, Carnival and BlackRock.

**Funds holding.** The number of distinct managers (CIKs) with shares above zero in the stock (any of its CUSIPs) for the period. 13f.info counts filings instead, and its numbers run 4 to 10% higher (see Reference numbers).

**All 13F filers.** The number of distinct managers with a holdings report for the period. This is the tide to compare against: every Dec 31 it jumps, because managers that grew past $100M during the year file for the first time. A stock that gains 8% more holders at year-end may only be keeping pace.

**Share of all filers.** Funds holding ÷ all 13F filers, per period.

**Change against the tide.** A stock's percentage change in funds holding minus the percentage change in all 13F filers, in points. If funds holding rose 3.0% while all filers rose 1.2%, that is +1.8 pts. It ranks the Biggest changes page and sits beside every stock's own change.

**Market median.** The middle percentage change in funds holding across every stock held by at least 100 funds in both periods: what the typical stock did. The designs show a "watchlist median" in this place because they were drawn from eight stocks; the app uses the market median.

**Changes between two periods, per manager.**
- Opened: no shares last period, shares now.
- Sold out: shares last period, none now, and the manager filed for the new period.
- Added or trimmed: shares went up or down.
- Held: no change.
- Not yet filed: the manager held shares last period but has not filed for the new one. Count these separately; never call them sold out.

## Tickers

13F filings carry CUSIPs, not tickers. `python -m thirteenf.tickers` looks each CUSIP up once with the OpenFIGI mapping API and caches the answer, as returned, in the `openfigi` table. Each pass only covers the CUSIPs the one before did not match:

1. The CUSIP on the US composite listing (`ID_CUSIP`; codes that start with a letter are CINS codes, `ID_CINS`, used for foreign issuers).
2. The CUSIP on any exchange, then that listing's share class on the US composite listing (`ID_BB_GLOBAL_SHARE_CLASS_LEVEL`).
3. The FIGI filers wrote in `INFOTABLE`, as a FIGI and then as a share class.

CUSIPs whose check digit is wrong (about 5,900: filers' typos and placeholders such as `000000001`) are not sent, since OpenFIGI rejects them, but still get pass 3. A stock's ticker and kind (OpenFIGI's security type: Common Stock, ETP, ADR, REIT, ...) come from its current CUSIP, or else its most recent earlier one. As of Oct 2026, 99% of stocks held by 100 or more funds have a ticker; most of the rest were acquired or delisted in 2026.

The key, free from openfigi.com, goes in `data/settings.toml` (`openfigi_api_key`); an `OPENFIGI_API_KEY` environment variable overrides it.

## Checks

**Implied price.** For each manager, CUSIP and period, implied price = value ÷ shares. Compare it with the median implied price across all managers holding that CUSIP in that period. Flag rows more than 3 times higher or lower than the median, leave them out of share totals, and list them on the data-check table with the manager's name.

One exception, decided Oct 1, 2026: some managers still file `VALUE` in thousands, the rule before 2023 (336 to 540 managers per period, falling as they switch). Their implied price is about 1/1000 of the median while their share counts are right. A row whose implied price × 1000 falls within 3 times the median is "value in thousands": its shares stay in the totals, its value counts × 1000, and it is still listed on the data-check table. Leaving these rows out would cut share totals by about 5% and make them drift upward as managers switch to dollars.

**Shares against value.** For each CUSIP, compare the period's change in total shares with its change in total value, allowing for the change in price per share (the median implied price): shares should move by (1 + value change) ÷ (1 + price change). When shares move 25 points or more beyond that, flag the total. Without the price adjustment, any stock whose price moves 25% in a quarter would be flagged, as would every split. In the reference file, Q2 2026 share totals for AAPL, MSFT, NVDA, AMZN, GOOGL, META and TSLA jump 46% to 117% while value moves 2% to 35%.

**Late filers.** Until the next deadline passes, show the latest period as still arriving, with the count filed so far.

## Reference numbers

`docs/reference/13finfo-holdings.csv` holds 13f.info's published figures for eight test stocks (the same eight as the example watchlist), Q2 2024 to Q2 2026: filings, shares and value (options left out). They are rounded source values used to test this pipeline, not ground truth. The share totals include the suspect ones above on purpose, so the checks can be tested against them.

Measured against the SEC data sets (Oct 1, 2026):

- Funds holding runs 4 to 10% below the reference's filings count. Counting every filing in the data sets that lists the stock, its options or its notes, superseded amendments included, still falls 1 to 7% short, so 13f.info counts filings the data sets do not hold. Q2 2026 is about 2 points further behind because filings made after Aug 31 arrive in the next zip.
- The change from period to period agrees within 2 points for every stock and period. The tests check that, and the level within 11% (worst case: Shopify, Q2 2024, 10.1% below).
- Share totals agree within 0.5% in most periods. The reference's Q2 2026 totals for the seven largest stocks and Microsoft's Q2 and Q3 2025 totals imply prices far from the market, so they are suspect; the SEC data sets show no such jumps.
