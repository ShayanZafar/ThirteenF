"""FastAPI app: server-rendered pages built from the design system's markup."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from thirteenf.config import DESIGN_SYSTEM_DIR, WATCHLIST_CSV
from thirteenf.web import charts, data, format as fmt, story

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


def freshness(latest_period: data.Period) -> dict:
    return {"latest_period": latest_period, "age_days": (date.today() - latest_period.period).days}


def example_cusips() -> list[str]:
    with open(WATCHLIST_CSV, newline="") as f:
        return [row["cusip"].strip().upper() for row in csv.DictReader(f)]


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return RedirectResponse("/stock", status_code=307)


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
            exact = [r for r in results if r["cusip"] == query.upper()]
            if exact or len(results) == 1:
                return RedirectResponse(f"/stock/{(exact or results)[0]['cusip']}", status_code=303)
        else:
            results = []
            for cusip in example_cusips():
                results += data.search(con, cusip, limit=1)
            results.sort(key=lambda r: -r["funds"])
    return render(request, "lookup.html", nav="lookup", query=query, results=results, **freshness(periods[-1]))


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
        came_from=came_from.upper() if any(e["old_cusip"] == came_from.upper() for e in earlier) else "",
        **freshness(periods[-1]),
    )


@app.get("/changes", response_class=HTMLResponse)
def changes_page(
    request: Request,
    period: str = "",
    minimum: int = Query(100, alias="min", ge=1),
    by: str = "tide",
    n: int = 25,
):
    by = by if by in data.RANKINGS else "tide"
    limit = n if n in (25, 50, 100) else 25
    with data.connection() as con:
        periods = data.periods(con)
        choices = [p for p in periods if p.prev_period is not None]
        selected = next((p for p in choices if p.period.isoformat() == period), choices[-1])
        added = data.ranked_changes(con, selected.period, minimum, by, limit, "added")
        lost = data.ranked_changes(con, selected.period, minimum, by, limit, "lost")
        summary = data.change_summary(con, selected.period, minimum)
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
        summary_text=story.change_summary(summary, selected, added if by == "tide" else []),
        year_end=selected.period.month == 12,
        quarter=f"Q{(selected.period.month - 1) // 3 + 1}",
        **freshness(selected),
    )
