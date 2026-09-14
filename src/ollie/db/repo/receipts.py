"""
Receipt evidence. `submit()` implements C10's two named rules in one
transaction: a duplicate image hash against *another* order is
rejected outright (DuplicateReceipt), and a second photo on the *same*
order deactivates the first rather than being rejected — "keep both
rows in receipt; only the latest is active."
"""

from __future__ import annotations

import sqlite3

from ollie.db.errors import OrderNotFound
from ollie.domain.errors import DuplicateReceipt
from ollie.domain.models import Receipt, ReceiptVerdict


def submit(
    conn: sqlite3.Connection,
    *,
    order_code: str,
    file_id: str,
    file_unique_id: str,
    image_hash: str,
    submitted_at: int,
) -> Receipt:
    conn.execute("BEGIN IMMEDIATE")
    try:
        order_row = conn.execute('SELECT id FROM "order" WHERE code = ?', (order_code,)).fetchone()
        if order_row is None:
            raise OrderNotFound(order_code)
        order_id = int(order_row["id"])

        dup = conn.execute(
            "SELECT 1 FROM receipt WHERE image_hash = ? AND order_id != ?",
            (image_hash, order_id),
        ).fetchone()
        if dup is not None:
            raise DuplicateReceipt(
                f"image_hash {image_hash!r} was already submitted on another order"
            )

        conn.execute("UPDATE receipt SET is_active = 0 WHERE order_id = ?", (order_id,))
        conn.execute(
            "INSERT INTO receipt "
            "(order_id, file_id, file_unique_id, image_hash, is_active, submitted_at) "
            "VALUES (?, ?, ?, ?, 1, ?)",
            (order_id, file_id, file_unique_id, image_hash, submitted_at),
        )
        conn.execute("COMMIT")
        return Receipt(
            order_code=order_code,
            file_id=file_id,
            file_unique_id=file_unique_id,
            image_hash=image_hash,
            is_active=True,
            submitted_at=submitted_at,
        )
    except Exception:
        conn.execute("ROLLBACK")
        raise


def get_active(conn: sqlite3.Connection, order_code: str) -> Receipt | None:
    row = conn.execute(
        'SELECT r.* FROM receipt r JOIN "order" o ON o.id = r.order_id '
        "WHERE o.code = ? AND r.is_active = 1",
        (order_code,),
    ).fetchone()
    return _receipt_from_row(row, order_code) if row is not None else None


def review(
    conn: sqlite3.Connection,
    order_code: str,
    *,
    verdict: ReceiptVerdict,
    reviewed_at: int,
    reject_reason: str | None = None,
) -> Receipt:
    """Record O1/O2's verdict on the currently-active receipt. Does not
    touch order state — repo/orders.py:transition() is the single place
    that changes an order's state and writes event_log; this only
    records the review outcome on the evidence row itself."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        order_row = conn.execute('SELECT id FROM "order" WHERE code = ?', (order_code,)).fetchone()
        if order_row is None:
            raise OrderNotFound(order_code)
        order_id = int(order_row["id"])

        active = conn.execute(
            "SELECT * FROM receipt WHERE order_id = ? AND is_active = 1", (order_id,)
        ).fetchone()
        if active is None:
            raise OrderNotFound(f"order {order_code!r} has no active receipt")

        conn.execute(
            "UPDATE receipt SET verdict = ?, reject_reason = ?, reviewed_at = ? WHERE id = ?",
            (verdict.value, reject_reason, reviewed_at, active["id"]),
        )
        conn.execute("COMMIT")
        return Receipt(
            order_code=order_code,
            file_id=active["file_id"],
            file_unique_id=active["file_unique_id"],
            image_hash=active["image_hash"],
            is_active=True,
            submitted_at=active["submitted_at"],
            verdict=verdict,
            reject_reason=reject_reason,
            reviewed_at=reviewed_at,
        )
    except Exception:
        conn.execute("ROLLBACK")
        raise


def _receipt_from_row(row: sqlite3.Row, order_code: str) -> Receipt:
    return Receipt(
        order_code=order_code,
        file_id=row["file_id"],
        file_unique_id=row["file_unique_id"],
        image_hash=row["image_hash"],
        is_active=bool(row["is_active"]),
        submitted_at=row["submitted_at"],
        verdict=ReceiptVerdict(row["verdict"]) if row["verdict"] is not None else None,
        reject_reason=row["reject_reason"],
        reviewed_at=row["reviewed_at"],
    )
