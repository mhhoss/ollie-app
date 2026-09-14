from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from ollie.db.conn import connect
from ollie.db.errors import OrderNotFound
from ollie.db.migrate import migrate
from ollie.db.repo import customers, events, orders
from ollie.domain.errors import IllegalTransition, InsufficientStock
from ollie.domain.models import OrderItem, ProductKind
from ollie.domain.states import OrderState
from tests.db.conftest import seed_digital_product, seed_physical_product

NOW = 1_757_000_000
TELEGRAM_ID = 42


def _digital_item(product_id: int = 1, quantity: int = 1) -> OrderItem:
    return OrderItem(
        product_id=product_id,
        variant_id=None,
        kind=ProductKind.DIGITAL,
        name_snapshot="اشتراک سه‌ماهه",
        unit_price=600_000,
        cost_price_snapshot=200_000,
        quantity=quantity,
    )


def _physical_item(product_id: int = 2, variant_id: int = 1, quantity: int = 1) -> OrderItem:
    return OrderItem(
        product_id=product_id,
        variant_id=variant_id,
        kind=ProductKind.PHYSICAL,
        name_snapshot="گردنبند",
        unit_price=100_000,
        cost_price_snapshot=40_000,
        quantity=quantity,
    )


def test_create_reserves_digital_credential_and_persists_order(
    conn: sqlite3.Connection,
) -> None:
    seed_digital_product(conn)
    customers.get_or_create(conn, TELEGRAM_ID)

    order = orders.create(
        conn,
        customer_telegram_id=TELEGRAM_ID,
        items=[_digital_item()],
        shipping_cost=0,
        payment_window_hours=24,
        created_at=NOW,
    )

    assert order.state == OrderState.AWAITING_RECEIPT
    assert order.subtotal == 600_000
    assert order.expires_at == NOW + 24 * 3600

    reserved = conn.execute(
        "SELECT COUNT(*) AS n FROM credential WHERE status = 'reserved' AND order_id IS NOT NULL"
    ).fetchone()["n"]
    assert reserved == 1

    fetched = orders.get(conn, order.code)
    assert fetched == order


def test_create_reserves_physical_stock(conn: sqlite3.Connection) -> None:
    seed_physical_product(conn, stock=3)
    customers.get_or_create(conn, TELEGRAM_ID)

    orders.create(
        conn,
        customer_telegram_id=TELEGRAM_ID,
        items=[_physical_item(quantity=2)],
        shipping_cost=30_000,
        payment_window_hours=24,
        created_at=NOW,
        ship_name="علی محمدی",
        ship_phone="09121234567",
        ship_address="تهران، خیابان آزادی، پلاک ۱",
    )

    row = conn.execute("SELECT stock, reserved FROM variant WHERE id = 1").fetchone()
    assert row["reserved"] == 2
    assert row["stock"] == 3  # stock itself only drops on fulfillment bookkeeping, not reserve


def test_create_rolls_back_entirely_on_insufficient_stock(conn: sqlite3.Connection) -> None:
    seed_physical_product(conn, stock=1)
    customers.get_or_create(conn, TELEGRAM_ID)

    with pytest.raises(InsufficientStock):
        orders.create(
            conn,
            customer_telegram_id=TELEGRAM_ID,
            items=[_physical_item(quantity=5)],
            shipping_cost=0,
            payment_window_hours=24,
            created_at=NOW,
            ship_name="علی محمدی",
            ship_phone="09121234567",
            ship_address="تهران، خیابان آزادی، پلاک ۱",
        )

    count = conn.execute('SELECT COUNT(*) AS n FROM "order"').fetchone()["n"]
    assert count == 0
    row = conn.execute("SELECT reserved FROM variant WHERE id = 1").fetchone()
    assert row["reserved"] == 0  # the partial reservation from before the failure didn't stick


def test_two_orders_never_get_the_same_payable_amount(conn: sqlite3.Connection) -> None:
    seed_digital_product(conn, credentials=5)
    customers.get_or_create(conn, TELEGRAM_ID)

    a = orders.create(
        conn,
        customer_telegram_id=TELEGRAM_ID,
        items=[_digital_item()],
        shipping_cost=0,
        payment_window_hours=24,
        created_at=NOW,
    )
    b = orders.create(
        conn,
        customer_telegram_id=TELEGRAM_ID,
        items=[_digital_item()],
        shipping_cost=0,
        payment_window_hours=24,
        created_at=NOW,
    )
    assert a.payable_amount != b.payable_amount


def test_concurrent_create_never_issues_the_same_payable_amount(db_path: Path) -> None:
    """
    The roadmap's named checkpoint: fire many concurrent create() calls
    for the same product from separate connections (separate threads,
    separate sqlite3.Connection objects — real concurrency, not just
    interleaved calls on one connection) and confirm the partial unique
    index plus the allocation retry loop together guarantee every
    payable_amount that lands is distinct.
    """
    setup = connect(db_path)
    migrate(setup)
    seed_digital_product(setup, credentials=20)
    customers.get_or_create(setup, TELEGRAM_ID)
    setup.close()

    n_threads = 8
    results: list[int] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker() -> None:
        thread_conn = connect(db_path)
        try:
            order = orders.create(
                thread_conn,
                customer_telegram_id=TELEGRAM_ID,
                items=[_digital_item()],
                shipping_cost=0,
                payment_window_hours=24,
                created_at=NOW,
            )
            with lock:
                results.append(order.payable_amount)
        except BaseException as exc:  # noqa: BLE001 - collected and asserted below
            with lock:
                errors.append(exc)
        finally:
            thread_conn.close()

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(results) == n_threads
    assert len(set(results)) == n_threads


def test_transition_updates_state_and_logs_one_event(conn: sqlite3.Connection) -> None:
    seed_digital_product(conn)
    customers.get_or_create(conn, TELEGRAM_ID)
    order = orders.create(
        conn,
        customer_telegram_id=TELEGRAM_ID,
        items=[_digital_item()],
        shipping_cost=0,
        payment_window_hours=24,
        created_at=NOW,
    )

    updated = orders.transition(
        conn,
        order.code,
        OrderState.RECEIPT_SUBMITTED,
        actor="customer",
        at=NOW + 10,
        expires_at=None,
    )

    assert updated.state == OrderState.RECEIPT_SUBMITTED
    log = events.list_for_order(conn, order.code)
    assert [e.to_state for e in log] == ["awaiting_receipt", "receipt_submitted"]


def test_double_transition_from_the_same_source_state_leaves_exactly_one_event_row(
    conn: sqlite3.Connection,
) -> None:
    """
    The roadmap's second named checkpoint: two callers both try to move
    the same order (receipt_submitted -> approved). The first succeeds
    and logs one event; the second re-reads under the write lock, sees
    the order is already approved, and IllegalTransition stops it before
    it can write a second row for the same edge.
    """
    seed_digital_product(conn)
    customers.get_or_create(conn, TELEGRAM_ID)
    order = orders.create(
        conn,
        customer_telegram_id=TELEGRAM_ID,
        items=[_digital_item()],
        shipping_cost=0,
        payment_window_hours=24,
        created_at=NOW,
    )
    orders.transition(
        conn,
        order.code,
        OrderState.RECEIPT_SUBMITTED,
        actor="customer",
        at=NOW + 10,
        expires_at=None,
    )

    orders.transition(
        conn,
        order.code,
        OrderState.APPROVED,
        actor="owner",
        at=NOW + 20,
        approved_at=NOW + 20,
    )
    with pytest.raises(IllegalTransition):
        orders.transition(
            conn,
            order.code,
            OrderState.APPROVED,
            actor="owner",
            at=NOW + 21,
            approved_at=NOW + 21,
        )

    log = events.list_for_order(conn, order.code)
    approved_events = [e for e in log if e.to_state == "approved"]
    assert len(approved_events) == 1


def test_transition_on_unknown_code_raises_order_not_found(conn: sqlite3.Connection) -> None:
    with pytest.raises(OrderNotFound):
        orders.transition(conn, "ZZZZZZ", OrderState.CANCELLED, actor="customer", at=NOW)


def test_list_for_customer_returns_orders_newest_first(conn: sqlite3.Connection) -> None:
    seed_digital_product(conn, credentials=5)
    customers.get_or_create(conn, TELEGRAM_ID)
    first = orders.create(
        conn,
        customer_telegram_id=TELEGRAM_ID,
        items=[_digital_item()],
        shipping_cost=0,
        payment_window_hours=24,
        created_at=NOW,
    )
    second = orders.create(
        conn,
        customer_telegram_id=TELEGRAM_ID,
        items=[_digital_item()],
        shipping_cost=0,
        payment_window_hours=24,
        created_at=NOW + 10,
    )

    history = orders.list_for_customer(conn, TELEGRAM_ID)
    assert [o.code for o in history] == [second.code, first.code]
