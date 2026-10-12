"""Checks the instructions Claude Code loads on its own: CLAUDE.md and the rules files in .claude/rules/.

CLAUDE.md is sent with every request, so it stays short. A rules file loads only when Claude reads or
edits a file its `paths` globs match, so each must have `paths`, every glob must match a file git tracks
(a dead scope never loads), and it stays short too. Words are whitespace-separated, HTML comments left
out. Standard library only. scripts/verify.sh and scripts\\verify.cmd run it last.

The globs are read as Claude Code reads them, from the repo root: `**` is any number of folders (none
included), `*` and `?` are any characters and one character except `/`, and `{a,b}` expands to each
alternative (nesting allowed). `[` is not supported here, so the check rejects it; every other character
matches itself.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLAUDE_MD = "CLAUDE.md"
RULES_DIR = ".claude/rules"
# CLAUDE.md goes with every request, and long rule lists get followed less carefully. Raise this only
# with the owner's OK; move rules for one area to .claude/rules/ and explanations to docs/ instead.
MAX_CLAUDE_MD_WORDS = 600
# A rules file loads whenever one of its files is touched. Raise this only with the owner's OK.
MAX_RULES_WORDS = 500

HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
FRONTMATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)^---[ \t]*\r?$", re.DOTALL | re.MULTILINE)
PATHS_KEY = re.compile(r"^paths[ \t]*:(.*)$")
LIST_ITEM = re.compile(r"^[ \t]*-[ \t]+(.*?)[ \t]*$")
QUOTED = re.compile(r"\"([^\"]*)\"|'([^']*)'")
# An unquoted YAML value starting with one of these is YAML syntax, not text: the frontmatter fails to
# parse and Claude Code loads the rule at launch, as if it had no paths.
YAML_INDICATORS = tuple("*&!{[|>%@`")


class CheckFailed(Exception):
    """CLAUDE.md or a rules file breaks a rule; the message says what to fix."""


class GlobError(ValueError):
    """A glob this check can't read."""


def words(text: str) -> int:
    """Whitespace-separated words, HTML comments left out."""
    return len(HTML_COMMENT.sub(" ", text).split())


def _unquote(value: str) -> str:
    quoted = QUOTED.match(value)
    if quoted:
        return quoted.group(1) if quoted.group(1) is not None else quoted.group(2)
    if value.startswith(YAML_INDICATORS):
        raise GlobError(f"{value!r} must be quoted: YAML reads an unquoted {value[0]!r} as syntax")
    return value


def _split_outside_braces(text: str) -> list[str]:
    parts, depth, start = [], 0, 0
    for i, char in enumerate(text):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return parts


def frontmatter_paths(text: str) -> list[str] | None:
    """The `paths` globs of a rules file, or None when it has no frontmatter or no `paths` key.

    Reads the forms Claude Code accepts: a YAML list (block or `[...]`) or a comma-separated string."""
    match = FRONTMATTER.match(text.lstrip("\ufeff"))
    if not match:
        return None
    lines = match.group(1).splitlines()
    for i, line in enumerate(lines):
        key = PATHS_KEY.match(line)
        if not key:
            continue
        value = key.group(1).strip()
        if value.startswith("["):
            return [a or b for a, b in QUOTED.findall(value)]
        if value:
            return [part.strip() for part in _split_outside_braces(_unquote(value)) if part.strip()]
        globs = []
        for item_line in lines[i + 1 :]:
            if not item_line.strip() or item_line.lstrip().startswith("#"):
                continue
            item = LIST_ITEM.match(item_line)
            if not item:
                break
            globs.append(_unquote(item.group(1)))
        return globs
    return None


def expand_braces(pattern: str) -> list[str]:
    """Every pattern a glob's `{a,b}` groups expand to, in order."""
    start = pattern.find("{")
    if start == -1:
        if "}" in pattern:
            raise GlobError(f"{pattern!r} has a '}}' with no '{{'")
        return [pattern]
    depth = 0
    for end in range(start, len(pattern)):
        depth += {"{": 1, "}": -1}.get(pattern[end], 0)
        if depth == 0:
            break
    else:
        raise GlobError(f"{pattern!r} has a '{{' with no '}}'")
    alternatives = _split_outside_braces(pattern[start + 1 : end])
    if len(alternatives) < 2:
        raise GlobError(f"{pattern!r} has a brace group with one alternative; write it without braces")
    head, tail = pattern[:start], pattern[end + 1 :]
    return [expanded for alt in alternatives for expanded in expand_braces(head + alt + tail)]


def glob_regex(pattern: str) -> re.Pattern[str]:
    """The regex for one brace-free glob, matched against a whole path from the repo root."""
    if "[" in pattern:
        raise GlobError(f"{pattern!r} uses '[', which this check does not read; list the names instead")
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:[^/]*/)*")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out))


def dead_globs(globs: Iterable[str], tracked: Iterable[str]) -> list[str]:
    """Each expanded glob that matches no tracked path. Raises GlobError for one it can't read."""
    files = list(tracked)
    dead = []
    for glob in globs:
        for expanded in expand_braces(glob):
            regex = glob_regex(expanded)
            if not any(regex.fullmatch(path) for path in files):
                dead.append(expanded)
    return dead


def rules_file_problems(name: str, text: str, tracked: Iterable[str]) -> list[str]:
    """What is wrong with one rules file, if anything."""
    problems = []
    try:
        globs = frontmatter_paths(text)
        if not globs:
            problems.append(
                f"{name}: no `paths` in its frontmatter, so it loads at launch like CLAUDE.md; "
                "scope it to the files it is about."
            )
        else:
            for glob in dead_globs(globs, tracked):
                problems.append(
                    f"{name}: {glob!r} matches no file git tracks (a dead scope never loads); fix it or drop it."
                )
    except GlobError as error:
        problems.append(f"{name}: {error}.")
    count = words(text)
    if count > MAX_RULES_WORDS:
        problems.append(
            f"{name}: {count} words, over {MAX_RULES_WORDS}; move what explains rather than instructs to docs/, "
            "or split the topic."
        )
    return problems


def check(root: Path, tracked: Iterable[str]) -> str:
    """The one-line summary when CLAUDE.md and every rules file hold; otherwise raises CheckFailed listing
    every problem."""
    files = list(tracked)
    claude_md = root / CLAUDE_MD
    if not claude_md.is_file():
        raise CheckFailed(f"{CLAUDE_MD} is missing.")
    problems = []
    claude_words = words(claude_md.read_text(encoding="utf-8"))
    if claude_words > MAX_CLAUDE_MD_WORDS:
        problems.append(
            f"{CLAUDE_MD}: {claude_words} words, over {MAX_CLAUDE_MD_WORDS}; move rules for one area to "
            f"{RULES_DIR}/ and explanations to docs/."
        )
    rules = sorted((root / RULES_DIR).rglob("*.md")) if (root / RULES_DIR).is_dir() else []
    largest = 0
    for path in rules:
        text = path.read_text(encoding="utf-8")
        largest = max(largest, words(text))
        problems += rules_file_problems(path.relative_to(root).as_posix(), text, files)
    if problems:
        raise CheckFailed("\n".join(problems))
    return (
        f"Claude files: {CLAUDE_MD} {claude_words} words (max {MAX_CLAUDE_MD_WORDS}), "
        f"{len(rules)} rules files scoped, largest {largest} words (max {MAX_RULES_WORDS})"
    )


def tracked_files(root: Path) -> list[str]:
    """The paths git tracks, relative to the repo root, with forward slashes."""
    result = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True)
    return [path for path in result.stdout.decode("utf-8").split("\0") if path]


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    root = Path(args[0]) if args else ROOT
    try:
        print(check(root, tracked_files(root)))
    except CheckFailed as failed:
        print(f"Claude files check failed:\n{failed}")
        return 1
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"Claude files check failed: could not list the files git tracks ({error}).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
