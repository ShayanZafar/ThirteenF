"""How each outside source answers, kept in data/source-health.json for you and for tools to read.

Every request to an outside source is one event: ok, failed or throttled (the source
asked us to slow down or paused us). The events of the last WINDOW, at most MAX_EVENTS
per source (a long OpenFIGI run never pushes the SEC's events out), are kept in
data/source-health-events.json, and each new event rewrites data/source-health.json
in this shape:

    {"updatedAt": ISO, "unreliable": bool, "summary": "one sentence",
     "sources": {"<name>": {"role": "primary" | "fallback", "for": "<data need>",
                            "ok": n, "failed": n, "throttled": n,
                            "lastOk": ISO | null, "lastError": "short text" | null}}}

A source is unreliable when it had at least MIN_ATTEMPTS attempts in the window and
under half of them succeeded. `unreliable` is true when, for some data need, the
primary and every fallback are unreliable, or the primary is unreliable and has no
fallback. lastOk and lastError carry over from the file before once their events age
out.

Both files are written atomically (a temporary file, then a rename). Recording never
stops a download: a file that cannot be read starts afresh, one that cannot be written
is skipped.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from thirteenf.config import DATA_DIR

HEALTH_PATH = DATA_DIR / "source-health.json"
EVENTS_PATH = DATA_DIR / "source-health-events.json"
WINDOW = timedelta(hours=24)
MAX_EVENTS = 500
# A source is judged only once it has this many attempts in the window.
MIN_ATTEMPTS = 5
OUTCOMES = ("ok", "failed", "throttled")


@dataclass(frozen=True)
class Source:
    role: str  # primary or fallback
    need: str  # the data need it answers for
    label: str  # how a sentence names it


# Each data need's primary first, then its fallbacks in order.
SOURCES = {
    "sec": Source("primary", "13F data", "the SEC's 13F data sets"),
    "sec-xbrl": Source("primary", "company cash-flow data", "the SEC's XBRL frames"),
    "openfigi": Source("primary", "tickers", "OpenFIGI"),
    "sec-ftd": Source("fallback", "tickers", "the SEC's fails-to-deliver data"),
}


def _iso(when: datetime) -> str:
    return when.astimezone(UTC).isoformat(timespec="seconds")


def _when(event: dict) -> datetime | None:
    try:
        when = datetime.fromisoformat(event["at"])
    except (KeyError, TypeError, ValueError):
        return None
    return when if when.tzinfo else when.replace(tzinfo=UTC)


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(path: Path, data, indent: int | None = None) -> None:
    """Write JSON to a temporary file beside `path`, then rename it over `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(data, out, indent=indent)
            out.write("\n")
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


def load_events() -> list[dict]:
    events = _read(EVENTS_PATH)
    if not isinstance(events, list):
        return []
    return [e for e in events if isinstance(e, dict) and e.get("outcome") in OUTCOMES and _when(e)]


def load() -> dict | None:
    """The health file as last written, or None."""
    report = _read(HEALTH_PATH)
    return report if isinstance(report, dict) else None


def prune(events: list[dict], now: datetime) -> list[dict]:
    """The events of the last WINDOW, oldest first, at most the newest MAX_EVENTS of each source."""
    since = now - WINDOW
    dated = [(when, e) for e in events if (when := _when(e)) is not None and when > since]
    dated.sort(key=lambda pair: pair[0])
    kept: dict[object, int] = {}
    newest_first = []
    for _, event in reversed(dated):
        source = event.get("source")
        if kept.get(source, 0) < MAX_EVENTS:
            kept[source] = kept.get(source, 0) + 1
            newest_first.append(event)
    return newest_first[::-1]


def attempts(entry: dict) -> int:
    return sum(entry[outcome] for outcome in OUTCOMES)


def is_unreliable(entry: dict) -> bool:
    """At least MIN_ATTEMPTS attempts in the window, and under half of them succeeded."""
    return attempts(entry) >= MIN_ATTEMPTS and entry["ok"] * 2 < attempts(entry)


def uncovered_needs(sources: dict) -> list[str]:
    """Data needs whose every source (the primary and all its fallbacks) is unreliable."""
    needs: dict[str, list[str]] = {}
    for name, source in SOURCES.items():
        needs.setdefault(source.need, []).append(name)
    return [need for need, names in needs.items() if all(is_unreliable(sources[n]) for n in names)]


def _and(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _answered(name: str, entry: dict, first: bool) -> str:
    counts = f"{entry['ok']} of {attempts(entry)}"
    label = SOURCES[name].label
    return f"{label} answered {counts} requests in the last 24 hours" if first else f"{label} {counts}"


def _summary(sources: dict, uncovered: list[str]) -> str:
    if uncovered:
        names = [n for n, s in SOURCES.items() if s.need in uncovered]
        parts = [_answered(n, sources[n], first=i == 0) for i, n in enumerate(names)]
        return f"No reliable source for {' or '.join(uncovered)}: {_and(parts)}."
    shaky = [n for n in SOURCES if is_unreliable(sources[n])]
    if shaky:
        parts = [
            f"{_answered(n, sources[n], first=True)}; another source still answers for {SOURCES[n].need}" for n in shaky
        ]
        text = "; ".join(parts)
        return text[0].upper() + text[1:] + "."
    return "No source was unreliable in the last 24 hours."


def summarize(events: list[dict], now: datetime, previous: dict | None = None) -> dict:
    """The health file's contents for these events (already pruned to the window)."""
    before = (previous or {}).get("sources")
    sources: dict[str, dict] = {}
    for name, source in SOURCES.items():
        mine = [e for e in events if e.get("source") == name]
        oks = [e for e in mine if e["outcome"] == "ok"]
        errors = [e for e in mine if e["outcome"] != "ok"]
        earlier = before.get(name) if isinstance(before, dict) else None
        if not isinstance(earlier, dict):
            earlier = {}
        sources[name] = {
            "role": source.role,
            "for": source.need,
            **{outcome: sum(1 for e in mine if e["outcome"] == outcome) for outcome in OUTCOMES},
            "lastOk": oks[-1]["at"] if oks else earlier.get("lastOk"),
            "lastError": errors[-1].get("error") if errors else earlier.get("lastError"),
        }
    uncovered = uncovered_needs(sources)
    return {
        "updatedAt": _iso(now),
        "unreliable": bool(uncovered),
        "summary": _summary(sources, uncovered),
        "sources": sources,
    }


def _save(events: list[dict], now: datetime) -> dict:
    report = summarize(events, now, load())
    with contextlib.suppress(OSError):
        _write(EVENTS_PATH, events)
        _write(HEALTH_PATH, report, indent=2)
    return report


def record(source: str, outcome: str, error: str | None = None, *, now: datetime | None = None) -> None:
    """One answer from an outside source: ok, failed or throttled, with a short error text."""
    now = now or datetime.now(UTC)
    event = {"source": source, "at": _iso(now), "outcome": outcome, "error": None if outcome == "ok" else error}
    _save(prune([*load_events(), event], now), now)


def refresh(now: datetime | None = None) -> dict:
    """Recompute the health file for now (events age out), write it, and return it."""
    now = now or datetime.now(UTC)
    return _save(prune(load_events(), now), now)


@dataclass(frozen=True)
class PageStatus:
    warning: str | None  # the summary while some data need has no reliable source
    fetched: datetime | None  # when the SEC's 13F data sets last answered


def page_status(now: datetime | None = None) -> PageStatus:
    """What every page says about the sources: computed for now from the events (they age
    out between runs) and the file before, writing nothing, so a page view is a small read."""
    now = now or datetime.now(UTC)
    report = summarize(prune(load_events(), now), now, load())
    last_ok = report["sources"]["sec"]["lastOk"]
    fetched = _when({"at": last_ok}) if last_ok else None
    return PageStatus(report["summary"] if report["unreliable"] else None, fetched)


def warning(now: datetime | None = None) -> str | None:
    """The summary sentence when some data need has no reliable source, else None.
    Printed at the end of an ingest or tickers run."""
    report = refresh(now)
    return report["summary"] if report["unreliable"] else None
