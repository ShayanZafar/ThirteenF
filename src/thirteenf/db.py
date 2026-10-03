"""DuckDB connections.

DuckDB lets one process write at a time, and a writer locks out readers in
other processes. Writers here hold the file only briefly, so both sides wait
a little for the lock before giving up.
"""

import time

import duckdb

from thirteenf.config import DB_PATH


class Busy(RuntimeError):
    """Another process is writing to the database."""


def connect(read_only: bool = False, wait_seconds: float = 60.0) -> duckdb.DuckDBPyConnection:
    if not read_only:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            con = duckdb.connect(str(DB_PATH), read_only=read_only)
            break
        except duckdb.IOException as err:
            if "lock" not in str(err).lower():
                raise
            if time.monotonic() >= deadline:
                raise Busy(str(err)) from err
            time.sleep(0.2)
    con.execute("SET enable_progress_bar = false")
    return con
