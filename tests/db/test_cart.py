from __future__ import annotations

import sqlite3
from pathlib import Path

from ollie.db.repo import cart, customers

TELEGRAM_ID = 900


def _seed_products(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO product (id, kind, name, description, price, cost_price, is_active) "
        "VALUES (1, 'digital', 'a', '', 1000, 500, 1)"
    )
    conn.execute(
        "INSERT INTO product (id, kind, name, description, price, cost_price, is_active) "
        "VALUES (2, 'digital', 'b', '', 1000, 500, 1)"
    )
    conn.execute(
        "INSERT INTO variant (id, product_id, label, price_delta, stock, reserved) "
        "VALUES (1, 1, 'v1', 0, 5, 0)"
    )
    conn.execute(
        "INSERT INTO variant (id, product_id, label, price_delta, stock, reserved) "
        "VALUES (2, 1, 'v2', 0, 5, 0)"
    )


def test_add_item_twice_increments_quantity(conn: sqlite3.Connection) -> None:
    _seed_products(conn)
    customers.get_or_create(conn, TELEGRAM_ID)
    cart.add_item(conn, TELEGRAM_ID, product_id=1, variant_id=None, quantity=1)
    cart.add_item(conn, TELEGRAM_ID, product_id=1, variant_id=None, quantity=1)

    items = cart.list_items(conn, TELEGRAM_ID)
    assert items == [cart.CartLine(product_id=1, variant_id=None, quantity=2)]


def test_add_item_distinguishes_variants(conn: sqlite3.Connection) -> None:
    _seed_products(conn)
    customers.get_or_create(conn, TELEGRAM_ID)
    cart.add_item(conn, TELEGRAM_ID, product_id=1, variant_id=1, quantity=1)
    cart.add_item(conn, TELEGRAM_ID, product_id=1, variant_id=2, quantity=1)

    items = cart.list_items(conn, TELEGRAM_ID)
    assert {i.variant_id for i in items} == {1, 2}


def test_set_quantity_to_zero_removes_line(conn: sqlite3.Connection) -> None:
    _seed_products(conn)
    customers.get_or_create(conn, TELEGRAM_ID)
    cart.add_item(conn, TELEGRAM_ID, product_id=1, variant_id=None, quantity=3)
    cart.set_quantity(conn, TELEGRAM_ID, product_id=1, variant_id=None, quantity=0)
    assert cart.list_items(conn, TELEGRAM_ID) == []


def test_remove_item(conn: sqlite3.Connection) -> None:
    _seed_products(conn)
    customers.get_or_create(conn, TELEGRAM_ID)
    cart.add_item(conn, TELEGRAM_ID, product_id=1, variant_id=None, quantity=1)
    cart.remove_item(conn, TELEGRAM_ID, product_id=1, variant_id=None)
    assert cart.list_items(conn, TELEGRAM_ID) == []


def test_clear_empties_the_whole_cart(conn: sqlite3.Connection) -> None:
    _seed_products(conn)
    customers.get_or_create(conn, TELEGRAM_ID)
    cart.add_item(conn, TELEGRAM_ID, product_id=1, variant_id=None, quantity=1)
    cart.add_item(conn, TELEGRAM_ID, product_id=2, variant_id=None, quantity=1)
    cart.clear(conn, TELEGRAM_ID)
    assert cart.list_items(conn, TELEGRAM_ID) == []


def test_cart_survives_across_connections(db_path: Path) -> None:
    from ollie.db.conn import connect
    from ollie.db.migrate import migrate

    conn1 = connect(db_path)
    migrate(conn1)
    _seed_products(conn1)
    customers.get_or_create(conn1, TELEGRAM_ID)
    cart.add_item(conn1, TELEGRAM_ID, product_id=1, variant_id=None, quantity=2)
    conn1.close()

    conn2 = connect(db_path)
    assert cart.list_items(conn2, TELEGRAM_ID) == [
        cart.CartLine(product_id=1, variant_id=None, quantity=2)
    ]
    conn2.close()
