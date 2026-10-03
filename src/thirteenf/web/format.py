"""Number, date and name formats from design-system/README.md.

Money: $ and 3 significant digits with K / M / B. Signed changes use U+2212,
never a hyphen. Dates: Jun 30, 2026. Periods: Q2 2026.
"""

from __future__ import annotations

import math
import re
from datetime import date

MINUS = "−"
DASH = "—"

_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
_UNITS = [(1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")]


def sign(x: float) -> str:
    return "+" if x > 0 else MINUS if x < 0 else ""


def flow(text: str) -> str:
    """The flow direction a formatted change shows: in, out, or none when it rounds to zero."""
    text = str(text).strip()
    if text.startswith("+"):
        return "in"
    if text.startswith(MINUS) or text.startswith("-"):
        return "out"
    return ""


def pct_fine(x: float | None) -> str:
    """Whole percent, or one decimal when the whole percent would read 0%."""
    if x is not None and 0 < abs(x) < 0.005:
        return pct(x, 1)
    return pct(x, 0)


def ticker(text: str | None) -> str:
    """OpenFIGI writes share classes with a slash (BRK/B); people write BRK.B."""
    return (text or "").replace("/", ".")


def number_word(n: int) -> str:
    return _WORDS[n] if 0 <= n < len(_WORDS) else f"{n:,}"


def count(n: int | None) -> str:
    return DASH if n is None else f"{n:,}"


def signed_count(n: int | None) -> str:
    if n is None:
        return DASH
    return f"{sign(n)}{abs(n):,}"


def pct(x: float | None, digits: int = 1, signed: bool = True) -> str:
    """0.0277 -> +2.8%. With signed=False, the size only: -0.0277 -> 2.8%."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return DASH
    value = round(abs(x) * 100, digits)
    text = f"{value:,.{digits}f}%"
    if value == 0 or not signed:
        return text
    return f"{sign(x)}{text}"


def pts(x: float | None, digits: int = 1) -> str:
    """-2.48 -> −2.5 pts"""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return DASH
    value = round(abs(x), digits)
    return f"{sign(x) if value else ''}{value:.{digits}f} pts"


def _sig3(value: float) -> str:
    """Three significant digits: 838, 95.0, 1.84"""
    if value >= 100:
        return f"{value:.0f}"
    if value >= 10:
        return f"{value:.1f}"
    return f"{value:.2f}"


def compact(x: float | None) -> str:
    """838_000_000 -> 838M; 16_100_000_000 -> 16.1B; 950 -> 950"""
    if x is None:
        return DASH
    a = abs(x)
    for size, unit in _UNITS:
        if a >= size * 0.9995:
            text = _sig3(a / size)
            # 999.6M rounds to 1000M: step up a unit
            if float(text) >= 1000 and unit != "T":
                return compact(x / abs(x) * size * 1000) if x else "0"
            return f"{MINUS if x < 0 else ''}{text}{unit}"
    return f"{MINUS if x < 0 else ''}{a:,.0f}"


def money(x: float | None) -> str:
    """$95.0B · $139B · $93.2M"""
    if x is None:
        return DASH
    text = compact(abs(x))
    return f"{MINUS if x < 0 else ''}${text}"


def money_signed(x: float | None) -> str:
    """+$377M · −$36M"""
    if x is None:
        return DASH
    text = compact(abs(x))
    return f"{sign(x)}${text}" if text != "0" else "$0"


def weight(x: float | None) -> str:
    """A position's share of a manager's book: 8.9%."""
    if x is None:
        return DASH
    return f"{x * 100:.1f}%" if x * 100 >= 0.05 else "<0.1%"


def meter_pct(x: float | None, scale: float = 0.10) -> float:
    """Where a weight sits on a conviction meter's 0 to 10% scale; 10% or more pins to the end."""
    return round(min(max(x or 0, 0) / scale, 1) * 100, 1)


def unit_for(total: float) -> tuple[float, str]:
    a = abs(total)
    for size, unit in _UNITS:
        if a >= size:
            return size, unit
    return 1, ""


def signed_compact(delta: float | None, total: float | None = None) -> str:
    """A change in the unit of its total: 838M total, +4.1M change -> +4M."""
    if delta is None:
        return DASH
    if total is None:
        total = delta
    size, unit = unit_for(total)
    scaled_total = abs(total) / size if size else 0
    digits = 0 if scaled_total >= 100 else 1 if scaled_total >= 10 else 2
    value = round(abs(delta) / size, digits)
    if value == 0:
        return f"0{unit}"
    return f"{sign(delta)}{value:,.{digits}f}{unit}"


def day(d: date) -> str:
    """Jun 30, 2026"""
    return f"{d:%b} {d.day}, {d.year}"


def short_day(d: date) -> str:
    """Mar 31"""
    return f"{d:%b} {d.day}"


def month_name(d: date) -> str:
    return f"{d:%B}"


def quarter_label(d: date) -> str:
    return f"Q{(d.month - 1) // 3 + 1} {d.year}"


def exchange(ratio: float) -> str:
    """How many new shares replaced each old one: 'one new share for every 2 old',
    'about 1.01 new shares for each old one'."""
    if abs(ratio - 1) < 0.005:
        return "one new share for each old one"
    if ratio < 1 and abs(1 / ratio - round(1 / ratio)) < 0.02:
        return f"one new share for every {round(1 / ratio)} old"
    if ratio > 1 and abs(ratio - round(ratio)) < 0.02:
        return f"{round(ratio)} new shares for each old one"
    return f"about {ratio:.3g} new shares for each old one"


def price(x: float | None) -> str:
    if x is None:
        return DASH
    if x >= 1000:
        return f"${x:,.0f}"
    if x >= 1:
        return f"${x:,.2f}"
    return f"${x:.4f}"


def ratio(x: float | None) -> str:
    """How far an implied price sits from the median: 5.6x, or 1/12."""
    if not x:
        return DASH
    if x >= 1:
        return f"{x:,.1f}× median" if x < 100 else f"{x:,.0f}× median"
    return f"1/{1 / x:,.0f} of median"


_KEEP_UPPER = {
    "ETF", "ETN", "REIT", "ADR", "ADS", "LLC", "LP", "PLC", "NV", "SA", "AG", "SE", "AB", "ASA",
    "USA", "US", "II", "III", "IV", "MSCI", "S&P", "ESG", "NYSE", "AI", "TR", "SPDR",
}


def display_name(name_filed: str | None, name_mixed: str | None) -> str:
    """The name most filers use, in the mixed case some filers write it, else title case."""
    if name_mixed:
        return name_mixed.strip()
    if not name_filed:
        return ""
    words = []
    for word in name_filed.split():
        bare = re.sub(r"[^A-Za-z&]", "", word)
        if bare.upper() in _KEEP_UPPER and bare.upper() not in {"TR"}:
            words.append(word.upper())
        elif any(ch.isdigit() for ch in word):
            words.append(word)
        else:
            words.append(word[:1].upper() + word[1:].lower())
    return " ".join(words)
