"""
Cart persistence — C5's own rule: "lives in the DB keyed by
customer_id, not in memory. A restart must not lose it." No domain
object backs a cart line (`ollie.domain` has no notion of one; a cart
is pre-order scratch state, not a business record with invariants of
its own), so `CartLine` is a plain dataclass local to this module.

Every function takes a `telegram_id`, not a surrogate `customer_id` —
consistent with the rest of `repo/`, the surrogate id never crosses
this module's boundary.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ollie.db.repo.customers import customer_id_for


@dataclass(frozen=True, slots=True)
class CartLine:
    product_id: int
    variant_id: int | None
    quantity: int


def list_items(conn: sqlite3.Connection, telegram_id: int) -> list[CartLine]:
    customer_id = customer_id_for(conn, telegram_id)
    rows = conn.execute(
        "SELECT product_id, variant_id, quantity FROM cart_item WHERE customer_id = ? ORDER BY id",
        (customer_id,),
    ).fetchall()
    return [
        CartLine(
            product_id=row["product_id"], variant_id=row["variant_id"], quantity=row["quantity"]
        )
        for row in rows
    ]


def add_item(
    conn: sqlite3.Connection,
    telegram_id: int,
    *,
    product_id: int,
    variant_id: int | None,
    quantity: int = 1,
) -> None:
    """Adds `quantity` more of this exact (product, variant) pair — a
    second tap on the same line increments rather than duplicating it
    (C4: "tapping again increments. No separate quantity step")."""
    customer_id = customer_id_for(conn, telegram_id)
    existing = conn.execute(
        "SELECT id, quantity FROM cart_item WHERE customer_id = ? AND product_id = ? "
        "AND variant_id IS ?",
        (customer_id, product_id, variant_id),
    ).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO cart_item (customer_id, product_id, variant_id, quantity) "
            "VALUES (?, ?, ?, ?)",
            (customer_id, product_id, variant_id, quantity),
        )
    else:
        conn.execute(
            "UPDATE cart_item SET quantity = ? WHERE id = ?",
            (existing["quantity"] + quantity, existing["id"]),
        )


def set_quantity(
    conn: sqlite3.Connection,
    telegram_id: int,
    *,
    product_id: int,
    variant_id: int | None,
    quantity: int,
) -> None:
    """Sets the line to an exact quantity; 0 or less removes it entirely."""
    customer_id = customer_id_for(conn, telegram_id)
    if quantity <= 0:
        conn.execute(
            "DELETE FROM cart_item WHERE customer_id = ? AND product_id = ? AND variant_id IS ?",
            (customer_id, product_id, variant_id),
        )
        return
    conn.execute(
        "UPDATE cart_item SET quantity = ? "
        "WHERE customer_id = ? AND product_id = ? AND variant_id IS ?",
        (quantity, customer_id, product_id, variant_id),
    )


def remove_item(
    conn: sqlite3.Connection, telegram_id: int, *, product_id: int, variant_id: int | None
) -> None:
    customer_id = customer_id_for(conn, telegram_id)
    conn.execute(
        "DELETE FROM cart_item WHERE customer_id = ? AND product_id = ? AND variant_id IS ?",
        (customer_id, product_id, variant_id),
    )


def clear(conn: sqlite3.Connection, telegram_id: int) -> None:
    customer_id = customer_id_for(conn, telegram_id)
    conn.execute("DELETE FROM cart_item WHERE customer_id = ?", (customer_id,))
