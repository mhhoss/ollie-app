"""
Persistence: SQLite behind plain functions, no ORM.

`conn.py` opens connections with the PRAGMAs the rest of this package
assumes are always on (WAL, foreign keys, a busy timeout). `migrate.py`
applies `schema.sql` and tracks the schema version on
`PRAGMA user_version`. `repo/` holds one module per aggregate; each
function takes a connection as its first argument and returns (or
raises about) `ollie.domain` objects — never a raw `sqlite3.Row` to a
caller outside this package.

Three functions in `repo/orders.py` and `repo/credentials.py` are each
a single all-or-nothing transaction, guarded with `BEGIN IMMEDIATE` so
a concurrent writer blocks rather than races: `orders.create`,
`orders.transition`, and `credentials.deliver`. See their docstrings.
"""

from __future__ import annotations
