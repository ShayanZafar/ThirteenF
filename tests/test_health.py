"""The source health file: its shape, the 24-hour window and the `unreliable` rule (fake clock)."""

import json
import os
from datetime import UTC, datetime, timedelta

from thirteenf import health

T0 = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


def _record(source, outcomes, start=T0, step=timedelta(minutes=1)):
    """Record `outcomes` ("ok", "failed", "throttled") for a source, a minute apart; returns the last time."""
    when = start
    for outcome in outcomes:
        health.record(source, outcome, None if outcome == "ok" else f"{outcome} once", now=when)
        when += step
    return when - step


def test_the_file_has_the_agreed_shape():
    health.record("sec", "ok", now=T0)
    health.record("sec", "failed", "HTTP 503", now=T0 + timedelta(seconds=5))
    report = json.loads(health.HEALTH_PATH.read_text())
    assert set(report) == {"updatedAt", "unreliable", "summary", "sources"}
    assert report["updatedAt"] == "2026-10-11T12:00:05+00:00" and report["unreliable"] is False
    assert isinstance(report["summary"], str) and report["summary"].endswith(".")
    assert set(report["sources"]) == {"sec", "sec-xbrl", "openfigi", "sec-ftd", "stooq", "tiingo"}
    assert report["sources"]["sec"] == {
        "role": "primary",
        "for": "13F data",
        "ok": 1,
        "failed": 1,
        "throttled": 0,
        "lastOk": "2026-10-11T12:00:00+00:00",
        "lastError": "HTTP 503",
    }
    assert report["sources"]["sec-ftd"]["role"] == "fallback" and report["sources"]["sec-ftd"]["for"] == "tickers"
    assert report["sources"]["openfigi"]["lastOk"] is None  # never asked
    # Written atomically: no temporary files are left beside it.
    assert sorted(p.name for p in health.HEALTH_PATH.parent.iterdir()) == [
        "source-health-events.json",
        "source-health.json",
    ]


def test_events_are_kept_for_24_hours_and_at_most_500_a_source():
    _record("sec", ["failed"] * 3, start=T0)
    health.record("sec", "ok", now=T0 + timedelta(hours=24, minutes=5))  # the failures are now over a day old
    sec = health.load()["sources"]["sec"]
    assert (sec["ok"], sec["failed"]) == (1, 0)
    assert sec["lastError"] == "failed once"  # carried over from the file before

    health.EVENTS_PATH.unlink()
    _record("sec", ["failed"] * 5, start=T0)
    _record("openfigi", ["ok"] * 510, start=T0 + timedelta(minutes=5), step=timedelta(seconds=1))
    assert len(health.load_events()) == health.MAX_EVENTS + 5 == 505
    report = health.load()
    assert report["sources"]["openfigi"]["ok"] == 500
    assert report["sources"]["sec"]["failed"] == 5  # a long run of another source never pushes them out
    assert report["unreliable"] is True


def test_a_source_is_unreliable_after_five_attempts_with_under_half_answered():
    def unreliable(outcomes):
        entry = dict.fromkeys(health.OUTCOMES, 0)
        for outcome in outcomes:
            entry[outcome] += 1
        return health.is_unreliable(entry)

    assert not unreliable(["failed"] * 4)  # too few attempts to judge
    assert unreliable(["failed", "throttled", "failed", "ok", "ok"])  # 2 of 5
    assert not unreliable(["failed", "failed", "ok", "ok", "ok"])  # 3 of 5
    assert not unreliable(["failed"] * 3 + ["ok"] * 3)  # exactly half is not under half


def test_a_primary_with_a_reliable_fallback_is_covered():
    last = _record("openfigi", ["throttled"] * 5)
    _record("sec-ftd", ["ok"] * 5, start=last)
    report = health.load()
    assert report["unreliable"] is False
    assert report["summary"] == (
        "OpenFIGI answered 0 of 5 requests in the last 24 hours; another source still answers for tickers."
    )


def test_a_primary_whose_fallback_is_not_judged_yet_is_covered():
    _record("openfigi", ["failed"] * 6)
    assert health.load()["unreliable"] is False


def test_tickers_are_uncovered_when_both_sources_are_unreliable():
    last = _record("openfigi", ["throttled"] * 4 + ["ok"])
    _record("sec-ftd", ["failed"] * 5, start=last)
    report = health.load()
    assert report["unreliable"] is True
    assert report["summary"] == (
        "No reliable source for tickers: OpenFIGI answered 1 of 5 requests in the last 24 hours "
        "and the SEC's fails-to-deliver data 0 of 5."
    )


def test_a_primary_without_a_fallback_is_uncovered_alone():
    _record("sec", ["failed"] * 4 + ["throttled"] * 2 + ["ok"])
    report = health.load()
    assert report["unreliable"] is True
    assert report["summary"].startswith("No reliable source for 13F data: the SEC's 13F data sets answered 1 of 7")


def test_nothing_unreliable_says_so():
    _record("sec", ["ok"] * 5)
    assert health.load()["summary"] == "No source was unreliable in the last 24 hours."


def test_the_warning_ages_out_with_the_events():
    _record("sec", ["failed"] * 5)
    assert health.warning(now=T0 + timedelta(hours=1)).startswith("No reliable source for 13F data")
    assert health.warning(now=T0 + timedelta(hours=25)) is None
    assert health.load()["unreliable"] is False  # refreshed on disk too


def test_the_pages_read_the_health_of_now_and_write_nothing():
    _record("sec", ["ok"], start=T0)
    _record("openfigi", ["failed"] * 5, start=T0 + timedelta(minutes=1))
    _record("sec-ftd", ["throttled"] * 5, start=T0 + timedelta(minutes=1))
    written = health.HEALTH_PATH.read_text(), health.EVENTS_PATH.read_text()

    status = health.page_status(now=T0 + timedelta(hours=1))
    assert status == health.PageStatus(warning=health.load()["summary"], fetched=T0)
    assert status.warning is not None and status.warning.startswith("No reliable source for tickers:")
    # A day later the failures have aged out, and the SEC's last answer is carried over.
    assert health.page_status(now=T0 + timedelta(hours=25)) == health.PageStatus(warning=None, fetched=T0)
    assert (health.HEALTH_PATH.read_text(), health.EVENTS_PATH.read_text()) == written

    health.HEALTH_PATH.unlink()
    health.EVENTS_PATH.unlink()
    assert health.page_status() == health.PageStatus(warning=None, fetched=None)  # no update has run yet


def test_unreadable_files_start_afresh_and_unwritable_ones_are_skipped(tmp_path, monkeypatch):
    health.EVENTS_PATH.write_text("{not json")
    health.HEALTH_PATH.write_text("[]")
    health.record("sec", "ok", now=T0)
    assert health.load()["sources"]["sec"]["ok"] == 1

    blocked = tmp_path / "not-a-folder"
    blocked.write_text("a file where a folder should be")
    monkeypatch.setattr(health, "HEALTH_PATH", blocked / "source-health.json")
    monkeypatch.setattr(health, "EVENTS_PATH", blocked / "source-health-events.json")
    health.record("sec", "failed", "HTTP 503", now=T0)  # does not raise


def test_a_failed_write_leaves_the_old_file_whole(monkeypatch):
    health.record("sec", "ok", now=T0)
    before = health.HEALTH_PATH.read_text()

    def broken_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", broken_replace)
    health.record("sec", "failed", "HTTP 503", now=T0 + timedelta(minutes=1))
    assert health.HEALTH_PATH.read_text() == before
    assert not [p for p in health.HEALTH_PATH.parent.iterdir() if p.name.endswith(".tmp")]
