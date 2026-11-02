---
paths:
  - ".github/workflows/**"
  - "docs/development.md"
---

# GitHub Actions

- `verify.yml` is the one always-on check and runs `scripts/verify.sh`; keep it fast and keep it on Ubuntu.
- A check that is slow, costly or only matters for some changes (another OS, live outside sources, long runs) is an **optional check**: `workflow_dispatch` plus `pull_request: types: [labeled]` with a job `if` on its own label, never a push or schedule trigger. Add it to the "Optional checks" table in `docs/development.md` with its label and when to run it (the owner's choice, Nov 2, 2026).
- When a change falls under an optional check's "run it when", add its label to the pull request and say so in the description.
