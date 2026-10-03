# Development

## Running while you change things

```bat
scripts\start.cmd --reload
```

`--reload` restarts the server when Python code in `src/thirteenf/` changes; templates and CSS are picked up on the next page load. Without data, pages explain how to load it.

## Tests

```bat
scripts\test.cmd
```

or `.venv\Scripts\python -m pytest`. About 125 tests, two kinds:

- **Unit tests** need nothing loaded: period deadlines, the zip loader on a tiny fake zip, the OpenFIGI client against a fake OpenFIGI, settings.
- **Data tests** (marked `data`) use the loaded database and skip until it exists. They check the model against 13f.info's published figures in `docs/reference/13finfo-holdings.csv`, render every page, and test the rankings against plain SQL.

| File | Covers |
| --- | --- |
| `tests/test_ingest.py` | Download links, the loader, the first data checks |
| `tests/test_model.py` | Filings, amendments, CUSIP changes, kinds, the reference numbers |
| `tests/test_web.py` | The stock page for many kinds of stock, both themes, no hard-coded colors |
| `tests/test_changes.py` | Biggest changes: rankings, the minimum, tabs |
| `tests/test_overview.py` | The overview and the watchlist (on a temporary watchlist file) |
| `tests/test_openfigi.py`, `tests/test_tickers.py` | Ticker mapping and search |
| `tests/test_flows.py` | Net 13F flow, who moved, the typical stock, manager pages |
| `tests/test_periods.py`, `tests/test_config.py` | Deadlines and settings |

Run one file or one test: `scripts\test.cmd tests\test_flows.py -k alphabet`.

## Conventions

The rules in [../CLAUDE.md](../CLAUDE.md) apply to every change. In short:

- Nothing is specific to one company; every page works for any CUSIP.
- UI comes from the design system: its CSS variables and `tf-` classes, never hard-coded colors (a test checks). `flow-in` and `flow-out` mean only money in and money out.
- Copy follows [../design-system/README.md](../design-system/README.md): plain, dated, sentence case, no buy or sell language. Every number shows its as-of date and source.
- Raw SEC files are never edited; everything is derived from the raw tables.
- A share total that fails a data check is never shown; the check is shown instead.

## Common changes

- **Change how a number is computed**: edit the SQL in `src/thirteenf/model/build.py`, run `python -m thirteenf.model`, update [13f-data.md](13f-data.md), and add a test.
- **Change a page**: the route is in `src/thirteenf/web/app.py`, its queries in `web/data.py`, its sentences in `web/story.py`, its markup in `web/templates/`. Shared pieces (change tags, meters, flow bars) are macros in `templates/_macros.html`.
- **Add a dependency**: add it to `pyproject.toml`, then run `scripts\setup.cmd` again.

## Git

`data/` and `.venv/` are ignored. Each finished phase or feature is one commit on `main`.
