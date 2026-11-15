# Decisions

Choices the owner made, or that took their default after 7 days without an answer, one line each: the date, the decision, why, and its issue. They are split by topic so that pull requests adding decisions to different areas don't collide. Decisions still waiting are GitHub issues labelled `decision`; debt is labelled `debt` (the `backlog` skill says how to file and close both). A decision that is a standing rule also goes into CLAUDE.md, or into the `.claude/rules/` file for its area. Never ask again about something recorded here.

Decisions made before Oct 12, 2026 are recorded inline with their dates, in CLAUDE.md, `.claude/rules/` and the docs they concern.

| File | What it covers |
| --- | --- |
| [picks-and-backtest.md](picks-and-backtest.md) | The Accumulate rule, its labels, and how the backtest measures past lists |
| [prices.md](prices.md) | Daily price sources, which symbols are priced, free and paid keys |
| [tickers.md](tickers.md) | Mapping CUSIPs to tickers, fallbacks, and which tickers the picks may use |
| [sec-access.md](sec-access.md) | How the app asks the SEC for data and what it does when blocked |
| [pages.md](pages.md) | What the pages show: stamps, source marks, freshness |

Add a decision at the **bottom** of the file for its topic, in this format:

`- YYYY-MM-DD — <decision>. Why: <reason>. (#n)`

For a default, add "(default applied: no answer in 7 days)" before `(#n)`. When no topic fits, start a new file and add a row to the table above.
