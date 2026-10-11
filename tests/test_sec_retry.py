"""The SEC client's retries, against a fake SEC (no network, no real waiting)."""

import sys

import httpx
import pytest

from thirteenf.ingest import __main__ as ingest_main
from thirteenf.ingest import sec

THROTTLE_PAGE = "<html><h1>Request Rate Threshold Exceeded</h1>Your request rate has exceeded the SEC's limits.</html>"
ZIP_BYTES = b"PK\x03\x04" + bytes(range(60))


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


def test_a_busy_server_is_asked_again():
    fake = FakeSec(answer(503, "Service Unavailable"), answer(200, "<html>the page</html>"))
    assert fake.client.get_text("https://www.sec.gov/page") == "<html>the page</html>"
    assert len(fake.seen) == 2
    assert len(fake.slept) == 1 and 2 <= fake.slept[0] < 3  # 2 ** 1 plus up to 1 s of jitter
    assert fake.logged == [f"  SEC: HTTP 503, waiting {fake.slept[0]:.0f} s (attempt 2 of 5)"]


def test_retry_after_is_honoured_as_it_is():
    fake = FakeSec(answer(429, "Too Many Requests", **{"Retry-After": "2"}), answer(200, "ok"))
    assert fake.client.get_text("https://www.sec.gov/page") == "ok"
    assert fake.slept == [2.0]  # no jitter when the SEC says how long


@pytest.mark.parametrize("page", [THROTTLE_PAGE, "<p>your request originates from an undeclared automated tool</p>"])
def test_the_throttling_page_is_waited_out(page):
    fake = FakeSec(answer(403, page), answer(200, "ok"))
    assert fake.client.get_text("https://www.sec.gov/page") == "ok"
    assert len(fake.seen) == 2 and len(fake.slept) == 1
    assert fake.logged[0].startswith("  SEC: throttled (HTTP 403), waiting")


@pytest.mark.parametrize("status, body", [(404, "Not Found"), (403, "Forbidden"), (400, "Bad Request")])
def test_other_client_errors_are_raised_at_once(status, body):
    fake = FakeSec(answer(status, body))
    with pytest.raises(httpx.HTTPStatusError) as raised:
        fake.client.get_text("https://data.sec.gov/api/xbrl/frames/us-gaap/Deposits/USD/CY2099Q4I.json")
    assert raised.value.response.status_code == status
    assert len(fake.seen) == 1 and fake.slept == []


def test_a_dropped_connection_is_retried():
    fake = FakeSec(httpx.ConnectError("[Errno -3] Temporary failure in name resolution"), answer(200, "ok"))
    assert fake.client.get_text("https://www.sec.gov/page") == "ok"
    assert len(fake.seen) == 2 and len(fake.slept) == 1
    assert fake.logged[0].startswith("  SEC: connection failed (ConnectError), waiting")


def test_the_client_gives_up_after_five_attempts():
    fake = FakeSec(answer(503, "Service Unavailable"))
    with pytest.raises(RuntimeError) as raised:
        fake.client.get_text("https://www.sec.gov/page")
    assert len(fake.seen) == 5 and len(fake.slept) == 4
    assert "5 times (last: HTTP 503)" in str(raised.value) and "10 minutes" in str(raised.value)
    assert "SEC_USER_AGENT" in str(raised.value)
    assert [line.split("(")[-1] for line in fake.logged] == [f"attempt {n} of 5)" for n in (2, 3, 4, 5)]


def test_the_client_gives_up_once_the_waiting_adds_up():
    fake = FakeSec(answer(403, THROTTLE_PAGE, **{"Retry-After": "120"}))
    with pytest.raises(RuntimeError, match="3 times"):
        fake.client.get_text("https://www.sec.gov/page")
    assert fake.slept == [120.0, 120.0]  # 240 s waited, more than the 180 s budget: the next failure is the last
    assert len(fake.seen) == 3


def test_retry_after_dates_and_nonsense():
    def seconds(value):
        return sec._retry_after_seconds(httpx.Response(429, headers={"Retry-After": value}))

    assert seconds("Fri, 31 Dec 2100 00:00:00 GMT") == 300.0  # a date is seconds from now, clamped
    assert seconds("Mon, 01 Jan 2001 00:00:00 GMT") == 0.0
    assert seconds("600") == 300.0 and seconds("-5") == 0.0
    assert seconds("soon") is None  # unreadable: back off as if it were not there
    assert sec._retry_after_seconds(httpx.Response(429)) is None


def test_requests_are_paced():
    fake = FakeSec(answer(200, "ok"))
    fake.client.get_text("https://www.sec.gov/one")
    fake.client.get_text("https://www.sec.gov/two")
    assert fake.slept == [pytest.approx(sec.MIN_SECONDS_BETWEEN_REQUESTS)]


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
    assert fake.logged[0].startswith("  SEC: connection failed (ReadError), waiting")


def test_a_throttled_download_is_waited_out(tmp_path):
    fake = FakeSec(answer(403, THROTTLE_PAGE), answer(200, ZIP_BYTES))
    dest = tmp_path / "01jun2024-31aug2024_form13f.zip"
    fake.client.download("https://www.sec.gov/files/x_form13f.zip", dest)
    assert dest.read_bytes() == ZIP_BYTES and len(fake.seen) == 2


def test_a_missing_download_is_raised_at_once(tmp_path):
    fake = FakeSec(answer(404, "Not Found"))
    dest = tmp_path / "01jun2024-31aug2024_form13f.zip"
    with pytest.raises(httpx.HTTPStatusError):
        fake.client.download("https://www.sec.gov/files/x_form13f.zip", dest)
    assert not dest.exists() and not dest.with_suffix(".zip.part").exists()
    assert len(fake.seen) == 1 and fake.slept == []


def test_the_message_reaches_the_command_line(monkeypatch, capsys):
    """python -m thirteenf.ingest prints what to do, not a traceback."""
    message = sec._gave_up(5, sec._TryAgain("throttled (HTTP 403)"))

    def refused():
        raise RuntimeError(message)

    monkeypatch.setattr(sec, "download_all", refused)
    monkeypatch.setattr(sys, "argv", ["python -m thirteenf.ingest", "--download-only"])
    assert ingest_main.main() == 1
    assert capsys.readouterr().err.strip() == message
