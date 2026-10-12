# Decisions

Choices the owner made, or that took their default after 7 days without an answer, newest first, one line each: the date, the decision, why, and its issue. Decisions still waiting are GitHub issues labelled `decision`; debt is labelled `debt` (the `backlog` skill says how to file and close both). A decision that is a standing rule also goes into CLAUDE.md. Never ask again about something recorded here.

Decisions made before Oct 12, 2026 are recorded inline in CLAUDE.md with their dates.

<!-- Format: - YYYY-MM-DD — <decision>. Why: <reason>. (#n) -->

- 2026-10-12 — The list pages (Biggest changes, the watchlist, Accumulate) mark tickers that came from a fallback, with the source in a tooltip, as the stock page does (option B). Why: every number shows where it came from, and lists are where people compare stocks. (#16)
- 2026-10-12 — Tickers matched only by issuer name (unverified) stay out of the Accumulate list's cash-flow matching (option A, no change). Why: the page recommends stocks, and a wrong name match would recommend a different company; verified tickers from OpenFIGI or the fails-to-deliver data still count. (#15)
- 2026-10-12 — The update waits out every SEC block (`Retry-After`, else 10 minutes) with no limit per run, but stops at once on the "Undeclared Automated Tool" page. Why: the SEC is the only source of 13F data, so waiting on its own means nobody restarts anything; that page means `SEC_USER_AGENT` is wrong, which waiting can't fix. (#13)
- 2026-10-12 — A CUSIP OpenFIGI answers "not found" for takes the SEC's fails-to-deliver symbol (never the issuer-name match), marked provisional and from that source, and OpenFIGI is asked about it again on the next run (option B). Why: the fails-to-deliver files carry symbols for about 20,500 CUSIPs, so many stocks OpenFIGI misses get a ticker, and each says where it came from. (#14)
