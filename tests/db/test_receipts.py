from __future__ import annotations

import sqlite3

import pytest

from ollie.db.errors import OrderNotFound
from ollie.db.repo import customers, orders, receipts
from ollie.domain.errors import DuplicateReceipt
from ollie.domain.models import OrderItem, ProductKind, ReceiptVerdict
from tests.db.conftest import seed_digital_product

NOW = 1_757_000_000
TELEGRAM_ID = 55


def _make_order(conn: sqlite3.Connection, product_id: int = 1) -> str:
    seed_digital_product(conn, product_id=product_id)
    customers.get_or_create(conn, TELEGRAM_ID)
    order = orders.create(
        conn,
        customer_telegram_id=TELEGRAM_ID,
        items=[
            OrderItem(
                product_id=product_id,
                variant_id=None,
                kind=ProductKind.DIGITAL,
                name_snapshot="اشتراک سه‌ماهه",
                unit_price=600_000,
                cost_price_snapshot=200_000,
                quantity=1,
            )
        ],
        shipping_cost=0,
        payment_window_hours=24,
        created_at=NOW,
    )
    return order.code


def test_submit_creates_active_receipt(conn: sqlite3.Connection) -> None:
    code = _make_order(conn)
    receipt = receipts.submit(
        conn,
        order_code=code,
        file_id="file-1",
        file_unique_id="uniq-1",
        image_hash="hash-1",
        submitted_at=NOW + 1,
    )
    assert receipt.is_active is True
    assert receipts.get_active(conn, code) == receipt


def test_resubmission_deactivates_the_previous_receipt(conn: sqlite3.Connection) -> None:
    code = _make_order(conn)
    receipts.submit(
        conn,
        order_code=code,
        file_id="f1",
        file_unique_id="u1",
        image_hash="h1",
        submitted_at=NOW,
    )
    second = receipts.submit(
        conn,
        order_code=code,
        file_id="f2",
        file_unique_id="u2",
        image_hash="h2",
        submitted_at=NOW + 5,
    )

    active = receipts.get_active(conn, code)
    assert active is not None
    assert active.file_id == "f2"
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM receipt WHERE image_hash IN ('h1', 'h2')"
    ).fetchone()["n"]
    assert count == 2  # both rows kept
    assert second.is_active is True


def test_duplicate_image_hash_against_another_order_is_rejected(
    conn: sqlite3.Connection,
) -> None:
    code_a = _make_order(conn, product_id=1)
    code_b = _make_order(conn, product_id=2)
    receipts.submit(
        conn,
        order_code=code_a,
        file_id="f1",
        file_unique_id="u1",
        image_hash="shared-hash",
        submitted_at=NOW,
    )

    with pytest.raises(DuplicateReceipt):
        receipts.submit(
            conn,
            order_code=code_b,
            file_id="f2",
            file_unique_id="u2",
            image_hash="shared-hash",
            submitted_at=NOW + 1,
        )


def test_submit_unknown_order_raises(conn: sqlite3.Connection) -> None:
    with pytest.raises(OrderNotFound):
        receipts.submit(
            conn,
            order_code="ZZZZZZ",
            file_id="f",
            file_unique_id="u",
            image_hash="h",
            submitted_at=NOW,
        )


def test_review_records_verdict_without_touching_order_state(conn: sqlite3.Connection) -> None:
    code = _make_order(conn)
    receipts.submit(
        conn,
        order_code=code,
        file_id="f1",
        file_unique_id="u1",
        image_hash="h1",
        submitted_at=NOW,
    )

    reviewed = receipts.review(
        conn,
        code,
        verdict=ReceiptVerdict.REJECTED,
        reviewed_at=NOW + 10,
        reject_reason="مبلغ مطابقت ندارد",
    )

    assert reviewed.verdict == ReceiptVerdict.REJECTED
    assert reviewed.reject_reason == "مبلغ مطابقت ندارد"
    order = orders.get(conn, code)
    assert order is not None
    assert order.state.value == "awaiting_receipt"  # untouched by review()
