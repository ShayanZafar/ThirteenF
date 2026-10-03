"""The one-sentence answer and key figures for a stock, written from rules.

Copy follows design-system/README.md: plain, dated, sentence case. It describes
what filers did and never says buy or sell.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from markupsafe import Markup, escape

from thirteenf.web.data import StockPeriod
from thirteenf.web.format import (
    compact, count, day, flow as flow_of, month_name, number_word, pct, pct_fine, pts, short_day,
    signed_compact, signed_count,
)


def when(period: date) -> str:
    """'the end of 2025' for a Dec 31, otherwise 'Mar 31, 2026'."""
    if period.month == 12:
        return f"the end of {period.year}"
    return day(period)


def _latest_held_shares(series: list[StockPeriod]) -> StockPeriod | None:
    for row in reversed(series):
        if row.shares_shown:
            return row
    return None


def answer(series: list[StockPeriod], name: str) -> str:
    latest = series[-1]
    prev = series[-2] if len(series) > 1 else None
    if not latest.held:
        text = f"No 13F filer reported shares of {name} at {day(latest.period)}."
        held = [r for r in series if r.held]
        if held:
            text += f" {count(held[-1].funds)} funds held it at {day(held[-1].period)}."
        return text
    if latest.funds_change is None:
        text = f"{count(latest.funds)} {'fund' if latest.funds == 1 else 'funds'} held {name} at {day(latest.period)}."
        if latest.prev_period is None:
            return text + " That is the first filing period in this data."
        return text + f" No 13F filer reported it at {day(latest.prev_period)}."

    d, n = latest.direction, latest.streak
    if d == 0:
        text = f"The same number of funds held {name} at {day(latest.period)} as at {short_day(prev.period)}: {count(latest.funds)}."
    elif n >= 2:
        start = series[-1 - n]
        funds = [r.funds for r in series]
        word, move = ("Fewer", "down") if d < 0 else ("More", "up")
        if d < 0 and start.funds == max(funds):
            origin = f"a peak of {count(start.funds)} at {when(start.period)}"
        elif d > 0 and start.funds == min(funds):
            origin = f"a low of {count(start.funds)} at {when(start.period)}"
        else:
            origin = f"{count(start.funds)} at {when(start.period)}"
        text = (
            f"{word} funds held {name} in each of the last {number_word(n)} filing periods: "
            f"{count(latest.funds)} at {day(latest.period)}, {move} from {origin}."
        )
    else:
        word, move = ("More", "up") if d > 0 else ("Fewer", "down")
        text = (
            f"{word} funds held {name} at {day(latest.period)} than at {short_day(prev.period)}: "
            f"{count(latest.funds)}, {move} {abs(latest.funds_change):,} ({pct(latest.funds_pct, signed=False)})."
        )
        if prev.direction == -d and prev.streak >= 2:
            before = "fewer" if d > 0 else "more"
            text += f" It follows {number_word(prev.streak)} periods with {before} funds."

    if latest.shares_change_shown:
        change = latest.shares_pct
        if abs(change) < 0.01:
            verb = "barely moved"
        elif change > 0:
            verb = f"rose {pct(change, 0, signed=False)}"
        else:
            verb = f"fell {pct(change, 0, signed=False)}"
        text += (
            f" The shares those funds hold {verb}: {compact(latest.shares)}, "
            f"against {compact(latest.shares_prev)} in {month_name(prev.period)}."
        )
    elif latest.share_check == "outran":
        text += (
            f" Their share total for {latest.label} moved {abs(latest.shares_vs_value_pts):,.0f} points "
            "beyond its value, so it is not shown until checked."
        )
    return text


def comparison(series: list[StockPeriod], name: str) -> str:
    latest = series[-1]
    compared = [r for r in series if r.vs_median_pts is not None][-8:]
    text = ""
    if len(compared) >= 2:
        ahead = sum(1 for r in compared if r.vs_median_pts > 0)
        if ahead == 0:
            how_often = "in none"
        elif ahead == len(compared):
            how_often = "in each"
        else:
            how_often = f"in {number_word(ahead)}"
        text = (
            f"Funds holding {name} ran ahead of the market median {how_often} "
            f"of the last {number_word(len(compared))} periods."
        )
    if latest.funds_pct is not None and latest.market_median_pct is not None:
        if round(latest.funds_pct * 100, 1) == 0:
            moved = "was unchanged"
        else:
            moved = f"was {'up' if latest.funds_pct > 0 else 'down'} {pct(latest.funds_pct, signed=False)}"
        text += (
            f" In the {month_name(latest.period)} quarter it {moved}, against a market median of "
            f"{pct(latest.market_median_pct)} and {pct(latest.filers_pct)} for all 13F filers."
        )
    return text.strip()


def over_time(series: list[StockPeriod], name: str) -> str:
    first, latest = series[0], series[-1]
    if first is latest or not latest.held:
        return ""
    quarters = len(series) - 1
    span = "Over two years" if quarters == 8 else f"Since {first.label}"
    diff = latest.funds - first.funds
    if diff == 0:
        text = f"{span}: the same number of funds hold {name}, {count(latest.funds)}"
    else:
        text = (
            f"{span}: {abs(diff):,} {'more' if diff > 0 else 'fewer'} funds hold {name} "
            f"({pct_fine(latest.funds / first.funds - 1)})"
        )
    if first.shares_shown and latest.shares_shown and first.shares:
        share_diff = latest.shares - first.shares
        join = "and" if (diff >= 0) == (share_diff >= 0) else "but"
        text += (
            f", {join} they hold {signed_compact(abs(share_diff), latest.shares).lstrip('+')} "
            f"{'more' if share_diff >= 0 else 'fewer'} shares ({pct_fine(latest.shares / first.shares - 1)})."
        )
        if diff > 0 and share_diff < 0:
            text += " More funds hold it, each with fewer shares on average."
        elif diff < 0 and share_diff > 0:
            text += " Fewer funds hold it, each with more shares on average."
    else:
        text += "."
    return text


@dataclass
class Figure:
    label: str
    value: str
    unit: str = ""
    delta: Markup = field(default_factory=lambda: Markup(""))
    direction: str = ""  # in, out or ""


def _dir(direction: str) -> Markup:
    return Markup(f'<span class="tf-dir tf-dir--{direction}"></span>') if direction else Markup("")


def _split_unit(text: str) -> tuple[str, str]:
    if text and text[-1] in "KMBT":
        return text[:-1], text[-1]
    return text, ""


def key_figures(series: list[StockPeriod]) -> list[Figure]:
    latest = series[-1]
    prev = series[-2] if len(series) > 1 else None
    figures: list[Figure] = []

    def flow(x: float | None) -> str:
        return "" if not x else ("in" if x > 0 else "out")

    # Funds holding
    f = Figure(label=f"Funds holding, {day(latest.period)}", value=count(latest.funds))
    if latest.funds_change is not None and prev:
        f.direction = flow(latest.funds_change)
        f.delta = _dir(f.direction) + Markup(f"<b>{escape(signed_count(latest.funds_change))}</b> vs {escape(short_day(prev.period))}")
    figures.append(f)

    # From the peak, or from the low when this is the peak
    if len(series) > 1:
        earlier = series[:-1]
        peak = max(earlier, key=lambda r: (r.funds, r.period))
        if latest.funds < peak.funds:
            diff = latest.funds - peak.funds
            figures.append(
                Figure(
                    label=f"From the {day(peak.period)} peak", value=signed_count(diff), direction="out",
                    delta=_dir("out") + Markup(f"<b>{escape(pct(diff / peak.funds, 0, signed=False))} fewer</b> than {escape(count(peak.funds))}"),
                )
            )
        else:
            low = min(earlier, key=lambda r: (r.funds, r.period))
            diff = latest.funds - low.funds
            more = f"{pct(diff / low.funds, 0, signed=False)} more" if low.funds else "up"
            figures.append(
                Figure(
                    label=f"From the {day(low.period)} low", value=signed_count(diff), direction=flow(diff),
                    delta=_dir(flow(diff)) + Markup(f"<b>{escape(more)}</b> than {escape(count(low.funds))}"),
                )
            )

    # Shares held
    if latest.shares_shown:
        number, unit = _split_unit(compact(latest.shares))
        f = Figure(label="Shares held by funds", value=number, unit=unit)
        if latest.shares_change_shown and prev:
            text = signed_compact(latest.shares_change, latest.shares)
            f.direction = flow_of(text)
            f.delta = _dir(f.direction) + Markup(f"<b>{escape(text)}</b> vs {escape(short_day(prev.period))}")
        figures.append(f)
    elif latest.held:
        figures.append(Figure(label="Shares held by funds", value="Check", delta=Markup("Shares outran value; not shown")))

    # Periods with more funds
    changes = [r for r in series if r.direction is not None][-8:]
    if changes:
        more = sum(1 for r in changes if r.direction > 0)
        d, n = latest.direction, latest.streak
        if d is None or d == 0:
            streak = "Unchanged in the latest period"
        else:
            word = "More" if d > 0 else "Fewer"
            streak = f"{word} in the latest {number_word(n)}" if n >= 2 else f"{word} in the latest period"
        figures.append(Figure(label="Periods with more funds", value=str(more), unit=f" of last {len(changes)}", delta=Markup(escape(streak))))

    quarter = f"Q{(latest.period.month - 1) // 3 + 1}"
    if latest.vs_median_pts is not None:
        figures.append(
            Figure(
                label=f"Vs market median, {quarter}", value=pts(latest.vs_median_pts)[:-4], unit=" pts",
                direction=flow(round(latest.vs_median_pts, 1)),
                delta=_dir(flow(round(latest.vs_median_pts, 1)))
                + Markup(f"<b>{escape(pct(latest.funds_pct))}</b> against {escape(pct(latest.market_median_pct))}"),
            )
        )
    if latest.vs_tide_pts is not None:
        figures.append(
            Figure(
                label=f"Vs all 13F filers, {quarter}", value=pts(latest.vs_tide_pts)[:-4], unit=" pts",
                direction=flow(round(latest.vs_tide_pts, 1)),
                delta=_dir(flow(round(latest.vs_tide_pts, 1)))
                + Markup(f"<b>{escape(pct(latest.funds_pct))}</b> against {escape(pct(latest.filers_pct))}"),
            )
        )
    return figures


def change_summary(summary: dict, period, added: list[dict], noun: tuple[str, str] = ("stocks", "stock")) -> str:
    """One paragraph on how the stocks (or ETFs, or both) compared moved in a period."""
    plural, singular = noun
    if not summary["stocks"]:
        return f"No {singular} meets the minimum at both {day(period.prev_period)} and {day(period.period)}."
    text = (
        f"More funds held {summary['more']:,} of the {summary['stocks']:,} {plural} compared at "
        f"{day(period.period)} than at {short_day(period.prev_period)}, and fewer held {summary['fewer']:,}."
    )
    median, tide = summary["median_pct"], summary["filers_pct"]
    if median is not None and tide is not None:
        moved = "rose" if tide > 0 else "fell" if tide < 0 else "held at"
        text += (
            f" The typical {singular}'s count changed by {pct(median)}, while the number of 13F filers "
            f"{moved} {pct(tide, signed=False) if tide else count(summary['filers'])}."
        )
    if added:
        top = added[0]
        text += f" {top['name']} gained the most against that tide: {pts(top['vs_tide_pts'])}."
    return text


_ORDINALS = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth"]


def ordinal(n: int) -> str:
    return _ORDINALS[n - 1] if 1 <= n <= len(_ORDINALS) else f"{n}th"


def join_names(names: list[str]) -> str:
    if len(names) <= 2:
        return " and ".join(names)
    return ", ".join(names[:-1]) + f" and {names[-1]}"


def watchlist_answer(rows: list, period) -> str:
    """rows: objects with .name and .latest (a StockPeriod)."""
    if not rows:
        return "Your watchlist is empty. Add a stock below to follow it here."
    n = len(rows)
    compared = [r for r in rows if r.latest.funds_change is not None]
    more = [r for r in compared if r.latest.funds_change > 0]
    fewer = [r for r in compared if r.latest.funds_change < 0]
    now, before = day(period.period), short_day(period.prev_period)
    if n > 1 and len(more) == n:
        return f"More funds held every stock on your watchlist at {now} than at {before}."
    if n > 1 and len(fewer) == n:
        return f"Fewer funds held every stock on your watchlist at {now} than at {before}."
    if n == 1:
        r = rows[0]
        if r.latest.funds_change is None:
            return f"{count(r.latest.funds)} funds held {r.name} at {now}."
        word = "More" if r.latest.funds_change > 0 else "Fewer" if r.latest.funds_change < 0 else "The same number of"
        return f"{word} funds held {r.name} at {now} than at {before}."
    text = f"More funds held {number_word(len(more))} of these {number_word(n)} stocks at {now} than at {before}."
    if len(fewer) == 1:
        r = fewer[0]
        text += f" {r.name} was the one that lost funds"
        text += f", for the {ordinal(r.latest.streak)} quarter running." if r.latest.streak >= 2 else "."
    elif 1 < len(fewer) <= 3:
        text += f" {join_names([r.name for r in fewer])} lost funds."
    elif len(fewer) > 3:
        text += f" {number_word(len(fewer)).capitalize()} lost funds."
    return text


def watchlist_figures(rows: list, period) -> list[Figure]:
    quarter = f"Q{(period.period.month - 1) // 3 + 1}"
    compared = [r for r in rows if r.latest.funds_change is not None]
    more = sum(1 for r in compared if r.latest.funds_change > 0)
    figures = [
        Figure(label=f"Stocks that gained funds, {quarter}", value=str(more), unit=f" of {len(rows)}",
               delta=Markup(escape(f"Against {short_day(period.prev_period)}"))),
        Figure(label=f"Market median, {quarter}", value=pct(period.market_median_pct),
               delta=Markup("Typical change in funds holding")),
    ]
    ranked = sorted((r for r in rows if r.latest.vs_median_pts is not None), key=lambda r: r.latest.vs_median_pts)
    if len(ranked) >= 2:
        best = "Furthest ahead of the median" if ranked[-1].latest.vs_median_pts > 0 else "Nearest the median"
        for label, r in ((best, ranked[-1]), ("Furthest behind", ranked[0])):
            d = "in" if r.latest.vs_median_pts > 0 else "out" if r.latest.vs_median_pts < 0 else ""
            figures.append(
                Figure(
                    label=label, value=pts(r.latest.vs_median_pts)[:-4], unit=" pts", direction=d,
                    delta=_dir(d) + Markup(f"<b>{escape(r.name)}</b>, {escape(pct(r.latest.funds_pct))}"),
                )
            )
    return figures
