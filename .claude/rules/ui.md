---
paths:
  - "src/thirteenf/web/**"
  - "design/**"
  - "design-system/**"
  - "tests/test_web.py"
  - "tests/test_signed.py"
  - "tests/test_story.py"
  - "tests/test_overview.py"
  - "tests/test_changes.py"
  - "tests/test_accumulate.py"
  - "tests/test_flows.py"
  - "tests/test_biggest_changes.py"
  - "tests/test_watchlist.py"
  - "tests/test_managers.py"
  - "tests/test_lookup.py"
  - "tests/test_freshness.py"
  - "tests/test_source_warning.py"
  - "docs/using-the-app.md"
---

# The pages: design system and copy

- Read `design-system/README.md` before writing any UI. The screens to build from are in `design/screens/`; `design/README.md` says how to use them in code.
- UI comes from the design system: use its CSS variables (`design-system/tokens.css`) and `tf-` classes (`design-system/components/bundle.css`), never hard-coded colors.
- `flow-in` and `flow-out` mean only more or fewer funds (money in or out).
- Signed numbers take the color of their sign through the `|signed` template filter: + in `flow-in` green, − in `flow-out` red (the user asked for this).
- Every number shows its as-of date and source with a freshness stamp.
- Every page shows the source health warning (`health.page_status()`) as a stale stamp while a data need has no reliable source, and the pages with a Source stamp say when the 13F data was last fetched (decision #25, Oct 19, 2026).
- Copy follows `design-system/README.md`: plain, dated, sentence case, no buy or sell language. One exception, asked for by the user (Oct 10, 2026): the Accumulate page names stocks to accumulate, because recommending them is the app's goal. It still says how each was chosen and that it is not advice.
