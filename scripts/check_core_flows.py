"""Checks docs/core-flows.md, the map of core flows to their tests (the definition of done in CLAUDE.md).

Every flow names at least one test at each level (unit, integration, UI) or `—` for a gap; every named
test must still be declared in its file; and the gaps must equal the file's `Gaps allowed:` count, which
only ever goes down. Standard library only. scripts/verify.sh and scripts\\verify.cmd run it after the tests.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLOWS_FILE = "docs/core-flows.md"
HEADER = ["Flow", "Unit", "Integration", "UI"]
GAP = "—"
ALLOWED = re.compile(r"^Gaps allowed:\s*(\d+)\s*$", re.MULTILINE)
REFERENCE = re.compile(r"^`([^`]+)` › ([A-Za-z_]\w*)$")


class CheckFailed(Exception):
    """The file is missing or broken, or its gap count is off; the message says what to fix."""


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _rows(text: str) -> list[list[str]]:
    lines = [line for line in text.splitlines() if line.lstrip().startswith("|")]
    if len(lines) < 3 or _cells(lines[0]) != HEADER:
        raise CheckFailed(f"{FLOWS_FILE} needs a table headed | {' | '.join(HEADER)} | with one row per flow.")
    return [_cells(line) for line in lines[2:]]


def _declares(path: Path, name: str, cache: dict[Path, str]) -> bool:
    if path not in cache:
        cache[path] = path.read_text(encoding="utf-8")
    return re.search(rf"^[ \t]*(?:async[ \t]+)?def {re.escape(name)}\(", cache[path], re.MULTILINE) is not None


def _check_reference(root: Path, where: str, ref: str, cache: dict[Path, str]) -> tuple[str, str] | str:
    """The (file, test) a reference names, or what is wrong with it."""
    match = REFERENCE.match(ref)
    if not match:
        return f"{where}: {ref!r} is not a reference; write `tests/test_x.py` › test_name, or {GAP} for a gap."
    file, name = match.groups()
    path = root / file
    if not path.is_file():
        return f"{where}: {file} does not exist."
    if not _declares(path, name, cache):
        return f"{where}: {file} declares no test {name}."
    return file, name


def check(root: Path = ROOT) -> str:
    """The one-line summary when docs/core-flows.md holds; otherwise raises CheckFailed listing every problem."""
    flows_path = root / FLOWS_FILE
    if not flows_path.is_file():
        raise CheckFailed(f"{FLOWS_FILE} is missing: list the core flows and their tests there (see CLAUDE.md).")
    text = flows_path.read_text(encoding="utf-8")
    allowed_match = ALLOWED.search(text)
    if not allowed_match:
        raise CheckFailed(f"{FLOWS_FILE} has no 'Gaps allowed: N' line.")
    allowed = int(allowed_match.group(1))

    problems: list[str] = []
    tests: set[tuple[str, str]] = set()
    cache: dict[Path, str] = {}
    gaps = 0
    rows = _rows(text)
    for row in rows:
        flow = row[0]
        if len(row) != len(HEADER):
            problems.append(f"{flow or 'A row'}: the row has {len(row)} cells, not {len(HEADER)}.")
            continue
        if not flow:
            problems.append("A row has an empty Flow cell; say the flow in a person's words.")
            continue
        for level, cell in zip(HEADER[1:], row[1:], strict=True):
            where = f"{flow} ({level})"
            if not cell:
                problems.append(f"{where}: an empty cell; name a test or write {GAP} for a gap.")
            elif cell == GAP:
                gaps += 1
            else:
                for ref in (part.strip() for part in cell.split("<br>")):
                    found = _check_reference(root, where, ref, cache)
                    if isinstance(found, str):
                        problems.append(found)
                    else:
                        tests.add(found)

    if gaps < allowed:
        problems.append(f"Close the gap count: it went down to {gaps}, set Gaps allowed: {gaps} in {FLOWS_FILE}.")
    elif gaps > allowed:
        problems.append(
            f"A core flow lost a test: {gaps} gaps, but {FLOWS_FILE} allows {allowed}. "
            "Name a test at each level instead (gaps only ever go down)."
        )
    if problems:
        raise CheckFailed("\n".join(problems))
    return f"Core flows: {len(rows)} flows, {len(tests)} tests named, {gaps} gaps (allowed {allowed})"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    root = Path(args[0]) if args else ROOT
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # a Windows console that can't print — or ›
    try:
        print(check(root))
    except CheckFailed as failed:
        print(f"Core flows check failed:\n{failed}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
