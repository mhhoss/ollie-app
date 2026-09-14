from __future__ import annotations

import sqlite3

import pytest

from ollie.db.errors import CredentialNotFound
from ollie.db.repo import credentials, customers, orders
from ollie.domain.models import CredentialStatus, OrderItem, ProductKind
from tests.db.conftest import seed_digital_product

NOW = 1_757_000_000
TELEGRAM_ID = 7


def _make_order(conn: sqlite3.Connection) -> str:
    seed_digital_product(conn)
    customers.get_or_create(conn, TELEGRAM_ID)
    order = orders.create(
        conn,
        customer_telegram_id=TELEGRAM_ID,
        items=[
            OrderItem(
                product_id=1,
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


def _reserved_credential_id(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT id FROM credential WHERE status = 'reserved'").fetchone()
    assert row is not None
    return int(row["id"])


async def _always_true() -> bool:
    return True


async def _always_false() -> bool:
    return False


@pytest.mark.asyncio
async def test_deliver_marks_delivered_only_after_send_succeeds(conn: sqlite3.Connection) -> None:
    _make_order(conn)
    credential_id = _reserved_credential_id(conn)

    delivered = await credentials.deliver(
        conn, credential_id, delivered_at=NOW + 5, send=_always_true
    )

    assert delivered.status == CredentialStatus.DELIVERED
    assert delivered.delivered_at == NOW + 5
    row = conn.execute("SELECT status FROM credential WHERE id = ?", (credential_id,)).fetchone()
    assert row["status"] == "delivered"


@pytest.mark.asyncio
async def test_failed_send_rolls_back_and_leaves_credential_reserved(
    conn: sqlite3.Connection,
) -> None:
    """The roadmap's third named checkpoint: a delivery callback that
    fails must not leave the credential marked delivered."""
    _make_order(conn)
    credential_id = _reserved_credential_id(conn)

    result = await credentials.deliver(
        conn, credential_id, delivered_at=NOW + 5, send=_always_false
    )

    assert result.status == CredentialStatus.RESERVED
    row = conn.execute(
        "SELECT status, delivered_at FROM credential WHERE id = ?", (credential_id,)
    ).fetchone()
    assert row["status"] == "reserved"
    assert row["delivered_at"] is None


@pytest.mark.asyncio
async def test_send_raising_also_leaves_credential_reserved(conn: sqlite3.Connection) -> None:
    _make_order(conn)
    credential_id = _reserved_credential_id(conn)

    async def boom() -> bool:
        raise RuntimeError("telegram is down")

    with pytest.raises(RuntimeError):
        await credentials.deliver(conn, credential_id, delivered_at=NOW + 5, send=boom)

    row = conn.execute("SELECT status FROM credential WHERE id = ?", (credential_id,)).fetchone()
    assert row["status"] == "reserved"


@pytest.mark.asyncio
async def test_deliver_twice_is_rejected(conn: sqlite3.Connection) -> None:
    _make_order(conn)
    credential_id = _reserved_credential_id(conn)
    await credentials.deliver(conn, credential_id, delivered_at=NOW + 5, send=_always_true)

    with pytest.raises(ValueError, match="not reserved"):
        await credentials.deliver(conn, credential_id, delivered_at=NOW + 6, send=_always_true)


@pytest.mark.asyncio
async def test_deliver_unknown_id_raises_credential_not_found(conn: sqlite3.Connection) -> None:
    with pytest.raises(CredentialNotFound):
        await credentials.deliver(conn, 9999, delivered_at=NOW, send=_always_true)


def test_get_resolves_order_code_for_reserved_credential(conn: sqlite3.Connection) -> None:
    code = _make_order(conn)
    credential_id = _reserved_credential_id(conn)
    credential = credentials.get(conn, credential_id)
    assert credential is not None
    assert credential.order_code == code
