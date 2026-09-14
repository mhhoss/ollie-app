from __future__ import annotations

import sqlite3
from pathlib import Path

from ollie.db.conn import connect
from ollie.db.migrate import CURRENT_VERSION, migrate


def test_migrate_on_fresh_file_creates_all_tables(db_path: Path) -> None:
    conn = connect(db_path)
    migrate(conn)

    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    assert {
        "product",
        "variant",
        "credential",
        "customer",
        "order",
        "order_item",
        "receipt",
        "event_log",
        "cart_item",
    } <= tables
    conn.close()


def test_migrate_stamps_user_version(db_path: Path) -> None:
    conn = connect(db_path)
    migrate(conn)
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == CURRENT_VERSION
    conn.close()


def test_migrate_is_idempotent(db_path: Path) -> None:
    conn = connect(db_path)
    migrate(conn)
    migrate(conn)  # must not raise (e.g. "table already exists")
    conn.close()


def test_open_payable_amount_index_rejects_duplicate_among_open_orders(
    conn: sqlite3.Connection,
) -> None:
    conn.execute("INSERT INTO customer (telegram_id, is_blocked) VALUES (1, 0)")
    conn.execute(
        'INSERT INTO "order" (code, customer_id, state, subtotal, shipping_cost, amount_tail, '
        "payable_amount, is_physical, reject_count, created_at, expires_at) "
        "VALUES ('AAAAAA', 1, 'awaiting_receipt', 100, 0, 347, 447, 0, 0, 1, 100)"
    )
    import pytest

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            'INSERT INTO "order" (code, customer_id, state, subtotal, shipping_cost, '
            "amount_tail, payable_amount, is_physical, reject_count, created_at, expires_at) "
            "VALUES ('BBBBBB', 1, 'receipt_submitted', 100, 0, 347, 447, 0, 0, 1, 100)"
        )
