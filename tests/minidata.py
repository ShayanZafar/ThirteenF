"""A small, made-up 13F data set in the SEC's zip format, for tests that run without the download.

Three filing windows (Q2, Q3 and Q4 2024), 160 managers and five securities. The
numbers are invented; what matters is that they go through the same load and
build as the real data, so tests can check where the steps meet.
"""

import zipfile
from pathlib import Path

MANAGERS = 160

# CUSIP: (issuer, class, price, how many managers hold it in each period)
SECURITIES = {
    "037833100": ("APPLE INC", "COM", 200, (160, 160, 160)),
    "594918104": ("MICROSOFT CORP", "COM", 400, (120, 130, 140)),
    "67066G104": ("NVIDIA CORPORATION", "COM", 120, (150, 140, 130)),
    "023135106": ("AMAZON COM INC", "COM", 180, (130, 130, 135)),
    # An ETF whose class reads like a unit: until OpenFIGI says ETP, it counts as "other".
    "46090E103": ("INVESCO QQQ TR", "UNIT SER 1", 480, (110, 125, 140)),
}

QQQ = "46090E103"

WINDOWS = [
    ("01jun2024-31aug2024_form13f.zip", "30-JUN-2024", "14-AUG-2024", "24"),
    ("01sep2024-30nov2024_form13f.zip", "30-SEP-2024", "14-NOV-2024", "24"),
    ("01dec2024-28feb2025_form13f.zip", "31-DEC-2024", "14-FEB-2025", "25"),
]


def _tsv(header: list[str], rows: list[list]) -> str:
    return "\n".join("\t".join(str(v) for v in row) for row in [header, *rows]) + "\n"


def write_zips(folder: Path) -> list[Path]:
    """The three filing windows as SEC-style zips in `folder`."""
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for seq, (name, period, filed, yy) in enumerate(WINDOWS):
        submissions, covers, summaries, lines = [], [], [], []
        for cik in range(1, MANAGERS + 1):
            accession = f"{cik:010d}-{yy}-{seq + 1:06d}"
            held = [(cusip, sec) for cusip, sec in SECURITIES.items() if cik <= sec[3][seq]]
            submissions.append([accession, filed, "13F-HR", f"{cik:010d}", period])
            covers.append([accession, "N", "", "", "13F HOLDINGS REPORT", f"Test Manager {cik}"])
            total = 0
            for n, (cusip, (issuer, title, price, _)) in enumerate(held, start=1):
                shares = 1000 * cik + 100 * seq
                total += shares * price
                lines.append([accession, n, issuer, title, cusip, "", shares * price, shares, "SH", ""])
            summaries.append([accession, len(held), total])
        tables = {
            "SUBMISSION.tsv": _tsv(["ACCESSION_NUMBER", "FILING_DATE", "SUBMISSIONTYPE", "CIK", "PERIODOFREPORT"], submissions),
            "COVERPAGE.tsv": _tsv(
                ["ACCESSION_NUMBER", "ISAMENDMENT", "AMENDMENTNO", "AMENDMENTTYPE", "REPORTTYPE", "FILINGMANAGER_NAME"],
                covers,
            ),
            "SUMMARYPAGE.tsv": _tsv(["ACCESSION_NUMBER", "TABLEENTRYTOTAL", "TABLEVALUETOTAL"], summaries),
            "INFOTABLE.tsv": _tsv(
                [
                    "ACCESSION_NUMBER", "INFOTABLE_SK", "NAMEOFISSUER", "TITLEOFCLASS", "CUSIP", "FIGI",
                    "VALUE", "SSHPRNAMT", "SSHPRNAMTTYPE", "PUTCALL",
                ],
                lines,
            ),
        }  # fmt: skip
        path = folder / name
        with zipfile.ZipFile(path, "w") as z:
            for member, text in tables.items():
                z.writestr(member, text)
        paths.append(path)
    return paths
