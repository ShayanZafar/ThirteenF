"""Paths and settings shared by ingest, model and web."""

import os
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("THIRTEENF_DATA", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "thirteenf.duckdb"
DESIGN_SYSTEM_DIR = ROOT / "design-system"
WATCHLIST_CSV = ROOT / "config" / "watchlist.csv"  # the example the watchlist starts from
WATCHLIST_PATH = Path(os.environ.get("THIRTEENF_WATCHLIST", DATA_DIR / "watchlist.csv"))  # yours
REFERENCE_CSV = ROOT / "docs" / "reference" / "13finfo-holdings.csv"
# Settings for this computer, such as API keys. In data/, which git ignores.
SETTINGS_PATH = Path(os.environ.get("THIRTEENF_SETTINGS", DATA_DIR / "settings.toml"))

SETTINGS_TEMPLATE = """\
# ThirteenF settings for this computer. This file lives in data/, which git ignores.

# A free key from https://www.openfigi.com (sign up, then open your account page).
# It raises OpenFIGI's rate limit, so mapping CUSIPs to tickers takes minutes, not hours.
# Paste it between the quotes and save.
openfigi_api_key = ""
"""


def settings_file_value(name: str) -> str:
    """A value from data/settings.toml, or "" when the file or the value is missing.

    Reads it as TOML, and still finds `name = value` if the quotes were lost in pasting."""
    try:
        text = SETTINGS_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""
    try:
        return str(tomllib.loads(text).get(name, "") or "").strip()
    except tomllib.TOMLDecodeError:
        match = re.search(rf"^\s*{re.escape(name)}\s*=\s*[\"']?([^\"'\s#]+)", text, re.M)
        return match.group(1) if match else ""


def ensure_settings_file() -> Path:
    """Create data/settings.toml with empty values, if it does not exist yet."""
    if not SETTINGS_PATH.exists():
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(SETTINGS_TEMPLATE, encoding="utf-8")
    return SETTINGS_PATH


def user_setting(name: str) -> str:
    """An environment variable, or on Windows the user variable of that name.

    A variable saved with setx or the Environment Variables dialog only reaches
    programs started afterwards; reading the user's settings directly means a
    terminal that was already open sees it too."""
    value = os.environ.get(name, "").strip()
    if value or os.name != "nt":
        return value
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            return str(winreg.QueryValueEx(key, name)[0]).strip()
    except OSError:
        return ""


class MissingUserAgent(RuntimeError):
    pass


def sec_user_agent() -> str:
    """The User-Agent the SEC requires on every request. Never guessed."""
    agent = user_setting("SEC_USER_AGENT")
    if not agent:
        raise MissingUserAgent(
            "SEC_USER_AGENT is not set. The SEC asks every client to identify itself "
            "with a name and contact email, for example:\n"
            '  setx SEC_USER_AGENT "ThirteenF you@example.com"\n'
            "Set it, open a new terminal, and run this again."
        )
    return agent


def openfigi_api_key() -> str:
    """Your free OpenFIGI key, which raises its rate limit. Empty when not set.

    From the OPENFIGI_API_KEY environment variable if one is set, else from
    openfigi_api_key in data/settings.toml."""
    return (
        os.environ.get("OPENFIGI_API_KEY", "").strip()
        or settings_file_value("openfigi_api_key")
        or user_setting("OPENFIGI_API_KEY")
    )
