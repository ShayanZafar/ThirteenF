"""Signed numbers are painted by their sign: + in flow-in green, − in flow-out red."""

import re

import pytest
from fastapi.testclient import TestClient

from thirteenf.web.app import app, signed
from thirteenf.web.charts import _tone

ALPHABET_MANAGER = 1652044
# A table value, a key figure or a chart label, and the text it starts with.
PAINTED = re.compile(r'class="(?:tf-kf__value |tf-map__label )?app-(?:svg-)?(pos|neg)"[^>]*>([^<]*)<')


def test_the_filter_paints_by_sign():
    assert signed("+2.8%") == '<span class="app-pos">+2.8%</span>'
    assert signed("−$36M") == '<span class="app-neg">−$36M</span>'
    assert signed("0.0%") == "0.0%"
    assert signed("$0") == "$0"
    assert signed("—") == "—"
    assert signed("<b>") == "&lt;b&gt;"


def test_chart_labels_take_the_printed_sign():
    assert _tone("+12") == " app-svg-pos"
    assert _tone("−$1.2B") == " app-svg-neg"
    assert _tone("$0") == ""


@pytest.mark.data
@pytest.mark.parametrize(
    "path",
    ["/stock/037833100", "/", "/changes", "/changes?by=count&kind=etfs", "/managers",
     f"/manager/{ALPHABET_MANAGER}?period=2026-03-31"],
)
def test_every_painted_number_matches_its_sign(con, path):
    html = TestClient(app).get(path).text
    painted = PAINTED.findall(html)
    assert painted, path
    for tone, text in painted:
        assert text.startswith("+" if tone == "pos" else "−"), (path, tone, text)
    assert "&lt;span" not in html


@pytest.mark.data
def test_a_stock_page_paints_both_ways(con):
    html = TestClient(app).get("/stock/037833100").text  # Apple: funds came and went
    tones = {tone for tone, _ in PAINTED.findall(html)}
    assert tones == {"pos", "neg"}
    assert "tf-map__label app-svg-" in html
    assert 'class="tf-kf__value app-' in html
