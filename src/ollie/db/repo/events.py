"""
`event_log` — the append-only audit trail every FSM transition writes
a row to. `log_event` deliberately does not open its own transaction:
it is always called from inside another function's (orders.create,
orders.transition) transaction, so the event row commits or rolls back
atomically with the state change it's recording. Calling it outside
such a transaction is a caller bug, not something this module guards
against.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Event:
    order_code: str
    from_state: str | None
    to_state: str
    actor: str
    detail: str | None
    at: int


def log_event(
    conn: sqlite3.Connection,
    order_id: int,
    *,
    from_state: str | None,
    to_state: str,
    actor: str,
    detail: str | None,
    at: int,
) -> None:
    conn.execute(
        "INSERT INTO event_log (order_id, from_state, to_state, actor, detail, at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (order_id, from_state, to_state, actor, detail, at),
    )


def list_for_order(conn: sqlite3.Connection, order_code: str) -> list[Event]:
    rows = conn.execute(
        "SELECT e.from_state, e.to_state, e.actor, e.detail, e.at "
        'FROM event_log e JOIN "order" o ON o.id = e.order_id '
        "WHERE o.code = ? ORDER BY e.at, e.id",
        (order_code,),
    ).fetchall()
    return [
        Event(
            order_code=order_code,
            from_state=row["from_state"],
            to_state=row["to_state"],
            actor=row["actor"],
            detail=row["detail"],
            at=row["at"],
        )
        for row in rows
    ]
