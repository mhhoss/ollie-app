"""
Customer rows, keyed everywhere outside this module by `telegram_id` —
`ollie.domain.models.Customer` has no surrogate id at all (see
models.py's module docstring). `_customer_id` is the one place that
surrogate `customer.id` leaks out, and only as far as `repo/orders.py`,
which needs it for the FK column.
"""

from __future__ import annotations

import sqlite3

from ollie.db.errors import CustomerNotFound
from ollie.domain.models import Customer


def get(conn: sqlite3.Connection, telegram_id: int) -> Customer | None:
    row = conn.execute("SELECT * FROM customer WHERE telegram_id = ?", (telegram_id,)).fetchone()
    return _customer_from_row(row) if row is not None else None


def get_or_create(conn: sqlite3.Connection, telegram_id: int) -> Customer:
    """Upsert-on-first-contact (C1: "Upsert customer on first /start").
    A single transaction so two near-simultaneous /start taps from the
    same brand-new user can't both try to insert the row."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        existing = get(conn, telegram_id)
        if existing is not None:
            conn.execute("COMMIT")
            return existing
        conn.execute(
            "INSERT INTO customer (telegram_id, is_blocked) VALUES (?, 0)",
            (telegram_id,),
        )
        conn.execute("COMMIT")
        return Customer(telegram_id=telegram_id)
    except Exception:
        conn.execute("ROLLBACK")
        raise


def update_profile(
    conn: sqlite3.Connection,
    telegram_id: int,
    *,
    full_name: str | None = None,
    phone: str | None = None,
    address: str | None = None,
    postal_code: str | None = None,
) -> Customer:
    """Overwrites only the fields explicitly passed; omitted ones keep
    their stored value. Raises CustomerNotFound if telegram_id has
    never been seen — get_or_create() is what creates the row."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        current = get(conn, telegram_id)
        if current is None:
            raise CustomerNotFound(telegram_id)
        updated = Customer(
            telegram_id=telegram_id,
            full_name=full_name if full_name is not None else current.full_name,
            phone=phone if phone is not None else current.phone,
            address=address if address is not None else current.address,
            postal_code=postal_code if postal_code is not None else current.postal_code,
            is_blocked=current.is_blocked,
        )
        conn.execute(
            "UPDATE customer SET full_name = ?, phone = ?, address = ?, postal_code = ? "
            "WHERE telegram_id = ?",
            (updated.full_name, updated.phone, updated.address, updated.postal_code, telegram_id),
        )
        conn.execute("COMMIT")
        return updated
    except Exception:
        conn.execute("ROLLBACK")
        raise


def set_blocked(conn: sqlite3.Connection, telegram_id: int, *, blocked: bool) -> None:
    """E7: flag a customer after too many rejections. Read-then-write is
    fine here (no transaction) — the only writer of is_blocked is the
    owner-facing flow this backs, never a concurrent one."""
    cursor = conn.execute(
        "UPDATE customer SET is_blocked = ? WHERE telegram_id = ?",
        (int(blocked), telegram_id),
    )
    if cursor.rowcount == 0:
        raise CustomerNotFound(telegram_id)


def customer_id_for(conn: sqlite3.Connection, telegram_id: int) -> int:
    """The one place customer.id (the surrogate FK column) is exposed —
    used only by repo/orders.py to populate order.customer_id."""
    row = conn.execute("SELECT id FROM customer WHERE telegram_id = ?", (telegram_id,)).fetchone()
    if row is None:
        raise CustomerNotFound(telegram_id)
    return int(row["id"])


def _customer_from_row(row: sqlite3.Row) -> Customer:
    return Customer(
        telegram_id=row["telegram_id"],
        full_name=row["full_name"],
        phone=row["phone"],
        address=row["address"],
        postal_code=row["postal_code"],
        is_blocked=bool(row["is_blocked"]),
    )
