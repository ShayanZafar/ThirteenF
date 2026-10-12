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

or `.venv\Scripts\python -m pytest`. About 230 tests, two kinds:

- **Unit tests** need nothing loaded: period deadlines, the zip loader on a tiny fake zip, the OpenFIGI client against a fake OpenFIGI, the SEC client and the ticker fallbacks against a fake SEC (no test touches a live service or really waits), settings, and the seam tests, which load and build a small made-up data set (`tests/minidata.py`) end to end.
- **Data tests** (marked `data`) use the loaded database and skip until it exists. They check the model against 13f.info's published figures in `docs/reference/13finfo-holdings.csv`, render every page, and test the rankings against plain SQL.

| File | Covers |
| --- | --- |
| `tests/test_ingest.py` | Download links, the loader, the first data checks |
| `tests/test_model.py` | Filings, amendments, CUSIP changes, kinds, the reference numbers |
| `tests/test_web.py` | The stock page for many kinds of stock, both themes, no hard-coded colors |
| `tests/test_changes.py` | Biggest changes: rankings, the minimum, tabs |
| `tests/test_overview.py` | The overview and the watchlist (on a temporary watchlist file) |
| `tests/test_openfigi.py`, `tests/test_tickers.py` | Ticker mapping and search; a batch OpenFIGI refuses or fails going down the chain with no waiting, and OpenFIGI's later answer replacing a provisional ticker |
| `tests/test_ftd.py` | The SEC's fails-to-deliver files: links ordered by the date in their names, the newest 13 months, only missing files downloaded, loading as text with the header and trailer checks, the newest symbol winning, a refusing SEC left at once |
| `tests/test_ticker_fallbacks.py` | The issuer-name match, the chain after OpenFIGI, the fails-to-deliver symbol for a CUSIP OpenFIGI does not know, the stock page saying where a fallback's ticker came from, and when tickers count as unreliable |
| `tests/test_flows.py` | Net 13F flow, who moved, the typical stock, manager pages |
| `tests/test_signed.py` | Every signed number painted by its sign, on every page |
| `tests/test_periods.py`, `tests/test_config.py` | Deadlines and settings |
| `tests/test_seams.py` | Where steps meet: search redirects, build then tickers, an OpenFIGI that stays down never stopping the run |
| `tests/test_sec_retry.py` | The SEC client against a fake SEC: quick retries, blocks waited out however many come, the "Undeclared Automated Tool" page stopping at once, a caller with another source moving on at once, dropped downloads, what the command line prints |
| `tests/test_health.py` | The source health file: its shape, the 24-hour window, when a source and a data need count as unreliable |
| `tests/test_core_flows_check.py` | The core flows check on made-up files: a good map, each failure, the gap count both ways |

Run one file or one test: `scripts\test.cmd tests\test_flows.py -k alphabet`.

### Core flows

[core-flows.md](core-flows.md) lists what a person relies on the app for, and for each flow the tests at three levels: unit (one module, no network), integration (real routes, DuckDB on `tests/minidata.py` or the ingest pipeline together, outside services played by stand-ins) and UI (a real browser driving the running app; none yet). The `data` tests skip on pull requests, so they are not named there. `scripts/check_core_flows.py`, the last step of the verify check, fails when a flow lacks a level without counting it as a gap (`—`), when a named test no longer exists, or when the gaps differ from `Gaps allowed`: close a gap and lower the count in the same change; it never goes up.

## Before a change is done

```bat
scripts\verify.cmd
```

or `scripts/verify.sh`. It runs `ruff format --check`, `ruff check`, `mypy`, the licence check, the tests and the core flows check, in that order, and stops at the first failure. GitHub Actions runs the same script on every push to `main` and every pull request, so a change that passes here passes there. `ruff format src tests scripts` fixes formatting; the lint rules and the complexity ceiling (25, to be lowered as functions are split) are in `pyproject.toml`.

## Conventions

The rules in [../CLAUDE.md](../CLAUDE.md) apply to every change. In short:

- Nothing is specific to one company; every page works for any CUSIP.
- UI comes from the design system: its CSS variables and `tf-` classes, never hard-coded colors (a test checks). `flow-in` and `flow-out` mean only money in and money out. Signed numbers go through the `|signed` filter, which paints + green and − red with those two colors; SVG labels use `app-svg-pos` and `app-svg-neg`.
- Copy follows [../design-system/README.md](../design-system/README.md): plain, dated, sentence case, no buy or sell language. Every number shows its as-of date and source.
- Raw SEC files are never edited; everything is derived from the raw tables.
- A share total that fails a data check is never shown; the check is shown instead.

## Common changes

- **Change how a number is computed**: edit the SQL in `src/thirteenf/model/build.py`, run `python -m thirteenf.model`, update [13f-data.md](13f-data.md), and add a test.
- **Change a page**: the route is in `src/thirteenf/web/app.py`, its queries in `web/data.py`, its sentences in `web/story.py`, its markup in `web/templates/`. Shared pieces (change tags, meters, flow bars) are macros in `templates/_macros.html`.
- **Add a dependency**: add it to `pyproject.toml`, then run `scripts\setup.cmd` again.

## Continuous integration

The workflows are in `.github/workflows/`. The two that use Claude run on the `CLAUDE_CODE_OAUTH_TOKEN` repository secret (created with `claude setup-token`); without it they log a warning and finish green.

| Workflow | Runs | What it does |
| --- | --- | --- |
| `verify.yml` | Every push to `main` and every pull request | `scripts/verify.sh` on Ubuntu with Python 3.12, then a second test run that puts test coverage in the job summary (it never fails the build) |
| `codeql.yml` | Pushes and pull requests to `main`, and weekly | CodeQL's Python security and quality queries; findings appear under Security > Code scanning |
| `claude-code-review.yml` | A pull request opened, reopened or marked ready | Claude reviews it once and posts inline comments. Drafts, forks and Dependabot's pull requests are skipped |
| `claude-refactor.yml` | The 1st of each month, or from the Actions tab | Claude runs the `/refactor` skill and opens a pull request with at most three behavior-preserving cleanups |
| `mutation.yml` | The 1st of each month, or from the Actions tab | Mutation testing with mutmut (Linux only): lists the mutants no test noticed, in the job summary and the `mutmut-results` artifact. It never fails the build |

Dependabot (`.github/dependabot.yml`) opens monthly pull requests for the Python dependencies and the GitHub Actions versions.

## Claude Code skills

- `/verify` (`.claude/skills/verify/`) runs `scripts/verify.sh` (or `scripts\verify.cmd`) and reports only the failures. Claude runs it before each commit.
- `/refactor` (`.claude/skills/refactor/`) measures churn, complexity, duplication and dead code, then applies the few cleanups with the best payoff, each with the verify script passing. Type it to run it; the monthly workflow runs it in CI.

## Git

`data/`, `.venv/` and `mutants/` (mutmut's results) are ignored. Each finished phase or feature is one commit. A pull request fills in `.github/pull_request_template.md`: what changed and why, and how it was checked.
