"""
Digital-goods inventory. Reservation happens inside
`repo/orders.py:create()` (stock is claimed at checkout, per C9 — "now,
not at approval"), so this module's own transaction is only
`deliver()`: the one place a credential moves reserved -> delivered,
and the roadmap's third named single-transaction function.
"""

from __future__ import annotations

import dataclasses
import sqlite3
from collections.abc import Callable

from ollie.db.errors import CredentialNotFound
from ollie.domain.models import Credential, CredentialStatus

_SELECT = (
    'SELECT c.*, o.code AS order_code FROM credential c LEFT JOIN "order" o ON o.id = c.order_id '
)


def get(conn: sqlite3.Connection, credential_id: int) -> Credential | None:
    row = conn.execute(_SELECT + "WHERE c.id = ?", (credential_id,)).fetchone()
    return _credential_from_row(row) if row is not None else None


def count_available(conn: sqlite3.Connection, product_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM credential WHERE product_id = ? AND status = 'available'",
        (product_id,),
    ).fetchone()
    return int(row["n"])


def deliver(
    conn: sqlite3.Connection,
    credential_id: int,
    *,
    delivered_at: int,
    send: Callable[[], bool],
) -> Credential:
    """
    Mark a reserved credential delivered — but only after `send()`
    (the actual Telegram call) reports success. `send` runs *inside*
    this transaction, between the read and the write, so "delivered in
    the database" and "actually sent" can never disagree: if `send()`
    returns False or raises, the transaction rolls back and the
    credential is left exactly as it was — still `reserved`, still
    available to retry. This is the trap the spec calls out by name:
    "an undelivered credential marked delivered is unrecoverable
    without the event log" — this function makes that outcome
    impossible rather than relying on the event log to detect it after
    the fact.

    Raises CredentialNotFound if the id doesn't exist, or ValueError if
    it exists but isn't currently `reserved` (delivering twice, or
    delivering one that was never reserved, are both caller bugs).
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(_SELECT + "WHERE c.id = ?", (credential_id,)).fetchone()
        if row is None:
            raise CredentialNotFound(credential_id)
        credential = _credential_from_row(row)
        if credential.status != CredentialStatus.RESERVED:
            raise ValueError(
                f"credential {credential_id} is {credential.status.value}, not reserved "
                f"— it cannot be delivered"
            )

        if not send():
            conn.execute("ROLLBACK")
            return credential

        conn.execute(
            "UPDATE credential SET status = 'delivered', delivered_at = ? WHERE id = ?",
            (delivered_at, credential_id),
        )
        conn.execute("COMMIT")
        return dataclasses.replace(
            credential, status=CredentialStatus.DELIVERED, delivered_at=delivered_at
        )
    except Exception:
        conn.execute("ROLLBACK")
        raise


def _credential_from_row(row: sqlite3.Row) -> Credential:
    return Credential(
        id=row["id"],
        product_id=row["product_id"],
        payload=row["payload"],
        status=CredentialStatus(row["status"]),
        order_code=row["order_code"],
        delivered_at=row["delivered_at"],
    )
