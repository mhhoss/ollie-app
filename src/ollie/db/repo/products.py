"""
Catalog reads. Products and variants are the one part of the schema
with genuine soft-delete semantics (`is_active`): an order references
a product forever, so nothing here ever deletes a row, and
`list_active_products` is the only function that filters on it —
`get_product`/`get_variant` intentionally return inactive rows too,
since an existing order still needs to render them.
"""

from __future__ import annotations

import sqlite3

from ollie.domain.models import Product, ProductKind, Variant


def get_product(conn: sqlite3.Connection, product_id: int) -> Product | None:
    row = conn.execute("SELECT * FROM product WHERE id = ?", (product_id,)).fetchone()
    return _product_from_row(row) if row is not None else None


def get_variant(conn: sqlite3.Connection, variant_id: int) -> Variant | None:
    row = conn.execute("SELECT * FROM variant WHERE id = ?", (variant_id,)).fetchone()
    return _variant_from_row(row) if row is not None else None


def list_variants(conn: sqlite3.Connection, product_id: int) -> list[Variant]:
    rows = conn.execute("SELECT * FROM variant WHERE product_id = ?", (product_id,)).fetchall()
    return [_variant_from_row(row) for row in rows]


def list_active_products(
    conn: sqlite3.Connection, *, category_id: int | None = None
) -> list[Product]:
    if category_id is None:
        rows = conn.execute("SELECT * FROM product WHERE is_active = 1 ORDER BY id").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM product WHERE is_active = 1 AND category_id = ? ORDER BY id",
            (category_id,),
        ).fetchall()
    return [_product_from_row(row) for row in rows]


def _product_from_row(row: sqlite3.Row) -> Product:
    return Product(
        id=row["id"],
        kind=ProductKind(row["kind"]),
        name=row["name"],
        description=row["description"],
        price=row["price"],
        cost_price=row["cost_price"],
        is_active=bool(row["is_active"]),
        category_id=row["category_id"],
        photo_file_id=row["photo_file_id"],
    )


def _variant_from_row(row: sqlite3.Row) -> Variant:
    return Variant(
        id=row["id"],
        product_id=row["product_id"],
        label=row["label"],
        price_delta=row["price_delta"],
        stock=row["stock"],
        reserved=row["reserved"],
    )
