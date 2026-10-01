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

**Positions.** Sum `INFOTABLE` rows for each manager, CUSIP and period, because one manager can list the same CUSIP on several lines.
- Shares: rows where `SSHPRNAMTTYPE` is `SH` and `PUTCALL` is empty. `PRN` rows are bond principal; options have `PUTCALL` set. Leave both out.
- Value: the same rows' `VALUE`, in dollars.

**Funds holding.** The number of distinct managers (CIKs) with shares above zero in the CUSIP for the period. 13f.info counts filings instead, so its numbers run slightly higher.

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

## Checks

**Implied price.** For each manager, CUSIP and period, implied price = value ÷ shares. Compare it with the median implied price across all managers holding that CUSIP in that period. Flag rows more than 3 times higher or lower than the median, leave them out of share totals, and list them on the data-check table with the manager's name.

**Shares against value.** For each CUSIP, compare the period's change in total shares with its change in total value. When shares move 25 points or more beyond value, flag the total. In the reference file, Q2 2026 share totals for AAPL, MSFT, NVDA, AMZN, GOOGL, META and TSLA jump 46% to 117% while value moves 2% to 35%.

**Late filers.** Until the next deadline passes, show the latest period as still arriving, with the count filed so far.

## Reference numbers

`docs/reference/13finfo-holdings.csv` holds 13f.info's published figures for eight test stocks (the same eight as the example watchlist), Q2 2024 to Q2 2026: filings, shares and value (options left out). They are rounded source values used to test this pipeline, not ground truth. The share totals include the suspect ones above on purpose, so the checks can be tested against them.
