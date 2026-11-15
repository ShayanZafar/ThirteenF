# Decisions: SEC access

Oldest first; add new ones at the bottom (format in [README.md](README.md)).

- 2026-10-12 — The update waits out every SEC block (`Retry-After`, else 10 minutes) with no limit per run, but stops at once on the "Undeclared Automated Tool" page. Why: the SEC is the only source of 13F data, so waiting on its own means nobody restarts anything; that page means `SEC_USER_AGENT` is wrong, which waiting can't fix. (#13)
