"""FastAPI app: server-rendered pages built from the design system's markup."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from thirteenf.config import DESIGN_SYSTEM_DIR, WATCHLIST_CSV
from thirteenf.web import charts, data, format as fmt, story, watchlist

HERE = Path(__file__).resolve().parent

app = FastAPI(title="ThirteenF", docs_url=None, redoc_url=None)
app.mount("/ds", StaticFiles(directory=DESIGN_SYSTEM_DIR), name="ds")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
templates.env.globals["fmt"] = fmt

ASSET_DIRS = {"/ds/": DESIGN_SYSTEM_DIR, "/static/": HERE / "static"}


def asset(url: str) -> str:
    """A stylesheet URL with its file's modification time, so browsers fetch it again after a change."""
    for prefix, folder in ASSET_DIRS.items():
        if url.startswith(prefix):
            try:
                return f"{url}?v={int((folder / url[len(prefix):]).stat().st_mtime)}"
            except OSError:
                return url
    return url


templates.env.globals["asset"] = asset


def theme_of(request: Request) -> str:
    return "dark" if request.cookies.get("tf_theme") == "dark" else "light"


def render(request: Request, name: str, nav: str = "", status_code: int = 200, **context) -> HTMLResponse:
    return templates.TemplateResponse(
        request, name, {"theme": theme_of(request), "nav": nav, **context}, status_code=status_code
    )


@app.exception_handler(data.NoData)
def no_data(request: Request, exc: data.NoData):
    return render(request, "nodata.html", status_code=503)


@app.exception_handler(data.Busy)
def busy(request: Request, exc: data.Busy):
    response = render(request, "busy.html", status_code=503)
    response.headers["Retry-After"] = "30"
    return response


def freshness(latest_period: data.Period) -> dict:
    return {"latest_period": latest_period, "age_days": (date.today() - latest_period.period).days}


def example_cusips() -> list[str]:
    with open(WATCHLIST_CSV, newline="") as f:
        return [row["cusip"].strip().upper() for row in csv.DictReader(f)]


@app.get("/search")
def search_redirect(q: str = ""):
    return RedirectResponse(f"/stock?q={q}" if q else "/stock", status_code=303)


@app.get("/stock", response_class=HTMLResponse)
def lookup(request: Request, q: str = ""):
    query = q.strip()
    with data.connection() as con:
        periods = data.periods(con)
        if query:
            results = data.search(con, query)
            target = data.best_match(results, query)
            if target:
                return RedirectResponse(f"/stock/{target['cusip']}", status_code=303)
        else:
            results = []
            for cusip in example_cusips():
                results += data.search(con, cusip, limit=1)
            results.sort(key=lambda r: -r["funds"])
    return render(
        request, "lookup.html", nav="lookup", query=query, results=results,
        on_watchlist=watchlist.cusips(), **freshness(periods[-1]),
    )


@app.get("/api/suggest")
def suggest(q: str = ""):
    """Up to eight stocks for the search box, as you type."""
    if len(q.strip()) < 1:
        return JSONResponse([])
    with data.connection() as con:
        results = data.search(con, q, limit=20)
    if any(r["funds"] for r in results):
        results = [r for r in results if r["funds"]]  # nobody holds the rest now: old bonds, options
    results = results[:8]
    names = [r["name"] for r in results]
    suggestions = []
    for r in results:
        funds = f"{fmt.count(r['funds'])} {'fund' if r['funds'] == 1 else 'funds'}"
        # Where two suggestions share a name, the class tells them apart.
        meta = f"{r['title_of_class']} · {funds}" if names.count(r["name"]) > 1 and r["title_of_class"] else funds
        if r.get("kind") == "etf":
            meta = f"ETF · {meta}"
        suggestions.append(
            {"cusip": r["cusip"], "ticker": r["ticker"], "name": r["name"], "funds": r["funds"], "funds_text": meta}
        )
    return JSONResponse(suggestions)


@app.get("/stock/{cusip}", response_class=HTMLResponse)
def stock_page(request: Request, cusip: str, came_from: str = Query("", alias="from")):
    with data.connection() as con:
        periods = data.periods(con)
        sec = data.security(con, cusip)
        if sec is None:
            return render(request, "notfound.html", nav="lookup", what=f"CUSIP {cusip.upper()}", status_code=404)
        if sec.stock != sec.cusip:
            # An earlier CUSIP: show the stock under its current one.
            return RedirectResponse(f"/stock/{sec.stock}?from={sec.cusip}", status_code=303)
        earlier = data.earlier_cusips(con, sec.cusip)
        series = data.stock_series(con, sec.cusip, periods)
        latest = series[-1]
        left_out, left_out_total = (
            data.left_out_rows(con, sec.cusip, latest.period) if latest.held else ([], 0)
        )
    chart = charts.funds_bar_chart(
        [{"label": r.label, "funds": r.funds, "change": r.funds_change} for r in series], sec.name
    )
    return render(
        request,
        "stock.html",
        nav="lookup",
        sec=sec,
        latest=latest,
        rows=list(reversed(series)),
        answer=story.answer(series, sec.name),
        comparison=story.comparison(series, sec.name),
        over_time=story.over_time(series, sec.name),
        figures=story.key_figures(series),
        chart=Markup(chart),
        left_out=left_out,
        left_out_total=left_out_total,
        outran=[r.label for r in series if r.held and r.share_check == "outran"],
        earlier=earlier,
        on_watchlist=sec.cusip in watchlist.cusips(),
        came_from=came_from.upper() if any(e["old_cusip"] == came_from.upper() for e in earlier) else "",
        **freshness(periods[-1]),
    )


# What a tab calls the things it compares: (plural, singular).
NOUNS = {"all": ("securities", "security"), "stocks": ("stocks", "stock"), "etfs": ("ETFs", "ETF")}


@app.get("/changes", response_class=HTMLResponse)
def changes_page(
    request: Request,
    period: str = "",
    minimum: int = Query(100, alias="min", ge=1),
    by: str = "tide",
    n: int = 25,
    kind: str = "all",
):
    by = by if by in data.RANKINGS else "tide"
    kind = kind if kind in data.KINDS else "all"
    limit = n if n in (25, 50, 100) else 25
    with data.connection() as con:
        periods = data.periods(con)
        choices = [p for p in periods if p.prev_period is not None]
        selected = next((p for p in choices if p.period.isoformat() == period), choices[-1])
        added = data.ranked_changes(con, selected.period, minimum, by, limit, "added", kind)
        lost = data.ranked_changes(con, selected.period, minimum, by, limit, "lost", kind)
        summary = data.change_summary(con, selected.period, minimum, kind)
        counts = data.kind_counts(con, selected.period, minimum)
    metric = data.RANKINGS[by]
    for rows in (added, lost):
        widest = max((abs(r[metric]) for r in rows), default=0) or 1
        for r in rows:
            r["bar"] = round(100 * abs(r[metric]) / widest, 1)
    return render(
        request,
        "changes.html",
        nav="changes",
        selected=selected,
        choices=choices,
        minimum=minimum,
        by=by,
        limit=limit,
        added=added,
        lost=lost,
        summary=summary,
        kind=kind,
        counts=counts,
        noun=NOUNS[kind],
        summary_text=story.change_summary(summary, selected, added if by == "tide" else [], NOUNS[kind]),
        year_end=selected.period.month == 12,
        quarter=f"Q{(selected.period.month - 1) // 3 + 1}",
        **freshness(selected),
    )


@dataclass
class WatchRow:
    cusip: str
    ticker: str
    name: str
    latest: data.StockPeriod
    spark: Markup
    since: str  # the first period shown, when the stock's history is shorter than the data's
    long_change: float | None
    left_out_total: int
    left_out_top: dict | None


def _back(url: str) -> str:
    """Only send people back to a page of this app."""
    return url if url.startswith("/") and not url.startswith("//") else "/"


@app.get("/", response_class=HTMLResponse)
def overview(request: Request):
    entries = watchlist.load()
    with data.connection() as con:
        periods = data.periods(con)
        latest_period = periods[-1]
        rows: list[WatchRow] = []
        missing: list[watchlist.Entry] = []
        seen: set[str] = set()
        for entry in entries:
            sec = data.security(con, entry.cusip)
            if sec is not None and sec.stock != sec.cusip:
                sec = data.security(con, sec.stock)  # a replaced CUSIP: follow it to the stock
            if sec is None:
                missing.append(entry)
                continue
            if sec.cusip in seen:
                continue
            seen.add(sec.cusip)
            series = data.stock_series(con, sec.cusip, periods)
            if not series:
                missing.append(entry)
                continue
            latest, first = series[-1], series[0]
            top, total = data.left_out_rows(con, sec.cusip, latest.period, limit=1) if latest.held else ([], 0)
            funds_by_period = {r.period: r.funds for r in series}
            rows.append(
                WatchRow(
                    cusip=sec.cusip,
                    ticker=entry.ticker or sec.ticker,
                    name=entry.name or sec.name,
                    latest=latest,
                    spark=Markup(charts.sparkline([funds_by_period.get(p.period) for p in periods])),
                    since="" if first.period == periods[0].period else first.label,
                    long_change=(latest.funds / first.funds - 1) if first is not latest and first.funds else None,
                    left_out_total=total,
                    left_out_top=top[0] if top else None,
                )
            )
    rows.sort(key=lambda r: (r.latest.vs_median_pts is None, -(r.latest.vs_median_pts or 0)))
    return render(
        request,
        "overview.html",
        nav="overview",
        rows=rows,
        missing=missing,
        periods=periods,
        answer=story.watchlist_answer(rows, latest_period),
        figures=story.watchlist_figures(rows, latest_period),
        failed=[r for r in rows if r.latest.held and r.latest.share_check == "outran"],
        left_out_sum=sum(r.left_out_total for r in rows),
        biggest_left_out=max(
            ((r, r.left_out_top) for r in rows if r.left_out_top), key=lambda x: x[1]["shares"], default=None
        ),
        **freshness(latest_period),
    )


@app.post("/watchlist/add")
def watchlist_add(q: str = Form(""), cusip: str = Form(""), back: str = Form("/")):
    with data.connection() as con:
        if cusip.strip():
            sec = data.security(con, cusip.strip())
            if sec is None:
                return RedirectResponse(f"/stock?q={quote(cusip.strip())}", status_code=303)
            target = sec.stock
        else:
            results = data.search(con, q)
            match = data.best_match(results, q)
            if match is None:
                # Several matches, or none: pick from the search results.
                return RedirectResponse(f"/stock?q={quote(q.strip())}", status_code=303)
            target = match["cusip"]
    watchlist.add(target)
    return RedirectResponse(_back(back), status_code=303)


@app.post("/watchlist/remove")
def watchlist_remove(cusip: str = Form(...), back: str = Form("/")):
    watchlist.remove(cusip)
    return RedirectResponse(_back(back), status_code=303)
