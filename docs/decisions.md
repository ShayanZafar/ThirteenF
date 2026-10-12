# Decisions

Choices the owner made, or that took their default after 7 days without an answer, newest first, one line each: the date, the decision, why, and its issue. Decisions still waiting are GitHub issues labelled `decision`; debt is labelled `debt` (the `backlog` skill says how to file and close both). A decision that is a standing rule also goes into CLAUDE.md. Never ask again about something recorded here.

Decisions made before Oct 12, 2026 are recorded inline in CLAUDE.md with their dates.

<!-- Format: - YYYY-MM-DD — <decision>. Why: <reason>. (#n) -->

- 2026-10-12 — A CUSIP OpenFIGI answers "not found" for takes the SEC's fails-to-deliver symbol (never the issuer-name match), marked provisional and from that source, and OpenFIGI is asked about it again on the next run (option B). Why: the fails-to-deliver files carry symbols for about 20,500 CUSIPs, so many stocks OpenFIGI misses get a ticker, and each says where it came from. (#14)
