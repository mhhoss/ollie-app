from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from ollie.bot import sweeper
from ollie.config import Config
from ollie.db.repo import customers, orders
from ollie.domain.models import OrderItem, ProductKind
from ollie.domain.states import OrderState

NOW = 1_757_000_000
DAY = 24 * 3600
TELEGRAM_ID = 500


def _seed_digital(conn: sqlite3.Connection, product_id: int = 1, credentials: int = 3) -> None:
    conn.execute(
        "INSERT INTO product (id, kind, name, description, price, cost_price, is_active) "
        "VALUES (?, 'digital', 'p', '', 100000, 50000, 1)",
        (product_id,),
    )
    for i in range(credentials):
        conn.execute(
            "INSERT INTO credential (product_id, payload, status) VALUES (?, ?, 'available')",
            (product_id, f"secret-{i}"),
        )


def _make_order(conn: sqlite3.Connection, *, created_at: int) -> str:
    _seed_digital(conn)
    customers.get_or_create(conn, TELEGRAM_ID)
    order = orders.create(
        conn,
        customer_telegram_id=TELEGRAM_ID,
        items=[
            OrderItem(
                product_id=1,
                variant_id=None,
                kind=ProductKind.DIGITAL,
                name_snapshot="p",
                unit_price=100000,
                cost_price_snapshot=50000,
                quantity=1,
            )
        ],
        shipping_cost=0,
        payment_window_hours=24,
        created_at=created_at,
    )
    return order.code


@pytest.mark.asyncio
async def test_expires_unpaid_order_past_window_and_notifies_customer(
    conn: sqlite3.Connection, config: Config, fake_bot: Any
) -> None:
    code = _make_order(conn, created_at=NOW - 25 * 3600)  # created 25h ago, 24h window

    await sweeper.sweep_once(conn, fake_bot, config, now=NOW)

    order = orders.get(conn, code)
    assert order is not None
    assert order.state == OrderState.EXPIRED
    assert any(chat == TELEGRAM_ID and code in text for chat, text in fake_bot.sent)


@pytest.mark.asyncio
async def test_expired_order_released_its_credential(
    conn: sqlite3.Connection, config: Config, fake_bot: Any
) -> None:
    code = _make_order(conn, created_at=NOW - 25 * 3600)

    await sweeper.sweep_once(conn, fake_bot, config, now=NOW)

    row = conn.execute(
        'SELECT status FROM credential WHERE order_id = (SELECT id FROM "order" WHERE code = ?)',
        (code,),
    ).fetchone()
    assert row is None  # order_id cleared on release
    available = conn.execute(
        "SELECT COUNT(*) AS n FROM credential WHERE status = 'available'"
    ).fetchone()["n"]
    assert available == 3


@pytest.mark.asyncio
async def test_order_not_yet_past_expiry_is_untouched(
    conn: sqlite3.Connection, config: Config, fake_bot: Any
) -> None:
    code = _make_order(conn, created_at=NOW - 1 * 3600)  # only 1h old

    await sweeper.sweep_once(conn, fake_bot, config, now=NOW)

    order = orders.get(conn, code)
    assert order is not None
    assert order.state == OrderState.AWAITING_RECEIPT


@pytest.mark.asyncio
async def test_rejected_order_expires_after_retry_window_elapses(
    conn: sqlite3.Connection, config: Config, fake_bot: Any
) -> None:
    code = _make_order(conn, created_at=NOW - 30 * 3600)
    orders.transition(
        conn,
        code,
        OrderState.RECEIPT_SUBMITTED,
        actor="customer",
        at=NOW - 26 * 3600,
        expires_at=None,
    )
    orders.transition(
        conn, code, OrderState.REJECTED, actor="owner", at=NOW - 25 * 3600, reject_count=1
    )

    await sweeper.sweep_once(conn, fake_bot, config, now=NOW)

    order = orders.get(conn, code)
    assert order is not None
    assert order.state == OrderState.EXPIRED


@pytest.mark.asyncio
async def test_rejected_order_within_retry_window_is_untouched(
    conn: sqlite3.Connection, config: Config, fake_bot: Any
) -> None:
    code = _make_order(conn, created_at=NOW - 5 * 3600)
    orders.transition(
        conn,
        code,
        OrderState.RECEIPT_SUBMITTED,
        actor="customer",
        at=NOW - 4 * 3600,
        expires_at=None,
    )
    orders.transition(
        conn, code, OrderState.REJECTED, actor="owner", at=NOW - 3 * 3600, reject_count=1
    )

    await sweeper.sweep_once(conn, fake_bot, config, now=NOW)

    order = orders.get(conn, code)
    assert order is not None
    assert order.state == OrderState.REJECTED


@pytest.mark.asyncio
async def test_invariant_violation_alerts_owner(
    conn: sqlite3.Connection, config: Config, fake_bot: Any
) -> None:
    code = _make_order(conn, created_at=NOW)
    orders.transition(
        conn, code, OrderState.RECEIPT_SUBMITTED, actor="customer", at=NOW, expires_at=None
    )
    orders.transition(conn, code, OrderState.APPROVED, actor="owner", at=NOW, approved_at=NOW)
    orders.transition(conn, code, OrderState.FULFILLED, actor="system", at=NOW, fulfilled_at=NOW)
    # Force a broken invariant directly: a credential still reserved
    # against an order that's already fulfilled.
    conn.execute("UPDATE credential SET status = 'reserved' WHERE order_id IS NOT NULL")

    await sweeper.sweep_once(conn, fake_bot, config, now=NOW)

    assert any(chat == config.bot.owner_telegram_id for chat, _ in fake_bot.sent)
