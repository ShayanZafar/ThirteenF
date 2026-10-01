"""Load the raw SEC tables into DuckDB exactly as filed.

Every column is kept as text, the way it appears in the zip, and every row is
tagged with the zip it came from. The model (thirteenf.model.build) parses
and derives everything from these tables, so any number can be rebuilt from them.
"""

from __future__ import annotations

import hashlib
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from thirteenf.config import DATA_DIR, RAW_DIR
from thirteenf.db import connect

# SEC file name -> DuckDB table
RAW_TABLES = {
    "SUBMISSION": "raw_submission",
    "COVERPAGE": "raw_coverpage",
    "SUMMARYPAGE": "raw_summarypage",
    "INFOTABLE": "raw_infotable",
}

LOAD_LOG_DDL = """
CREATE TABLE IF NOT EXISTS load_log (
    source_zip   VARCHAR NOT NULL,
    table_name   VARCHAR NOT NULL,
    row_count    BIGINT  NOT NULL,
    zip_bytes    BIGINT  NOT NULL,
    zip_sha256   VARCHAR NOT NULL,
    loaded_at    TIMESTAMP NOT NULL,
    PRIMARY KEY (source_zip, table_name)
)
"""


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_data_lines(path: Path) -> int:
    newlines = 0
    last = b""
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            newlines += chunk.count(b"\n")
            last = chunk
    if last and not last.endswith(b"\n"):
        newlines += 1  # final line without a newline
    return newlines - 1  # header


def _member(archive: zipfile.ZipFile, table: str) -> str:
    for name in archive.namelist():
        if name.rsplit("/", 1)[-1].upper() == f"{table}.TSV":
            return name
    raise FileNotFoundError(f"{table}.tsv not found in {archive.filename}")


def _read_tsv(path: Path) -> str:
    # quote='' and escape='': fields are taken byte for byte, never unquoted.
    return (
        f"read_csv('{path.as_posix()}', delim='\\t', header=true, quote='', escape='', "
        f"all_varchar=true, auto_detect=true)"
    )


def ensure_load_log(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(LOAD_LOG_DDL)


def already_loaded(con: duckdb.DuckDBPyConnection, zip_name: str, sha: str) -> bool:
    row = con.execute(
        "SELECT count(*) FROM load_log WHERE source_zip = ? AND zip_sha256 = ?", [zip_name, sha]
    ).fetchone()
    return row[0] == len(RAW_TABLES)


def load_zip(
    con: duckdb.DuckDBPyConnection, zip_path: Path, log=print, work_root: Path | None = None
) -> bool:
    """Load one zip. Returns False when the same file was already loaded."""
    zip_name = zip_path.name
    sha = sha256_of(zip_path)
    if already_loaded(con, zip_name, sha):
        log(f"  {zip_name}: already loaded")
        return False

    work = (work_root or DATA_DIR / "tmp") / zip_path.stem
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    try:
        with zipfile.ZipFile(zip_path) as archive:
            extracted = {t: Path(archive.extract(_member(archive, t), work)) for t in RAW_TABLES}

        loaded_at = datetime.now(timezone.utc).replace(tzinfo=None)
        con.execute("BEGIN TRANSACTION")
        try:
            con.execute("DELETE FROM load_log WHERE source_zip = ?", [zip_name])
            for sec_name, table in RAW_TABLES.items():
                source = _read_tsv(extracted[sec_name])
                con.execute(
                    f"CREATE TABLE IF NOT EXISTS {table} AS "
                    f"SELECT *, ''::VARCHAR AS source_zip FROM {source} LIMIT 0"
                )
                # Loading the same zip twice replaces its rows rather than adding to them.
                con.execute(f"DELETE FROM {table} WHERE source_zip = ?", [zip_name])
                con.execute(
                    f"INSERT INTO {table} BY NAME SELECT *, ?::VARCHAR AS source_zip FROM {source}",
                    [zip_name],
                )
                rows = con.execute(
                    f"SELECT count(*) FROM {table} WHERE source_zip = ?", [zip_name]
                ).fetchone()[0]
                expected = count_data_lines(extracted[sec_name])
                if rows != expected:
                    raise ValueError(
                        f"{zip_name} {sec_name}: loaded {rows:,} rows but the file has {expected:,}"
                    )
                con.execute(
                    "INSERT INTO load_log VALUES (?, ?, ?, ?, ?, ?)",
                    [zip_name, table, rows, zip_path.stat().st_size, sha, loaded_at],
                )
                log(f"  {zip_name}: {table} {rows:,} rows")
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return True


def load_all(log=print) -> None:
    zips = sorted(RAW_DIR.glob("*_form13f.zip"))
    if not zips:
        raise FileNotFoundError(f"No *_form13f.zip files in {RAW_DIR}; run python -m thirteenf.ingest")
    with connect() as con:
        ensure_load_log(con)
        log(f"Loading {len(zips)} zips into DuckDB")
        for zip_path in zips:
            load_zip(con, zip_path, log=log)
