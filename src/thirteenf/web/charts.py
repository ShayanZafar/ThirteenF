"""Inline SVG charts, drawn on the server with the design system's classes."""

from __future__ import annotations

import math
from html import escape

from thirteenf.web.format import DASH, count, signed_count

NICE_STEPS = [1, 2, 2.5, 3, 4, 5, 6, 8, 10]


def nice_ticks(top: float, intervals: int = 4) -> list[float]:
    """0 and `intervals` evenly spaced round numbers covering `top`."""
    if top <= 0:
        return [0, 1, 2, 3, 4][: intervals + 1]
    raw = top / intervals
    power = 10 ** math.floor(math.log10(raw))
    step = next(s * power for s in NICE_STEPS if s * power >= raw)
    if step >= 1:
        step = round(step)
    return [step * i for i in range(intervals + 1)]


def _tick_text(v: float) -> str:
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.1f}"


def funds_bar_chart(points: list[dict], name: str) -> str:
    """Funds holding per period, with the change from the period before under each bar.

    points: [{"label": "Q2 2026", "funds": 1843, "change": -13 or None}], oldest first.
    The latest bar is ink; the first, the peak and the latest carry their value.
    """
    width, x0, x1 = 1200, 72, 1188
    zero_y, top_y = 236, 30
    n = max(len(points), 1)
    slot = (x1 - x0) / n
    bar = min(24, slot * 0.5)
    ticks = nice_ticks(max((p["funds"] for p in points), default=0))
    scale = (zero_y - top_y) / ticks[-1] if ticks[-1] else 0

    peak_i = max(range(len(points)), key=lambda i: (points[i]["funds"], i)) if points else -1
    labelled = {0, peak_i, len(points) - 1}
    out = []
    for t in ticks[1:]:
        y = zero_y - t * scale
        out.append(f'<line class="tf-map__grid" x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}"></line>')
    for t in ticks:
        y = zero_y - t * scale + 4
        out.append(f'<text class="tf-map__tick" x="62" y="{y:.1f}" style="text-anchor: end">{_tick_text(t)}</text>')
    out.append('<text class="tf-map__tick" x="62" y="286" style="text-anchor: end">Change</text>')

    for i, p in enumerate(points):
        cx = x0 + slot * i + slot / 2
        left, right = cx - bar / 2, cx + bar / 2
        height = p["funds"] * scale
        top = zero_y - height
        cls = "app-chart__bar app-chart__bar--latest" if i == len(points) - 1 else "app-chart__bar"
        tip = f'{count(p["funds"])} funds · {p["label"]}'
        if height > 0:
            r = min(4, height, bar / 2)
            d = (
                f"M{left:.1f} {zero_y} V{top + r:.1f} Q{left:.1f} {top:.1f} {left + r:.1f} {top:.1f} "
                f"H{right - r:.1f} Q{right:.1f} {top:.1f} {right:.1f} {top + r:.1f} V{zero_y} Z"
            )
            out.append(f'<path class="{cls}" d="{d}"><title>{escape(tip)}</title></path>')
        if i in labelled:
            out.append(
                f'<text class="tf-map__label" x="{cx:.1f}" y="{top - 8:.1f}" style="text-anchor: middle">{count(p["funds"])}</text>'
            )
        out.append(f'<text class="tf-map__tick" x="{cx:.1f}" y="256" style="text-anchor: middle">{escape(p["label"])}</text>')
        change = p.get("change")
        if change is None:
            out.append(f'<text class="tf-map__tick" x="{cx:.1f}" y="286" style="text-anchor: middle">{DASH}</text>')
        elif change == 0:
            out.append(f'<text class="tf-map__label" x="{cx:.1f}" y="286" style="text-anchor: middle">0</text>')
        else:
            tx = cx - 28
            if change > 0:
                tri = f'<polygon class="tf-map__in" points="{tx - 4:.1f},282 {tx + 4:.1f},282 {tx:.1f},275"></polygon>'
            else:
                tri = f'<polygon class="tf-map__out" points="{tx - 4:.1f},275 {tx + 4:.1f},275 {tx:.1f},282"></polygon>'
            out.append(tri)
            out.append(f'<text class="tf-map__label" x="{cx - 18:.1f}" y="286">{signed_count(change)}</text>')

    out.append(f'<line class="tf-map__zero" x1="{x0}" y1="{zero_y}" x2="{x1}" y2="{zero_y}"></line>')

    values = ", ".join(count(p["funds"]) for p in points)
    first, last = (points[0]["label"], points[-1]["label"]) if points else ("", "")
    label = f"Funds holding {name} by quarter from {first} to {last}: {values}."
    return (
        f'<svg class="app-chart" viewBox="0 0 {width} 330" role="img" aria-label="{escape(label)}">'
        + "".join(out)
        + "</svg>"
    )


def sparkline(values: list[float | None]) -> str:
    """A 160 x 32 line through the values, oldest first, with a dot on the latest."""
    pts = [(i, v) for i, v in enumerate(values) if v is not None]
    if not pts:
        return ""
    lo = min(v for _, v in pts)
    hi = max(v for _, v in pts)
    span = hi - lo or 1
    n = max(len(values) - 1, 1)

    def xy(i, v):
        return 4 + 152 * i / n, 28 - 24 * (v - lo) / span

    coords = [xy(i, v) for i, v in pts]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    lx, ly = coords[-1]
    return (
        '<svg class="app-spark" viewBox="0 0 160 32" aria-hidden="true">'
        f'<polyline class="app-spark__line" points="{line}"></polyline>'
        f'<circle class="app-spark__dot" cx="{lx:.1f}" cy="{ly:.1f}" r="3.5"></circle>'
        "</svg>"
    )



def flow_chart(points: list[dict], name: str) -> str:
    """Net 13F flow per period: bars up (flow-in) for net buying, down (flow-out) for
    net selling, from one zero line. points: [{"label", "net"}], oldest first; net None
    when there is no earlier period to compare with."""
    from thirteenf.web.format import money_signed

    width, x0, x1, top_y, bottom_y = 1200, 88, 1188, 24, 236
    values = [p["net"] for p in points if p["net"] is not None]
    if not values:
        return ""
    high, low = max(max(values), 0), min(min(values), 0)
    span = (high - low) or 1
    # Round the scale to tidy steps on both sides of zero.
    step = nice_ticks(span, 4)[1]
    top = step * math.ceil(high / step) if high > 0 else 0
    bottom = -step * math.ceil(-low / step) if low < 0 else 0
    if top == bottom:
        top = step
    scale = (bottom_y - top_y) / (top - bottom)
    zero = top_y + top * scale
    n = max(len(points), 1)
    slot = (x1 - x0) / n
    bar = min(24, slot * 0.5)
    out = []
    tick = bottom
    while tick <= top + step / 2:
        y = top_y + (top - tick) * scale
        if abs(tick) > step / 1e6:
            out.append(f'<line class="tf-map__grid" x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}"></line>')
        label = "0" if abs(tick) < step / 1e6 else money_signed(tick)
        out.append(f'<text class="tf-map__tick" x="{x0 - 10}" y="{y + 4:.1f}" style="text-anchor: end">{escape(label)}</text>')
        tick += step
    extremes = {max(range(n), key=lambda i: points[i]["net"] if points[i]["net"] is not None else -math.inf),
                min(range(n), key=lambda i: points[i]["net"] if points[i]["net"] is not None else math.inf),
                n - 1}
    for i, p in enumerate(points):
        cx = x0 + slot * i + slot / 2
        out.append(f'<text class="tf-map__tick" x="{cx:.1f}" y="{bottom_y + 22}" style="text-anchor: middle">{escape(p["label"])}</text>')
        if p["net"] is None:
            continue
        height = abs(p["net"]) * scale
        left, right = cx - bar / 2, cx + bar / 2
        r = min(4, height, bar / 2)
        if p["net"] >= 0:
            end = zero - height
            d = (f"M{left:.1f} {zero:.1f} V{end + r:.1f} Q{left:.1f} {end:.1f} {left + r:.1f} {end:.1f} "
                 f"H{right - r:.1f} Q{right:.1f} {end:.1f} {right:.1f} {end + r:.1f} V{zero:.1f} Z")
            cls, label_y = "tf-map__in", end - 8
        else:
            end = zero + height
            d = (f"M{left:.1f} {zero:.1f} V{end - r:.1f} Q{left:.1f} {end:.1f} {left + r:.1f} {end:.1f} "
                 f"H{right - r:.1f} Q{right:.1f} {end:.1f} {right:.1f} {end - r:.1f} V{zero:.1f} Z")
            cls, label_y = "tf-map__out", end + 16
        tip = f'{money_signed(p["net"])} · {p["label"]}'
        if height > 0:
            out.append(f'<path class="{cls}" d="{d}"><title>{escape(tip)}</title></path>')
        if i in extremes:
            out.append(f'<text class="tf-map__label" x="{cx:.1f}" y="{label_y:.1f}" style="text-anchor: middle">{escape(money_signed(p["net"]))}</text>')
    out.append(f'<line class="tf-map__zero" x1="{x0}" y1="{zero:.1f}" x2="{x1}" y2="{zero:.1f}"></line>')
    values_text = ", ".join(f'{p["label"]} {money_signed(p["net"])}' for p in points if p["net"] is not None)
    label = f"Net 13F flow into {name} by quarter: {values_text}."
    return (
        f'<svg class="app-chart" viewBox="0 0 {width} {bottom_y + 34}" role="img" aria-label="{escape(label)}">'
        + "".join(out)
        + "</svg>"
    )
