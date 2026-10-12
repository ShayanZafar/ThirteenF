"""scripts/check_claude_files.py: CLAUDE.md's size and the rules files' scopes and sizes, on made-up repos."""

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "check_claude_files", Path(__file__).resolve().parent.parent / "scripts" / "check_claude_files.py"
)
assert _spec and _spec.loader
claude_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(claude_check)

TRACKED = [
    "CLAUDE.md",
    "README.md",
    "src/app/web/app.py",
    "src/app/web/templates/base.html",
    "src/app/ingest/sec.py",
    "tests/test_web.py",
    "docs/sources.md",
]
RULE = '---\npaths:\n  - "src/app/web/**"\n  - "tests/test_web.py"\n---\n\n# The pages\n\n- Use the tokens.\n'


def _repo(tmp_path: Path, claude_md: str = "# App\n\nShort.\n", rules: dict[str, str] | None = None) -> Path:
    (tmp_path / "CLAUDE.md").write_text(claude_md, encoding="utf-8")
    for name, text in (rules if rules is not None else {"ui.md": RULE}).items():
        path = tmp_path / ".claude" / "rules" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def _matches(glob: str, path: str) -> bool:
    return any(claude_check.glob_regex(expanded).fullmatch(path) for expanded in claude_check.expand_braces(glob))


def test_words_are_whitespace_separated_and_skip_html_comments():
    assert claude_check.words("One two\nthree\t four") == 4
    assert claude_check.words("Kept <!-- not\ncounted at all --> kept, too") == 3


@pytest.mark.parametrize(
    ("glob", "path", "expected"),
    [
        ("src/app/web/**", "src/app/web/templates/base.html", True),
        ("src/app/web/**", "src/app/webby/app.py", False),
        ("src/**/*.py", "src/app.py", True),
        ("src/**/*.py", "src/app/web/app.py", True),
        ("**/*.html", "src/app/web/templates/base.html", True),
        ("**/*.html", "index.html", True),
        ("*.md", "README.md", True),
        ("*.md", "docs/sources.md", False),
        ("tests/test_*.py", "tests/test_web.py", True),
        ("tests/test_*.py", "tests/unit/test_web.py", False),
        ("tests/test_we?.py", "tests/test_web.py", True),
        ("tests/test_we?.py", "tests/test_we/.py", False),
        ("docs/sources.md", "docs/sources_md", False),
        ("src/app/{web,ingest}/*.py", "src/app/ingest/sec.py", True),
        ("src/**/*.{py,html}", "src/app/web/templates/base.html", True),
        ("src/**/*.{py,html}", "src/app/web/app.css", False),
    ],
)
def test_globs_match_whole_paths_from_the_repo_root(glob, path, expected):
    assert _matches(glob, path) is expected


def test_braces_expand_in_order_and_nest():
    assert claude_check.expand_braces("a/{b,c}/{d,e}.py") == ["a/b/d.py", "a/b/e.py", "a/c/d.py", "a/c/e.py"]
    assert claude_check.expand_braces("x.{py,{md,txt}}") == ["x.py", "x.md", "x.txt"]


@pytest.mark.parametrize("glob", ["src/{web,ingest", "src/web}/*.py", "src/{web}/*.py"])
def test_unbalanced_or_single_brace_groups_are_refused(glob):
    with pytest.raises(claude_check.GlobError):
        claude_check.expand_braces(glob)


def test_a_bracket_expression_is_refused():
    with pytest.raises(claude_check.GlobError, match="does not read"):
        claude_check.glob_regex("tests/test_[ab].py")


def test_paths_are_read_from_a_block_list_a_flow_list_or_a_string():
    block = "---\npaths:\n  - \"src/**\"\n  - 'docs/*.md'  # the docs\n  - tests/test_web.py\n---\nBody\n"
    assert claude_check.frontmatter_paths(block) == ["src/**", "docs/*.md", "tests/test_web.py"]
    flow = '---\npaths: ["src/**/*.{py,html}", "docs/*.md"]\n---\n'
    assert claude_check.frontmatter_paths(flow) == ["src/**/*.{py,html}", "docs/*.md"]
    string = '---\npaths: "src/**/*.{py,html}, docs/*.md"\n---\n'
    assert claude_check.frontmatter_paths(string) == ["src/**/*.{py,html}", "docs/*.md"]
    crlf = '---\r\nother: 1\r\npaths:\r\n  - "src/**"\r\n---\r\nBody\r\n'
    assert claude_check.frontmatter_paths(crlf) == ["src/**"]


def test_no_frontmatter_or_no_paths_reads_as_none():
    assert claude_check.frontmatter_paths("# Rules\n\n- Always.\n") is None
    assert claude_check.frontmatter_paths("---\ndescription: x\n---\n# Rules\n") is None


def test_an_unquoted_glob_that_yaml_reads_as_syntax_is_refused():
    with pytest.raises(claude_check.GlobError, match="must be quoted"):
        claude_check.frontmatter_paths("---\npaths:\n  - **/*.py\n---\n")


def test_good_files_pass_with_one_line(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(claude_check, "tracked_files", lambda root: TRACKED)
    assert claude_check.main([str(_repo(tmp_path))]) == 0
    out = capsys.readouterr().out
    assert out.count("\n") == 1
    assert out.startswith("Claude files: CLAUDE.md 3 words (max 600), 1 rules files scoped, largest ")


def test_claude_md_over_the_limit_fails(tmp_path):
    claude_md = "# App\n\n" + "word " * claude_check.MAX_CLAUDE_MD_WORDS
    with pytest.raises(claude_check.CheckFailed, match=r"CLAUDE\.md: 602 words, over 600"):
        claude_check.check(_repo(tmp_path, claude_md), TRACKED)


def test_html_comments_do_not_count_toward_the_limit(tmp_path):
    claude_md = "# App\n\n<!-- " + "note " * 1000 + "-->\n"
    assert "CLAUDE.md 2 words" in claude_check.check(_repo(tmp_path, claude_md), TRACKED)


def test_a_missing_claude_md_fails(tmp_path):
    with pytest.raises(claude_check.CheckFailed, match=r"CLAUDE\.md is missing"):
        claude_check.check(tmp_path, TRACKED)


def test_a_rules_file_without_paths_fails(tmp_path):
    repo = _repo(tmp_path, rules={"always.md": "# Always\n\n- Loaded at launch.\n"})
    with pytest.raises(claude_check.CheckFailed, match=r"\.claude/rules/always\.md: no `paths`"):
        claude_check.check(repo, TRACKED)


def test_a_glob_matching_no_tracked_file_fails_and_names_the_expansion(tmp_path):
    rule = '---\npaths:\n  - "src/app/{web,gone}/*.py"\n---\n# Rules\n'
    with pytest.raises(claude_check.CheckFailed, match=r"'src/app/gone/\*\.py' matches no file git tracks") as failed:
        claude_check.check(_repo(tmp_path, rules={"ui.md": rule}), TRACKED)
    assert "src/app/web" not in str(failed.value)


def test_a_rules_file_over_the_limit_fails(tmp_path):
    rule = RULE + "word " * claude_check.MAX_RULES_WORDS
    with pytest.raises(claude_check.CheckFailed, match=r"\.claude/rules/ui\.md: \d+ words, over 500"):
        claude_check.check(_repo(tmp_path, rules={"ui.md": rule}), TRACKED)


def test_rules_files_in_subfolders_are_checked_and_every_problem_is_listed(tmp_path):
    rules = {"ui.md": RULE, "area/sub.md": "# No paths\n", "bad.md": '---\npaths:\n  - "src/{web"\n---\n'}
    with pytest.raises(claude_check.CheckFailed) as failed:
        claude_check.check(_repo(tmp_path, rules=rules), TRACKED)
    message = str(failed.value)
    assert ".claude/rules/area/sub.md: no `paths`" in message
    assert ".claude/rules/bad.md: 'src/{web' has a '{' with no '}'" in message
    assert ".claude/rules/ui.md" not in message


def test_no_rules_folder_is_fine(tmp_path):
    assert "0 rules files" in claude_check.check(_repo(tmp_path, rules={}), TRACKED)


def test_a_folder_git_cannot_list_fails_with_one_message(tmp_path, capsys):
    assert claude_check.main([str(_repo(tmp_path))]) == 1
    assert capsys.readouterr().out.startswith("Claude files check failed: could not list the files git tracks")
