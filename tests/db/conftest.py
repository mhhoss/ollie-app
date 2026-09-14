from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from ollie.db.conn import connect
from ollie.db.migrate import migrate


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "ollie-test.db"


@pytest.fixture
def conn(db_path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(db_path)
    migrate(connection)
    yield connection
    connection.close()


def seed_digital_product(
    conn: sqlite3.Connection, *, product_id: int = 1, price: int = 600_000, credentials: int = 3
) -> None:
    conn.execute(
        "INSERT INTO product (id, kind, name, description, price, cost_price, is_active) "
        "VALUES (?, 'digital', 'اشتراک سه‌ماهه', '', ?, 200000, 1)",
        (product_id, price),
    )
    for i in range(credentials):
        conn.execute(
            "INSERT INTO credential (product_id, payload, status) VALUES (?, ?, 'available')",
            (product_id, f"secret-{product_id}-{i}"),
        )


def seed_physical_product(
    conn: sqlite3.Connection,
    *,
    product_id: int = 2,
    variant_id: int = 1,
    price: int = 100_000,
    stock: int = 3,
) -> None:
    conn.execute(
        "INSERT INTO product (id, kind, name, description, price, cost_price, is_active) "
        "VALUES (?, 'physical', 'گردنبند', '', ?, 40000, 1)",
        (product_id, price),
    )
    conn.execute(
        "INSERT INTO variant (id, product_id, label, price_delta, stock, reserved) "
        "VALUES (?, ?, 'یک عدد', 0, ?, 0)",
        (variant_id, product_id, stock),
    )
