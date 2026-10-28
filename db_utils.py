"""Read-only SQLite access for the OSU P-card audit dashboard."""
from __future__ import annotations

import gzip
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import time
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent
ARCHIVE_PATH = ROOT / "data" / "pcards.db.gz"
LOCAL_PATH = Path(tempfile.gettempdir()) / "osupcards_case2_v1.db"
OUTPUT_ROW_LIMIT = 200
SEARCH_ROW_LIMIT = 500


class QueryRejected(ValueError):
    """Query was rejected before/during execution for safety."""


def ensure_database() -> Path:
    """Expand the bundled gzip database to writable temp storage, if required."""
    if not ARCHIVE_PATH.exists():
        raise FileNotFoundError("Missing data/pcards.db.gz — check the GitHub repository contents.")
    if LOCAL_PATH.exists() and LOCAL_PATH.stat().st_size > 100_000_000:
        return LOCAL_PATH
    temp_path = LOCAL_PATH.with_suffix(".db.partial")
    try:
        with gzip.open(ARCHIVE_PATH, "rb") as src, temp_path.open("wb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
        if temp_path.stat().st_size < 100_000_000:
            raise ValueError("Database archive appears incomplete.")
        temp_path.replace(LOCAL_PATH)
    finally:
        temp_path.unlink(missing_ok=True)
    return LOCAL_PATH


def connect() -> sqlite3.Connection:
    path = ensure_database()
    # file is immutable for the app; no write access is ever needed.
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
    connection.execute("PRAGMA query_only = ON")
    return connection


def get_overview() -> dict[str, Any]:
    with connect() as c:
        n, people, total = c.execute(
            "SELECT COUNT(*), COUNT(DISTINCT FullName), SUM(Amount) FROM pcards"
        ).fetchone()
        years = [r[0] for r in c.execute(
            "SELECT DISTINCT Year FROM pcards ORDER BY Year DESC")]
    return {"transactions": n, "employees": people, "net_amount": total, "years": years}


def get_year_summary(year: int) -> dict[str, Any]:
    with connect() as c:
        r = c.execute(
            "SELECT COUNT(*), COUNT(DISTINCT FullName), COUNT(DISTINCT Vendor), "
            "SUM(Amount) FROM pcards WHERE Year=? AND AgencyNumber=1000", (year,)
        ).fetchone()
    return {"transactions": r[0], "employees": r[1], "vendors": r[2], "net_amount": r[3] or 0}


def search_field(year: int, field: str, term: str) -> tuple[pd.DataFrame, int]:
    """Parameterised, literal substring match in one approved field."""
    if field not in {"Description", "Vendor"}:
        raise QueryRejected("Invalid search field")
    clean = term.strip()
    if not clean:
        return pd.DataFrame(), 0
    if len(clean) > 120:
        raise QueryRejected("Use a keyword of 120 characters or fewer")
    # Escape LIKE's wildcard characters, so a term is searched literally.
    escaped = clean.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    where = f'Year = ? AND AgencyNumber = 1000 AND "{field}" LIKE ? ESCAPE \'\\\''
    params = (year, f"%{escaped}%")
    with connect() as c:
        total = c.execute(f"SELECT COUNT(*) FROM pcards WHERE {where}", params).fetchone()[0]
        frame = pd.read_sql_query(
            f"SELECT TransactionDate AS Date, FullName AS Employee, Vendor, Description, "
            f"ROUND(Amount, 2) AS Amount_USD, MCC, PostedDate FROM pcards "
            f"WHERE {where} ORDER BY ABS(Amount) DESC, ID ASC LIMIT {SEARCH_ROW_LIMIT}",
            c, params=params,
        )
    return frame, total


_SAFE_FUNCTIONS = {
    "abs", "avg", "coalesce", "count", "date", "datetime", "dense_rank",
    "first_value", "glob", "group_concat", "ifnull", "iif", "instr",
    "julianday", "lag", "last_value", "lead", "length", "like", "lower",
    "ltrim", "max", "min", "nullif", "ntile", "percent_rank", "printf",
    "rank", "replace", "round", "row_number", "rtrim", "strftime",
    "substr", "substring", "sum", "time", "total", "trim", "typeof",
    "unixepoch", "upper",
}


def validate_query(sql: str) -> str:
    if not isinstance(sql, str):
        raise QueryRejected("The generated query must be text")
    value = sql.strip()
    if len(value) < 8 or len(value) > 10000:
        raise QueryRejected("Query length outside permitted range")
    if not re.match(r"^(SELECT|WITH)\b", value, re.IGNORECASE):
        raise QueryRejected("Only SELECT queries are permitted")
    if ";" in value.rstrip(";"):
        raise QueryRejected("Multiple SQL statements are not permitted")
    value = value.rstrip(";").strip()
    # A model should not need comments; disallow to limit evasion tricks.
    if "--" in value or "/*" in value or "*/" in value:
        raise QueryRejected("SQL comments are not permitted")
    return value


def run_readonly_query(sql: str, max_rows: int = OUTPUT_ROW_LIMIT, max_seconds: int = 12) -> tuple[pd.DataFrame, bool]:
    """Execute a single read-only SELECT, with a database authorizer and timeout."""
    query = validate_query(sql)
    if not 1 <= max_rows <= 500:
        raise QueryRejected("Invalid row limit")
    start = time.monotonic()
    conn = connect()
    try:
        def authorizer(action: int, first: str | None, second: str | None,
                       database: str | None, source: str | None) -> int:
            if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE):
                return sqlite3.SQLITE_OK
            if action == sqlite3.SQLITE_READ:
                return sqlite3.SQLITE_OK if (first or "").lower() == "pcards" else sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_FUNCTION:
                return sqlite3.SQLITE_OK if (second or "").lower() in _SAFE_FUNCTIONS else sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_DENY

        conn.set_authorizer(authorizer)
        conn.set_progress_handler(
            lambda: int(time.monotonic() - start > max_seconds), 10000
        )
        # LIMIT is applied outside the model-generated query so the model cannot bypass it.
        wrapped = f"SELECT * FROM ({query}) AS audit_results LIMIT {max_rows + 1}"
        try:
            cursor = conn.execute(wrapped)
            names = [d[0] for d in cursor.description]
            rows = cursor.fetchall()
        except sqlite3.DatabaseError as exc:
            raise QueryRejected(f"SQLite rejected the query: {exc}") from exc
        truncated = len(rows) > max_rows
        return pd.DataFrame(rows[:max_rows], columns=names), truncated
    finally:
        conn.close()
