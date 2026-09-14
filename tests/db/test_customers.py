from __future__ import annotations

import sqlite3

import pytest

from ollie.db.errors import CustomerNotFound
from ollie.db.repo import customers

TELEGRAM_ID = 123


def test_get_returns_none_for_unknown_customer(conn: sqlite3.Connection) -> None:
    assert customers.get(conn, TELEGRAM_ID) is None


def test_get_or_create_inserts_once(conn: sqlite3.Connection) -> None:
    first = customers.get_or_create(conn, TELEGRAM_ID)
    second = customers.get_or_create(conn, TELEGRAM_ID)

    assert first == second
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM customer WHERE telegram_id = ?", (TELEGRAM_ID,)
    ).fetchone()["n"]
    assert count == 1


def test_update_profile_overwrites_only_given_fields(conn: sqlite3.Connection) -> None:
    customers.get_or_create(conn, TELEGRAM_ID)
    customers.update_profile(conn, TELEGRAM_ID, full_name="علی محمدی", phone="09121234567")

    updated = customers.update_profile(conn, TELEGRAM_ID, address="تهران")

    assert updated.full_name == "علی محمدی"
    assert updated.phone == "09121234567"
    assert updated.address == "تهران"


def test_update_profile_unknown_customer_raises(conn: sqlite3.Connection) -> None:
    with pytest.raises(CustomerNotFound):
        customers.update_profile(conn, TELEGRAM_ID, full_name="علی محمدی")


def test_set_blocked_flags_customer(conn: sqlite3.Connection) -> None:
    customers.get_or_create(conn, TELEGRAM_ID)
    customers.set_blocked(conn, TELEGRAM_ID, blocked=True)
    assert customers.get(conn, TELEGRAM_ID).is_blocked is True  # type: ignore[union-attr]


def test_set_blocked_unknown_customer_raises(conn: sqlite3.Connection) -> None:
    with pytest.raises(CustomerNotFound):
        customers.set_blocked(conn, TELEGRAM_ID, blocked=True)


def test_customer_id_for_unknown_customer_raises(conn: sqlite3.Connection) -> None:
    with pytest.raises(CustomerNotFound):
        customers.customer_id_for(conn, TELEGRAM_ID)
