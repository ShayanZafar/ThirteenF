"""scripts/check_core_flows.py: the map of core flows to unit, integration and UI tests, on made-up repos."""

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "check_core_flows", Path(__file__).resolve().parent.parent / "scripts" / "check_core_flows.py"
)
assert _spec and _spec.loader
flows_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(flows_check)

TESTS = {
    "tests/test_a.py": "def test_unit():\n    pass\n\n\nclass TestB:\n    def test_inside(self):\n        pass\n",
    "tests/test_b.py": "async def test_async():\n    pass\n\n\ndef test_integration():\n    pass\n",
}
ROWS = [
    "| Refresh the data | `tests/test_a.py` › test_unit | `tests/test_b.py` › test_integration<br>`tests/test_a.py` › test_inside | — |",
    "| Look up a stock | `tests/test_b.py` › test_async | — | — |",
]


def _repo(tmp_path: Path, rows: list[str] = ROWS, allowed: str | None = "3") -> Path:
    for name, text in TESTS.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text, encoding="utf-8")
    lines = ["# Core flows", "", "What this file is.", ""]
    if allowed is not None:
        lines += [f"Gaps allowed: {allowed}", ""]
    lines += ["| Flow | Unit | Integration | UI |", "|---|---|---|---|", *rows]
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "core-flows.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tmp_path


def test_a_complete_map_passes_with_one_line(tmp_path, capsys):
    assert flows_check.main([str(_repo(tmp_path))]) == 0
    assert capsys.readouterr().out == "Core flows: 2 flows, 4 tests named, 3 gaps (allowed 3)\n"


def test_a_missing_file_fails(tmp_path, capsys):
    assert flows_check.main([str(tmp_path)]) == 1
    assert "docs/core-flows.md is missing" in capsys.readouterr().out


def test_a_missing_gaps_allowed_line_fails(tmp_path):
    with pytest.raises(flows_check.CheckFailed, match="no 'Gaps allowed: N' line"):
        flows_check.check(_repo(tmp_path, allowed=None))


def test_an_empty_cell_fails(tmp_path):
    rows = [ROWS[0], "| Look up a stock | `tests/test_b.py` › test_async |  | — |"]
    with pytest.raises(flows_check.CheckFailed, match=r"Look up a stock \(Integration\): an empty cell"):
        flows_check.check(_repo(tmp_path, rows, allowed="2"))


def test_a_reference_to_a_missing_file_fails(tmp_path):
    rows = [ROWS[0], "| Look up a stock | `tests/test_gone.py` › test_async | — | — |"]
    with pytest.raises(flows_check.CheckFailed, match=r"Look up a stock \(Unit\): tests/test_gone.py does not exist"):
        flows_check.check(_repo(tmp_path, rows))


def test_a_test_that_no_longer_exists_fails(tmp_path):
    rows = [ROWS[0], "| Look up a stock | `tests/test_b.py` › test_renamed | — | — |"]
    with pytest.raises(flows_check.CheckFailed, match=r"tests/test_b\.py declares no test test_renamed"):
        flows_check.check(_repo(tmp_path, rows))


def test_a_cell_that_is_not_a_reference_fails(tmp_path):
    rows = [ROWS[0], "| Look up a stock | test_async | — | — |"]
    with pytest.raises(flows_check.CheckFailed, match="'test_async' is not a reference"):
        flows_check.check(_repo(tmp_path, rows))


def test_fewer_gaps_than_allowed_asks_to_close_the_count(tmp_path):
    with pytest.raises(
        flows_check.CheckFailed, match=r"(?i)close the gap count: it went down to 3, set Gaps allowed: 3"
    ):
        flows_check.check(_repo(tmp_path, allowed="4"))


def test_more_gaps_than_allowed_means_a_flow_lost_a_test(tmp_path, capsys):
    rows = [ROWS[0], "| Look up a stock | — | — | — |"]
    assert flows_check.main([str(_repo(tmp_path, rows))]) == 1
    assert "A core flow lost a test: 4 gaps, but docs/core-flows.md allows 3" in capsys.readouterr().out
