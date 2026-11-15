# Decisions: pages

Oldest first; add new ones at the bottom (format in [README.md](README.md)).

- 2026-10-12 — The list pages (Biggest changes, the watchlist, Accumulate) mark tickers that came from a fallback, with the source in a tooltip, as the stock page does (option B). Why: every number shows where it came from, and lists are where people compare stocks. (#16)
- 2026-10-19 — Every page shows the source health summary as a stale stamp while some data need has no reliable source, read from the health file on each request (option A), and the pages also say when the 13F data was last fetched from the SEC. Why: the pages show old data until the sources answer again, and the person reading them should know, as well as how fresh the last fetch is. (#25)
