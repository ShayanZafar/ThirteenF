---
name: verify
disable-model-invocation: true
description: Run ThirteenF's one check (ruff format, ruff lint, mypy, pytest) and report only failures. A commit hook runs it before each commit; type /verify to run it yourself.
---

A commit hook runs this same check before every `git commit` and blocks the commit when it fails, so there is no need to run it before committing; run it directly while working, to check a step.

Run the project's check script from the repo root, showing only the end of the output:

- Windows: `scripts/verify.cmd 2>&1 | tail -40`
- macOS/Linux: `scripts/verify.sh 2>&1 | tail -40`

It runs ruff format --check, ruff check, mypy, pip-licenses (every dependency must carry a free, open-source licence; a failure names the package and its licence, which means replacing the package, not widening the allow-list), pytest, the core flows check (`scripts/check_core_flows.py`), then the Claude files check (`scripts/check_claude_files.py`: CLAUDE.md at most 600 words, each `.claude/rules/` file scoped to tracked files and at most 500), and stops at the first step that fails. Tests marked `data` skip when `data/thirteenf.duckdb` is missing; that's expected. CI runs the same script on every push to main and every pull request.

Report which step failed and, for each failure, the file, line and message (for tests: the test name and the assertion line). Don't paste the full log. For a formatting failure in files you changed, run `.venv/Scripts/ruff.exe format src tests` (or `.venv/bin/ruff`) and re-check.

If a step fails because of the change being committed, fix it before committing. If it fails for an unrelated reason, say so and stop; don't change unrelated code to make it pass.
