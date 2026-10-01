"""Paths and settings shared by ingest, model and web."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("THIRTEENF_DATA", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "thirteenf.duckdb"
DESIGN_SYSTEM_DIR = ROOT / "design-system"
WATCHLIST_CSV = ROOT / "config" / "watchlist.csv"
REFERENCE_CSV = ROOT / "docs" / "reference" / "13finfo-holdings.csv"


class MissingUserAgent(RuntimeError):
    pass


def sec_user_agent() -> str:
    """The User-Agent the SEC requires on every request. Never guessed."""
    agent = os.environ.get("SEC_USER_AGENT", "").strip()
    if not agent:
        raise MissingUserAgent(
            "SEC_USER_AGENT is not set. The SEC asks every client to identify itself "
            "with a name and contact email, for example:\n"
            '  setx SEC_USER_AGENT "ThirteenF you@example.com"\n'
            "Set it, open a new terminal, and run this again."
        )
    return agent
