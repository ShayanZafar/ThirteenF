"""python -m thirteenf COMMAND (what scripts/run.sh and scripts\\run.cmd call) runs the right module."""

import runpy

import pytest

from thirteenf import __main__ as run


def test_a_short_name_runs_its_module_with_the_options_passed_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, list[str]]] = []

    def fake_run_module(name: str, **_: object) -> None:
        import sys

        calls.append((name, list(sys.argv)))
        raise SystemExit(0)

    monkeypatch.setattr(runpy, "run_module", fake_run_module)
    assert run.main(["tickers", "--retry-missing"]) == 0
    assert calls == [("thirteenf.tickers", ["python -m thirteenf.tickers", "--retry-missing"])]


def test_every_listed_command_is_a_module_that_runs_on_its_own() -> None:
    import importlib.util

    for name in run.COMMANDS:
        spec = importlib.util.find_spec(f"thirteenf.{name}")
        assert spec is not None, name


def test_an_unknown_or_missing_command_lists_the_commands(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run.main(["tikcers"]) == 2
    err = capsys.readouterr().err
    assert "Unknown command: tikcers" in err
    assert "tickers" in err and "prices" in err
    assert run.main([]) == 2
    assert run.main(["--help"]) == 0
