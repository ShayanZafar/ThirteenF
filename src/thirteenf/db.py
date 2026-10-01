"""DuckDB connections."""

import duckdb

from thirteenf.config import DB_PATH


def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    if not read_only:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH), read_only=read_only)
    con.execute("SET enable_progress_bar = false")
    return con
