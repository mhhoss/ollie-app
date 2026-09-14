"""
Schema migrations, versioned on `PRAGMA user_version` — needed from
day one, not added later: every client runs its own copy of this
database on its own VPS, so "everyone is on the same schema" can never
be assumed the way it can behind a single shared service. A forgotten
migration on one client's file is a corrupted store, silently, the
first time a query assumes a column that isn't there yet.

Version 0 (a brand-new file) gets the full `schema.sql` applied in one
`executescript` and is stamped version 1. A future schema change adds
another `if version < N` branch here with its own `ALTER TABLE` /
backfill statements — `schema.sql` itself only ever describes the
*current* shape, never a diff.
"""

from __future__ import annotations

import sqlite3
from importlib import resources

CURRENT_VERSION = 1


def migrate(conn: sqlite3.Connection) -> None:
    version = _user_version(conn)
    if version >= CURRENT_VERSION:
        return

    if version == 0:
        schema_sql = resources.files("ollie.db").joinpath("schema.sql").read_text(encoding="utf-8")
        conn.executescript(schema_sql)
        version = 1

    conn.execute(f"PRAGMA user_version = {version}")


def _user_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0])
