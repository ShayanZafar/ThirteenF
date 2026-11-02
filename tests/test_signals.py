"""The Accumulate rule as its own module (thirteenf.signals.accumulate): the commands use it
without the web app, and each update saves the list it ends with."""

import subprocess
import sys
from datetime import UTC, datetime

from test_accumulate import MSFT, accumulate_db  # noqa: F401  (the fixture: made-up financials and tickers)

from thirteenf.db import connect
from thirteenf.signals import accumulate

RUN_1 = datetime(2025, 1, 20, 6, tzinfo=UTC)
RUN_2 = datetime(2025, 1, 21, 6, tzinfo=UTC)


def test_the_commands_and_the_rule_never_import_the_web_app():
    code = (
        "import sys, thirteenf.prices, thirteenf.signals.accumulate, thirteenf.ingest.__main__; "
        "print(sorted(m for m in sys.modules if m.startswith(('thirteenf.web', 'fastapi'))))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    assert out.strip() == "[]"


def test_each_run_saves_the_list_it_ends_with_and_keeps_the_earlier_ones(accumulate_db):  # noqa: F811
    accumulate_db()
    with connect() as con:
        assert accumulate.saved_runs(con) == []
        assert accumulate.save_run(con, RUN_1) == 1
        assert accumulate.save_run(con, RUN_2) == 1
        assert accumulate.saved_runs(con) == [RUN_1.replace(tzinfo=None), RUN_2.replace(tzinfo=None)]
        saved = con.execute("SELECT run_at, period, rank, cusip, rules FROM accumulate_runs ORDER BY run_at").fetchall()
    assert [(r[2], r[3]) for r in saved] == [(1, MSFT), (1, MSFT)]
    assert saved[0][1].isoformat() == "2024-12-31"  # the period the page opens on
    assert '"min_streak": 2' in saved[0][4]


def test_a_rebuild_of_the_model_keeps_the_saved_runs(accumulate_db):  # noqa: F811
    from thirteenf.model.build import build_all

    accumulate_db()
    with connect() as con:
        accumulate.save_run(con, RUN_1)
    build_all(log=lambda *_: None)
    with connect() as con:
        assert accumulate.saved_runs(con) == [RUN_1.replace(tzinfo=None)]


def test_an_empty_list_is_saved_as_a_run_too(accumulate_db):  # noqa: F811
    accumulate_db({789019: 4e9})  # share counts disagree: nothing qualifies
    with connect() as con:
        assert accumulate.save_run(con, RUN_1) == 0
        assert accumulate.saved_runs(con) == [RUN_1.replace(tzinfo=None)]
