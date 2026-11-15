# Decisions: tickers

Oldest first; add new ones at the bottom (format in [README.md](README.md)).

- 2026-10-12 — A CUSIP OpenFIGI answers "not found" for takes the SEC's fails-to-deliver symbol (never the issuer-name match), marked provisional and from that source, and OpenFIGI is asked about it again on the next run (option B). Why: the fails-to-deliver files carry symbols for about 20,500 CUSIPs, so many stocks OpenFIGI misses get a ticker, and each says where it came from. (#14)
- 2026-10-12 — Tickers matched only by issuer name (unverified) stay out of the Accumulate list's cash-flow matching (option A, no change). Why: the page recommends stocks, and a wrong name match would recommend a different company; verified tickers from OpenFIGI or the fails-to-deliver data still count. (#15)
