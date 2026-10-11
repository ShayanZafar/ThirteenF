"""The SEC client's waits, against a fake SEC (no network, no real waiting).

The owner's rules (Oct 11, 2026): requests are paced to the SEC's published limit.
Where the SEC is the only source (the 13F data sets, the XBRL frames), a failed
connection or a 5xx is asked again within seconds and a block is waited out, at
most twice a run. A caller with another source moves on at once."""

import sys

import httpx
import pytest

from thirteenf import health
from thirteenf.ingest import __main__ as ingest_main
from thirteenf.ingest import sec

THROTTLE_PAGE = "<html><h1>Request Rate Threshold Exceeded</h1>Your request rate has exceeded the SEC's limits.</html>"
ZIP_BYTES = b"PK\x03\x04" + bytes(range(60))
PAUSED = "SEC paused requests from this computer; waiting {}, then carrying on (Ctrl+C stops)"


@pytest.fixture(autouse=True)
def user_agent(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "ThirteenF tests@example.com")


def answer(status: int, body: str | bytes = "", **headers: str):
    """An answer the fake SEC gives: a fresh response each time it is asked."""
    if isinstance(body, str):
        return lambda: httpx.Response(status, text=body, headers=headers)
    return lambda: httpx.Response(status, content=body, headers=headers)


class CutOff(httpx.SyncByteStream):
    """A body that breaks off after one chunk, as a dropped connection does."""

    def __iter__(self):
        yield ZIP_BYTES[:4]
        raise httpx.ReadError("Connection reset by peer")


class FakeSec:
    """SecClient against a fake SEC that gives `answers` in turn (the last one repeats).

    An answer makes a response when called, or is an exception to raise instead of answering.
    Requests, sleeps and log lines are recorded; sleeping moves the fake clock, so pacing sees time pass."""

    def __init__(self, *answers):
        self.answers = answers
        self.seen: list[httpx.Request] = []
        self.slept: list[float] = []
        self.logged: list[str] = []
        self.now = 1000.0
        self.client = sec.SecClient(
            transport=httpx.MockTransport(self._handle),
            sleep=self._sleep,
            clock=lambda: self.now,
            log=self.logged.append,
        )

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        reply = self.answers[min(len(self.seen), len(self.answers)) - 1]
        if isinstance(reply, Exception):
            raise reply
        return reply()

    def _sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def _health(name: str = "sec") -> dict:
    return health.load()["sources"][name]


def test_a_busy_server_is_asked_again_within_seconds():
    fake = FakeSec(answer(503, "Service Unavailable"), answer(200, "<html>the page</html>"))
    assert fake.client.get_text("https://www.sec.gov/page") == "<html>the page</html>"
    assert len(fake.seen) == 2
    assert len(fake.slept) == 1 and 1 <= fake.slept[0] < 1.5  # 1 s plus up to half a second of jitter
    assert fake.logged == [f"  SEC: HTTP 503, asking again in {fake.slept[0]:.0f} s (attempt 2 of 4)"]
    assert {k: _health()[k] for k in ("ok", "failed", "throttled", "lastError")} == {
        "ok": 1,
        "failed": 1,
        "throttled": 0,
        "lastError": "HTTP 503",
    }


def test_a_dropped_connection_is_retried_quickly():
    fake = FakeSec(httpx.ConnectError("[Errno -3] Temporary failure in name resolution"), answer(200, "ok"))
    assert fake.client.get_text("https://www.sec.gov/page") == "ok"
    assert len(fake.seen) == 2 and len(fake.slept) == 1 and fake.slept[0] < 1.5
    assert fake.logged[0].startswith("  SEC: connection failed (ConnectError), asking again in 1 s")


def test_the_client_gives_up_after_four_quick_attempts():
    fake = FakeSec(answer(503, "Service Unavailable"))
    with pytest.raises(RuntimeError) as raised:
        fake.client.get_text("https://www.sec.gov/page")
    assert len(fake.seen) == 4 and len(fake.slept) == 3
    for slept, base in zip(fake.slept, (1, 2, 4), strict=True):
        assert base <= slept < base + sec.RETRY_JITTER
    assert "failed to answer 4 times (last: HTTP 503)" in str(raised.value)
    assert "carries on from the finished downloads" in str(raised.value)
    assert [line.split("(")[-1] for line in fake.logged] == [f"attempt {n} of 4)" for n in (2, 3, 4)]
    assert _health()["failed"] == 4 and _health()["ok"] == 0


@pytest.mark.parametrize("page", [THROTTLE_PAGE, "<p>your request originates from an undeclared automated tool</p>"])
def test_a_block_is_waited_out_for_ten_minutes(page):
    fake = FakeSec(answer(403, page), answer(200, "ok"))
    assert fake.client.get_text("https://www.sec.gov/page") == "ok"
    assert len(fake.seen) == 2 and fake.slept == [600.0]
    assert fake.logged == [PAUSED.format("10 minutes")]
    assert _health()["throttled"] == 1 and _health()["ok"] == 1
    assert _health()["lastError"] == "paused requests (HTTP 403)"


def test_retry_after_is_honoured_as_it_is():
    fake = FakeSec(answer(429, "Too Many Requests", **{"Retry-After": "2"}), answer(200, "ok"))
    assert fake.client.get_text("https://www.sec.gov/page") == "ok"
    assert fake.slept == [2.0]  # no jitter when the SEC says how long
    assert fake.logged == [PAUSED.format("2 seconds")]


def test_at_most_two_blocks_are_waited_out_in_a_run():
    """The limit counts across every request of the client, which a run shares."""
    fake = FakeSec(
        answer(403, THROTTLE_PAGE),
        answer(200, "ok"),
        answer(429, "", **{"Retry-After": "90"}),
        answer(403, THROTTLE_PAGE),
    )
    assert fake.client.get_text("https://www.sec.gov/one") == "ok"
    with pytest.raises(RuntimeError) as raised:
        fake.client.get_text("https://www.sec.gov/two")
    assert fake.slept == [600.0, pytest.approx(sec.MIN_SECONDS_BETWEEN_REQUESTS), 90.0]  # no third wait
    assert fake.logged == [PAUSED.format("10 minutes"), PAUSED.format("2 minutes")]
    assert "paused requests from this computer 3 times in this run (last: HTTP 403)" in str(raised.value)
    assert "SEC_USER_AGENT" in str(raised.value)
    assert _health()["throttled"] == 3


def test_a_caller_with_another_source_is_not_kept_waiting_by_a_block():
    fake = FakeSec(answer(403, THROTTLE_PAGE))
    with pytest.raises(sec.SecBlocked):
        fake.client.get_text("https://www.sec.gov/page", source="sec-ftd", has_fallback=True)
    assert len(fake.seen) == 1 and fake.slept == [] and fake.logged == []
    assert _health("sec-ftd")["throttled"] == 1 and _health("sec")["throttled"] == 0
    assert fake.client.blocks_waited == 0  # the run can still wait out two blocks for the 13F data


@pytest.mark.parametrize(
    "failure, what",
    [
        (answer(503, "Service Unavailable"), "HTTP 503"),
        (httpx.ConnectError("[Errno -3] Temporary failure in name resolution"), "connection failed (ConnectError)"),
    ],
)
def test_a_caller_with_another_source_is_not_kept_waiting_by_a_failure(failure, what, tmp_path):
    """No 1, 2, 4 s retries either: the caller switches to its next source at once."""
    fake = FakeSec(failure)
    with pytest.raises(sec.SecUnavailable) as raised:
        fake.client.get_text("https://www.sec.gov/page", source="sec-ftd", has_fallback=True)
    assert not isinstance(raised.value, sec.SecBlocked) and what in str(raised.value)
    dest = tmp_path / "cnsfails202609a.zip"
    with pytest.raises(sec.SecUnavailable):
        fake.client.download("https://www.sec.gov/files/cnsfails202609a.zip", dest, source="sec-ftd", has_fallback=True)
    assert not dest.exists() and not dest.with_suffix(".zip.part").exists()
    assert len(fake.seen) == 2 and fake.slept == [pytest.approx(sec.MIN_SECONDS_BETWEEN_REQUESTS)]  # pacing only
    assert fake.logged == []
    assert _health("sec-ftd")["failed"] == 2 and _health("sec-ftd")["lastError"] == what


@pytest.mark.parametrize("status, body", [(404, "Not Found"), (403, "Forbidden"), (400, "Bad Request")])
def test_other_client_errors_are_raised_at_once(status, body):
    fake = FakeSec(answer(status, body))
    with pytest.raises(httpx.HTTPStatusError) as raised:
        fake.client.get_text("https://www.sec.gov/files/x.json")
    assert raised.value.response.status_code == status
    assert len(fake.seen) == 1 and fake.slept == []
    assert _health()["failed"] == 1 and _health()["lastError"] == f"HTTP {status}"


def test_a_missing_frame_is_an_answer_where_one_is_expected():
    fake = FakeSec(answer(404, "Not Found"))
    with pytest.raises(httpx.HTTPStatusError):
        fake.client.get_text("https://data.sec.gov/api/xbrl/frames/x.json", source="sec-xbrl", missing_ok=True)
    assert _health("sec-xbrl")["ok"] == 1 and _health("sec-xbrl")["failed"] == 0


def test_retry_after_dates_and_nonsense():
    def seconds(value):
        return sec._retry_after_seconds(httpx.Response(429, headers={"Retry-After": value}))

    assert seconds("Fri, 31 Dec 2100 00:00:00 GMT") == sec.MAX_RETRY_AFTER  # a date is seconds from now, clamped
    assert seconds("Mon, 01 Jan 2001 00:00:00 GMT") == 0.0
    assert seconds("600") == 600.0 and seconds("86400") == 3600.0 and seconds("-5") == 0.0
    assert seconds("soon") is None  # unreadable: wait the documented 10 minutes instead
    assert sec._retry_after_seconds(httpx.Response(429)) is None


def test_requests_are_paced_just_under_ten_a_second():
    fake = FakeSec(answer(200, "ok"))
    fake.client.get_text("https://www.sec.gov/one")
    fake.client.get_text("https://www.sec.gov/two")
    assert sec.MIN_SECONDS_BETWEEN_REQUESTS == 0.11
    assert fake.slept == [pytest.approx(0.11)]


def test_a_download_is_retried_and_leaves_no_part_file(tmp_path):
    fake = FakeSec(answer(503, "Service Unavailable"), answer(200, ZIP_BYTES))
    dest = tmp_path / "01jun2024-31aug2024_form13f.zip"
    fake.client.download("https://www.sec.gov/files/x_form13f.zip", dest)
    assert dest.read_bytes() == ZIP_BYTES
    assert not dest.with_suffix(".zip.part").exists()
    assert len(fake.seen) == 2 and len(fake.slept) == 1
    assert fake.logged[-1] == f"  {dest.name}: 0 of 0 MB"  # the usual progress line, through the same log


def test_a_download_cut_off_mid_body_starts_over(tmp_path):
    cut = lambda: httpx.Response(200, headers={"Content-Length": str(len(ZIP_BYTES))}, stream=CutOff())
    fake = FakeSec(cut, answer(200, ZIP_BYTES))
    dest = tmp_path / "01jun2024-31aug2024_form13f.zip"
    fake.client.download("https://www.sec.gov/files/x_form13f.zip", dest)
    assert dest.read_bytes() == ZIP_BYTES
    assert not dest.with_suffix(".zip.part").exists()
    assert len(fake.seen) == 2
    assert fake.logged[0].startswith("  SEC: connection failed (ReadError), asking again in")


def test_a_blocked_download_is_waited_out(tmp_path):
    fake = FakeSec(answer(403, THROTTLE_PAGE), answer(200, ZIP_BYTES))
    dest = tmp_path / "01jun2024-31aug2024_form13f.zip"
    fake.client.download("https://www.sec.gov/files/x_form13f.zip", dest)
    assert dest.read_bytes() == ZIP_BYTES and len(fake.seen) == 2 and fake.slept == [600.0]


def test_a_missing_download_is_raised_at_once(tmp_path):
    fake = FakeSec(answer(404, "Not Found"))
    dest = tmp_path / "01jun2024-31aug2024_form13f.zip"
    with pytest.raises(httpx.HTTPStatusError):
        fake.client.download("https://www.sec.gov/files/x_form13f.zip", dest)
    assert not dest.exists() and not dest.with_suffix(".zip.part").exists()
    assert len(fake.seen) == 1 and fake.slept == []


def test_the_message_reaches_the_command_line(monkeypatch, capsys):
    """python -m thirteenf.ingest prints what to do, not a traceback."""
    message = sec._blocked_message(3, sec._Blocked("HTTP 403"))

    def refused(**_):
        raise RuntimeError(message)

    monkeypatch.setattr(sec, "download_all", refused)
    monkeypatch.setattr(sys, "argv", ["python -m thirteenf.ingest", "--download-only"])
    assert ingest_main.main() == 1
    assert capsys.readouterr().err.strip() == message


def test_the_command_line_says_when_a_data_need_has_no_reliable_source(monkeypatch, capsys):
    def failing(**_):
        for _ in range(5):
            health.record("sec", "failed", "HTTP 503")
        raise RuntimeError(sec._failed_message(4, sec._Failed("HTTP 503")))

    monkeypatch.setattr(sec, "download_all", failing)
    monkeypatch.setattr(sys, "argv", ["python -m thirteenf.ingest", "--download-only"])
    assert ingest_main.main() == 1
    out = capsys.readouterr().out
    assert out == (
        "Sources: No reliable source for 13F data: the SEC's 13F data sets answered 0 of 5 requests "
        f"in the last 24 hours. Details in {health.HEALTH_PATH}.\n"
    )
