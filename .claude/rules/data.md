---
paths:
  - "src/thirteenf/ingest/**"
  - "src/thirteenf/model/**"
  - "src/thirteenf/web/data.py"
  - "docs/13f-data.md"
  - "docs/reference/**"
  - "tests/minidata.py"
  - "tests/test_ingest.py"
  - "tests/test_model.py"
  - "tests/test_periods.py"
  - "tests/test_flows.py"
  - "tests/test_changes.py"
  - "tests/test_accumulate.py"
  - "tests/test_seams.py"
---

# The SEC data and the model

- Raw SEC files are never edited. Load them as they are and derive everything from them, so every number can be rebuilt from the raw tables.
- Never show a share total that fails the implied-price check in `docs/13f-data.md`; show the check instead.
- `docs/13f-data.md` says how every number is computed and which checks apply; `docs/reference/13finfo-holdings.csv` has published numbers for 8 stocks, used as test fixtures.
