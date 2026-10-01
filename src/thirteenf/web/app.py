"""FastAPI app: server-rendered pages built from the design system's markup."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from thirteenf.config import DESIGN_SYSTEM_DIR

HERE = Path(__file__).resolve().parent

app = FastAPI(title="ThirteenF", docs_url=None, redoc_url=None)
app.mount("/ds", StaticFiles(directory=DESIGN_SYSTEM_DIR), name="ds")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")


def theme_of(request: Request) -> str:
    return "dark" if request.cookies.get("tf_theme") == "dark" else "light"


def render(request: Request, name: str, nav: str = "", **context) -> HTMLResponse:
    return templates.TemplateResponse(
        request, name, {"theme": theme_of(request), "nav": nav, **context}
    )


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return render(request, "home.html", nav="overview")
