# Using the app

Every page answers one question first, then shows the evidence. Every number carries its date: the stamps under each title give the quarter end the positions describe, how many days ago that was, and the source.

## Search

The search box in the top bar, and the big one on Look up a stock, take a ticker (`NVDA`, `BRK.B`), a company name (`Shopify`, `Berkshire Hathaway class A`), a CUSIP (`82509L107`) or a manager (`Vanguard`). Matches appear as you type; use the arrow keys and Enter, or click. An exact ticker, CUSIP or name opens the stock's page directly; otherwise you get a list, most widely held first.

## Overview

Your watchlist for the latest quarter. It starts from the example in `config/watchlist.csv`; add stocks with the box under the table, from search results, or with **Add to watchlist** on a stock's page, and remove them with **Remove**.

For each stock: funds holding, the change since last quarter, the change against the typical stock (an ETF against the typical ETF), a sparkline of every quarter, the streak, and the two-year change. The data check below lists each share total, how many reports the price check left out of it, and a **Check** stamp in place of any total that fails.

## Look up a stock

From the top of the page down:

- **The answer**: more or fewer funds than last quarter, the streak, and how that compares with the typical stock and with all 13F filers.
- **Key figures**: funds holding, the distance from the peak (or low), shares held, the net 13F flow, and the change against the typical stock and against all filers.
- **Funds holding by filing period**: one bar per quarter, with the change under each.
- **Net 13F flow by filing period**: shares bought minus sold each quarter, valued at the quarter-end price. Up is money in, down is money out.
- **Who added, who left**: the biggest moves as flow bars, then every manager whose position changed: New, Add, Trim or Exit, the change in shares (and as a percentage of their position), the value, the position's weight in their reported portfolio (with last quarter's weight), the dollar flow, and when they filed. The 25 largest moves show first; **Show all** lists every one. Each manager links to their page.
- **Where it sits in each book**: the managers with the largest share of their portfolio in the stock, among those with 10 or more positions. A big weight in a concentrated book says more than a big dollar amount in an index fund's.
- **Every filing period**: the table behind the charts.
- **Data check**: share totals that failed a check, and the reports the price check left out.

## Biggest changes

Every stock held by at least 100 funds in both periods, ranked by its change in funds holding.

- **Tabs**: **All** (the default) mixes stocks, ETFs and other securities; **Stocks** and **ETFs** show one kind each.
- **Rank by**: against the tide (the stock's change minus the change in all 13F filers, in points), or the plain change in the number of funds.
- **Period**, **minimum funds holding** and **rows** are in the filter bar. Each row links to the stock's page.

## Managers

**Managers** lists the largest 13F filers for the latest quarter, with a search box for any of them. A manager's page shows their reported 13F portfolio, number of positions, the share of the ten largest and their net buying, the biggest moves, and every position with its weight and its change from the quarter before. Pick another quarter in **Period**; **Download CSV** gives the full list, and the link under the title opens the filing on sec.gov.

## Reading the numbers

- **Green and red**: a number with a + is green and a number with a − is red, the colors of the bars and triangles. A portfolio's value also moves with prices, so on the Managers page green or red is not all buying and selling.
- **Funds holding** counts managers (one per SEC CIK) with shares in the stock at the quarter end. Options and bond principal are left out.
- **The tide**: every Dec 31 most stocks gain holders, because managers that grew past $100M file their first 13F. Compare a stock with all 13F filers, or with the typical stock, rather than with zero.
- **Typical stock, typical ETF**: the middle change in funds holding across every stock (or ETF) held by at least 100 funds in both quarters.
- **Net 13F flow**: shares bought minus sold, at the quarter-end price, counting only managers with complete reports in both quarters. A manager filing for the first time has not bought, and one that has not filed yet has not sold.
- **Weight in book**: a position's value as a share of the manager's reported 13F portfolio (long positions in US-listed securities only).
- **Still arriving**: the latest quarter keeps gaining late filers until the data reaches the next quarter's filing deadline.
- **Check**: a share total is hidden when it fails a data check, and a manager's report is marked when its value per share is far from everyone else's. The rules are in [13f-data.md](13f-data.md).
- **Change of CUSIP**: when a company replaces its CUSIP (a reverse split, a new holding company, a move abroad), its history continues under the new one, and the stock's page says so.

13F covers long positions only: no shorts, no cash, and no holdings outside US-listed securities. It is not advice, and the app never says buy or sell.
