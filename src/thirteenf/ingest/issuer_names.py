"""The last resort for a CUSIP's ticker: its issuer name, matched exactly against the SEC's ticker list.

company_tickers.json (loaded by the XBRL step into raw_sec_tickers) names the
company behind each ticker. Both names are normalised the same way (case,
punctuation, a leading THE, and trailing legal suffixes and class or share words)
and must then be equal. A match counts only when it is unambiguous on both sides:
exactly one ticker has that name in the SEC's list, and exactly one stock has it in
the 13F data (a company's common shares and warrants share a name, as do its share
classes). Anything else is no answer. A ticker found this way is marked unverified.

Nothing is fetched here, so nothing goes to the source health file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import duckdb

from thirteenf.ingest.openfigi import valid_cusip

# Trailing words that name the legal form, not the company.
LEGAL = {
    "INC",
    "INCORPORATED",
    "CORP",
    "CORPORATION",
    "CO",
    "COMPANY",
    "LTD",
    "LIMITED",
    "PLC",
    "LLC",
    "LP",
    "LLP",
    "NV",
    "SA",
    "AG",
    "SE",
}
# Trailing words 13F names carry for the class of share, or for the filing: DEL is
# Delaware, NEW a successor company ("BERKSHIRE HATHAWAY INC DEL CL B").
CLASS_WORDS = {
    "COM",
    "COMMON",
    "STK",
    "STOCK",
    "SHS",
    "SHARES",
    "ORD",
    "ORDINARY",
    "ADR",
    "ADS",
    "SPONSORED",
    "SPON",
    "NEW",
    "DEL",
}
# "CL A", "CLASS B", "SER 1": a class word and its letter or digit.
CLASS_LEADS = {"CL", "CLASS", "SER", "SERIES"}
# EDGAR's state of incorporation after a company name: "BANK OF AMERICA CORP /DE/".
STATE_MARK = re.compile(r"\s*/[A-Z ]{1,4}/?\s*$")
# Initials written with dots: U.S., N.V., S.A.
INITIALS = re.compile(r"\b([A-Z])\.(?=[A-Z]\b)")


def normalize(name: str | None) -> str:
    """A company name reduced for an exact match: 'Apple Inc.' and 'APPLE INC' both give
    APPLE, 'U.S. Bancorp' and 'US BANCORP DEL' both USBANCORP. Empty when nothing is left."""
    text = STATE_MARK.sub("", (name or "").upper())
    text = INITIALS.sub(r"\1", text.replace("&", " AND ").replace("'", "").replace("’", ""))
    words = re.findall(r"[A-Z0-9]+", text)
    if words[:1] == ["THE"]:
        words = words[1:]
    while words and (cut := _trailing(words)):
        del words[-cut:]
    return "".join(words)


def _trailing(words: list[str]) -> int:
    """How many words at the end are a legal suffix or a class or share word: 0 when none."""
    if (len(words) >= 2 and words[-2] in CLASS_LEADS and len(words[-1]) == 1) or words[-2:] == ["CAP", "STK"]:
        return 2
    if words[-1] in LEGAL or words[-1] in CLASS_WORDS:
        return 1
    for n in (3, 2):  # a legal suffix spelt in single letters, as 13F names often write it: N V, P L C
        if len(words) > n and all(len(w) == 1 for w in words[-n:]) and "".join(words[-n:]) in LEGAL:
            return n
    return 0


@dataclass
class NameMatch:
    """The unambiguous names on both sides: SEC name -> (ticker, the SEC's own title), and
    13F name -> the one stock that carries it."""

    tickers: dict[str, tuple[str, str]]
    names: dict[str, str]  # CUSIP -> its normalised 13F name, for CUSIPs whose name is unambiguous

    @classmethod
    def from_db(cls, con: duckdb.DuckDBPyConnection) -> NameMatch:
        """Built from raw_sec_tickers and securities; empty when either is missing."""
        tables = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
        if not {"raw_sec_tickers", "securities"} <= tables:
            return cls({}, {})
        by_title: dict[str, set[tuple[str, str]]] = {}
        for ticker, title in con.execute("SELECT ticker, title FROM raw_sec_tickers").fetchall():
            key = normalize(title)
            if key and ticker:
                by_title.setdefault(key, set()).add((ticker.strip(), title))
        tickers = {}
        for key, found in by_title.items():
            if len({t for t, _ in found}) == 1:
                tickers[key] = min(found)
        stocks: dict[str, set[str]] = {}
        named: dict[str, str] = {}
        for cusip, stock, name in con.execute("SELECT cusip, stock, name_filed FROM securities").fetchall():
            key = normalize(name)
            if key and valid_cusip(cusip):  # a CUSIP with a wrong check digit is a filer's typo
                stocks.setdefault(key, set()).add(stock)
                named[cusip] = key
        return cls(tickers, {cusip: key for cusip, key in named.items() if len(stocks[key]) == 1})

    def ticker(self, cusip: str) -> tuple[str, str] | None:
        """The ticker and the SEC's title for a CUSIP, or None when its name does not match exactly one."""
        key = self.names.get(cusip)
        return self.tickers.get(key) if key else None
