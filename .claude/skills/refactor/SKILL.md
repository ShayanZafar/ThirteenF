---
name: refactor
description: Measure what makes this code hard to change (complexity, duplication, dead code, churn) and apply the few cleanups with the best payoff, with scripts/verify passing; also fixes drift in the scripts, docs references and workflows. Runs monthly in CI as a pull request; type /refactor to run it locally.
disable-model-invocation: true
allowed-tools: Read Glob Grep Edit MultiEdit Write Bash(scripts/verify.sh *) Bash(scripts/verify.cmd *) Bash(.venv/bin/* *) Bash(.venv/Scripts/* *) Bash(pipx run *) Bash(npx *) Bash(git *) Bash(gh pr *) Bash(wc *) Bash(sort *) Bash(uniq *) Bash(head *) Bash(tail *) Bash(xargs *)
---

# Refactor for cheaper changes

The goal is code that the next feature can be added to with less reading and less risk: one place for each idea, functions you can hold in your head, no dead weight. Behavior never changes, and every number the app shows must still be rebuilt from the raw SEC tables. Show only the last lines of each command.

Use `.venv/bin/<tool>` on macOS and Linux, `.venv/Scripts/<tool>.exe` on Windows.

## 1. Measure (report only; none of these fail the run)

- Churn, the best predictor of where refactoring pays: `git log --since="90 days ago" --name-only --format="" -- src tests | sort | uniq -c | sort -rn | head -15`
- Long files: `git ls-files "src/**/*.py" | xargs wc -l | sort -n | tail -12`
- Complex functions: `.venv/bin/ruff check src --select C901,PLR0911,PLR0912,PLR0913,PLR0915 --exit-zero --output-format concise 2>&1 | tail -40`
- Dead code: `pipx run vulture src --min-confidence 80 2>&1 | tail -30` (leads to check by hand, not truth)
- Duplication: `npx --yes jscpd --min-tokens 70 --format python --reporters consoleFull src 2>&1 | tail -40`

## 2. Choose at most three cleanups

Rank by payoff divided by risk. Good candidates:
- The same logic in two or three places → one helper, with the existing tests covering each caller.
- A function with a C901 or PLR091x finding that does several things → split along the things it does, keeping names from the existing code.
- A module over ~400 lines with clear seams (for example a route handler that also shapes data) → split at the seam.
- Functions, branches and imports nothing uses → delete.

Rules:
- Never change behavior, SQL results or the HTML the templates produce; never add a dependency.
- Prefer the smallest change that removes the problem; formatting is whatever `ruff format` does to the files you touched.
- One cleanup per commit, each independently revertable, with a message that says what is now easier to change.

## 2b. Pin behavior before touching untested code

If the code you'll change has no test that would fail when its behavior changed, write characterization tests first: call it with the inputs it sees today (`tests/minidata.py` has a small data set; the reference CSV has published numbers) and assert the outputs you observe now. Commit them on their own, then refactor against them. If you can't characterize it cheaply, pick another cleanup.

## 3. Verify each one

After every cleanup, run `scripts/verify.sh 2>&1 | tail -40` (or `scripts/verify.cmd`). It must pass before the commit; tests marked `data` skipping is fine. If a cleanup needs more than a small test change to keep it green, revert it and pick another.

## 4. Setup files (mechanical fixes only; doesn't count against the three)

The files that steer sessions drift as the code changes. Fix what is mechanical, in one extra commit `setup: <what changed>`; judgment calls (shortening CLAUDE.md, merging docs) are for the user's `/tune`, so only report them.

- References: every `scripts/…`, `npm run …`, `docs/….md` and `.github/workflows/….yml` named in `CLAUDE.md`, `README.md`, `docs/` and `.claude/skills/` exists (Grep for them, confirm with Glob); fix the name, or delete the sentence if the thing is gone.
- Clickable scripts: each double-click action has a `.cmd`, a `.command` and a `.sh` (helpers exempt); `git ls-files --eol scripts` shows `i/lf` for all of them; `git ls-files -s scripts` shows `100755` for every `.sh` and `.command` (`git update-index --chmod=+x <file>` fixes it); a `.command` only `cd`s and `exec`s its `.sh`; the three do the same steps.
- Workflows: the names `auto-merge.yml` lists (`workflows:`, `ON_MAIN`) match the `name:` of real workflows; `uses:` versions agree across workflows.
- Sizes, reported in the PR body: `wc -w CLAUDE.md .claude/skills/*/SKILL.md`. `CLAUDE.md` is sent with every request; over 600 words, say so and what you'd move to the docs, but don't move it here.
## 5. Deliver

- In CI (`GITHUB_ACTIONS` is set): create a branch `refactor/<year>-<month>` from the current `main`, push it, and open one pull request with `gh pr create` titled "Monthly refactor: <one line>". The body lists each cleanup (what, why, the measurement it improves), the before/after numbers from step 1, and anything the reviewer should look at closely. If a PR for that branch already exists, push to it instead.
- Locally: leave the commits on the current branch and summarize the same way in the conversation.

If nothing clears the bar in step 2, say so and open no pull request. A quiet month is a good result.
