from __future__ import annotations

import sqlite3

from ollie.db.repo import products
from tests.db.conftest import seed_digital_product, seed_physical_product


def test_get_product_returns_none_for_unknown_id(conn: sqlite3.Connection) -> None:
    assert products.get_product(conn, 999) is None


def test_get_product_roundtrips(conn: sqlite3.Connection) -> None:
    seed_digital_product(conn, product_id=1)
    product = products.get_product(conn, 1)
    assert product is not None
    assert product.price == 600_000
    assert product.is_active is True


def test_get_variant_roundtrips(conn: sqlite3.Connection) -> None:
    seed_physical_product(conn, product_id=2, variant_id=5, stock=4)
    variant = products.get_variant(conn, 5)
    assert variant is not None
    assert variant.stock == 4
    assert variant.reserved == 0


def test_list_variants_for_product(conn: sqlite3.Connection) -> None:
    seed_physical_product(conn, product_id=2, variant_id=5)
    conn.execute(
        "INSERT INTO variant (id, product_id, label, price_delta, stock, reserved) "
        "VALUES (6, 2, 'دو عدد', 5000, 2, 0)"
    )
    variants = products.list_variants(conn, 2)
    assert {v.id for v in variants} == {5, 6}


def test_list_active_products_excludes_inactive(conn: sqlite3.Connection) -> None:
    seed_digital_product(conn, product_id=1)
    conn.execute(
        "INSERT INTO product (id, kind, name, description, price, cost_price, is_active) "
        "VALUES (2, 'digital', 'قدیمی', '', 10000, 5000, 0)"
    )
    active = products.list_active_products(conn)
    assert [p.id for p in active] == [1]


def test_list_active_products_filters_by_category(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO product (id, category_id, kind, name, description, price, cost_price, "
        "is_active) VALUES (1, 10, 'digital', 'الف', '', 1000, 500, 1)"
    )
    conn.execute(
        "INSERT INTO product (id, category_id, kind, name, description, price, cost_price, "
        "is_active) VALUES (2, 20, 'digital', 'ب', '', 1000, 500, 1)"
    )
    result = products.list_active_products(conn, category_id=10)
    assert [p.id for p in result] == [1]
