"""
Connection factory. Every connection this codebase opens goes through
`connect()` so the PRAGMAs below are a fact enforced once, not a habit
every call site has to remember.

`isolation_level=None` puts sqlite3 in autocommit mode: the driver
never opens a transaction behind the caller's back. Every repo
function that needs one opens it explicitly with `BEGIN IMMEDIATE`
(acquiring the write lock up front, so a concurrent writer blocks
instead of racing) and closes it with `COMMIT` or `ROLLBACK`. That
explicitness is what makes "these three functions are each a single
transaction" a checkable fact rather than an assumption about
sqlite3's default behavior.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn
