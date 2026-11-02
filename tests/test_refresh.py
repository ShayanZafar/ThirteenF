"""The recurring refresh (python -m thirteenf.refresh): one update at a time, a build that
stops part way changes nothing, and each run says what entered and left the Accumulate list,
on the command line, in data/refresh-summary.txt and on the Accumulate page."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import Page, expect
from test_accumulate import AMZN, MSFT, accumulate_db  # noqa: F401  (the fixture: made-up financials and tickers)

from thirteenf import config, refresh, runlock
from thirteenf.db import connect
from thirteenf.ingest import __main__ as ingest
from thirteenf.model import build
from thirteenf.signals import accumulate
from thirteenf.signals.accumulate import RunChange
from thirteenf.web import story
from thirteenf.web.app import app

RUN_1 = datetime(2025, 1, 20, 6, tzinfo=UTC)
RUN_2 = datetime(2025, 1, 21, 6, tzinfo=UTC)


@pytest.fixture(autouse=True)
def own_data_dir(tmp_path, monkeypatch):
    """The lock and the summary in a folder of the test's own, never data/."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")


def _pick(cusip: str, ticker: str, name: str, rank: int = 1) -> dict:
    return {"cusip": cusip, "ticker": ticker, "name_filed": name.upper(), "name_mixed": name, "rank": rank}


def _change(**kw) -> RunChange:
    period = datetime(2024, 12, 31).date()
    base = dict(
        run_at=RUN_2,
        previous_at=RUN_1,
        period=period,
        previous_period=period,
        entered=[],
        left=[],
        stayed=0,
        rules_changed=False,
    )
    return RunChange(**(base | kw))


# --- Unit ------------------------------------------------------------------------------------


def test_only_one_update_holds_the_lock_and_it_is_free_again_after():
    with runlock.held("first"), pytest.raises(runlock.UpdateRunning, match="first"), runlock.held("second"):
        pass
    with runlock.held("third"):
        pass


def test_a_second_process_is_refused_while_the_first_holds_the_lock():
    """The lock is the operating system's (fcntl, or msvcrt on Windows), across processes."""
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "from thirteenf import runlock\nwith runlock.held('update-data'):\n    print('held', flush=True)\n    input()",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        env=os.environ | {"THIRTEENF_DATA": str(config.DATA_DIR)},
    )
    try:
        assert holder.stdout is not None and holder.stdout.readline().strip() == "held"
        with pytest.raises(runlock.UpdateRunning), runlock.held("refresh"):
            pass
    finally:
        holder.communicate("\n", timeout=30)
    with runlock.held("refresh"):  # free again once the other process ends
        pass


def test_the_summary_names_what_entered_and_left():
    change = _change(
        entered=[_pick(AMZN, "T023", "Amazon.com Inc")], left=[_pick(MSFT, "T594", "Microsoft Corp")], stayed=3
    )
    text = story.run_change(change)
    assert text == (
        "Since the update of Jan 20, 2025, 1 stock entered: Amazon.com Inc (T023); "
        "1 left: Microsoft Corp (T594). 3 stayed on it."
    )
    plain = refresh.describe(change, picks=4)
    assert "Entered since the run of Jan 20, 2025: T023 (Amazon.com Inc)." in plain
    assert "Left since the run of Jan 20, 2025: T594 (Microsoft Corp)." in plain


def test_a_new_quarter_and_a_change_of_thresholds_are_said_so():
    change = _change(previous_period=datetime(2024, 9, 30).date(), rules_changed=True)
    text = story.run_change(change)
    assert text.startswith("The list moved to new 13F data, positions at Dec 31, 2024.")
    assert "no stock entered or left" in text and "thresholds changed" in text
    assert "New 13F quarter: the list moved from Q3 2024 to Q4 2024." in refresh.describe(change, 0)
    assert refresh.describe(None, 2).endswith("The next run will say what entered and left.")


# --- Integration -----------------------------------------------------------------------------


def _update_that_drops_microsoft(calls: list[str]):
    """Stands in for the whole update: the second one brings a 10-K with negative free cash flow."""

    def run(args: argparse.Namespace) -> int:
        calls.append("update")
        with connect() as con:
            if len(calls) == 2:
                con.execute("UPDATE stock_cash_flows SET free_cash_flow = -1 WHERE cusip = ?", [MSFT])
            accumulate.save_run(con, RUN_1 if len(calls) == 1 else RUN_2)
        return 0

    return run


def test_each_refresh_says_what_left_since_the_run_before(accumulate_db, monkeypatch, capsys):  # noqa: F811
    accumulate_db()
    calls: list[str] = []
    monkeypatch.setattr(ingest, "run", _update_that_drops_microsoft(calls))
    assert refresh.run([]) == 0
    assert "The next run will say" in refresh.summary_path().read_text(encoding="utf-8")
    assert refresh.run([]) == 0
    summary = refresh.summary_path().read_text(encoding="utf-8")
    assert "Accumulate list for Q4 2024: 0 picks." in summary
    assert "Left since the run of Jan 20, 2025: T594" in summary
    assert "Left since the run" in capsys.readouterr().out


def test_a_refresh_waits_for_no_one_while_another_update_runs(accumulate_db, monkeypatch, capsys):  # noqa: F811
    accumulate_db()
    calls: list[str] = []
    monkeypatch.setattr(ingest, "run", _update_that_drops_microsoft(calls))
    with runlock.held("update-data"):
        assert refresh.run([]) == 3
    assert calls == []
    assert "Another update is running (update-data" in capsys.readouterr().err


def test_a_build_that_stops_part_way_leaves_the_model_as_it_was(accumulate_db, monkeypatch):  # noqa: F811
    accumulate_db()
    with connect() as con:
        before = con.execute("SELECT count(*) FROM stock_periods").fetchone()

    def broken(con) -> None:
        con.execute("DROP TABLE stock_periods")
        raise RuntimeError("the disk is full")

    monkeypatch.setattr(build, "STEPS", [*build.STEPS[:5], ("broken", broken)])
    with pytest.raises(RuntimeError, match="disk is full"):
        build.build_all(log=lambda *_: None)
    with connect() as con:
        assert con.execute("SELECT count(*) FROM stock_periods").fetchone() == before


def test_the_page_says_what_changed_since_the_last_update(accumulate_db, monkeypatch):  # noqa: F811
    accumulate_db()
    calls: list[str] = []
    monkeypatch.setattr(ingest, "run", _update_that_drops_microsoft(calls))
    html = TestClient(app).get("/accumulate").text
    assert "Since the last update" not in html  # no runs yet
    refresh.run([])
    refresh.run([])
    html = TestClient(app).get("/accumulate").text
    assert "Since the last update" in html
    assert "1 left: Microsoft" in html
    other = TestClient(app).get("/accumulate", params={"period": "2024-09-30"}).text
    assert "Since the last update" not in other  # the runs are about the period the list opens on


# --- UI --------------------------------------------------------------------------------------


@pytest.mark.ui
def test_a_person_sees_what_left_the_list_since_the_last_update(accumulate_db, monkeypatch, page: Page):  # noqa: F811
    accumulate_db()
    calls: list[str] = []
    monkeypatch.setattr(ingest, "run", _update_that_drops_microsoft(calls))
    refresh.run([])
    refresh.run([])
    page.goto("/accumulate")
    section = page.locator("section").filter(has=page.get_by_role("heading", name="Since the last update"))
    expect(section).to_be_visible()
    expect(section).to_contain_text(re.compile(r"1 left: Microsoft"))
    expect(section).to_contain_text("Default settings")
