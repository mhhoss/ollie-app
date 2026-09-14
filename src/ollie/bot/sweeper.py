"""
The 5-minute background loop. Three jobs, each independent of the
others so a bug in one never blocks the other two:

1. Expire `awaiting_receipt` orders past `expires_at` — release
   reservations (via `orders.transition`'s own cancelled/expired
   handling), notify the customer.
2. Expire `rejected` orders that were never resubmitted within the
   configured retry window — the `(rejected -> expired)` edge added
   post-M1-draft. This is the policy `ollie.domain.states` and
   `docs/roadmap.md` both left open for this module to decide: the
   window reuses `payment_window_hours` (a rejected order gets the
   same grace period a fresh one does, not a separate config value —
   one number for a customer to reason about, not two), and the clock
   reads from `event_log`, not a new column on `order` (see
   `repo.orders.list_rejected_past_retry_window`'s own docstring).
3. Run `ollie.domain.validate.validate_snapshot` over every order and
   credential, alerting the owner on any violation. This is the safety
   net behind everything above: if a bug ever left a credential
   `reserved` against a terminal order, this is what surfaces it
   instead of it sitting silently wrong for months.

`sweep_once()` is a plain async function taking an explicit `now` —
deliberately not reaching for `time.time()` internally — so a test can
drive it against a fabricated clock without waiting on a real one.
`run_forever()` is the thin wrapper `main.py` schedules as a background
task.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time

from aiogram import Bot

from ollie.bot import copy_fa
from ollie.bot.send import send_or_alert
from ollie.config import Config
from ollie.db.conn import connect
from ollie.db.repo import credentials as credentials_repo
from ollie.db.repo import orders as orders_repo
from ollie.domain.models import Order
from ollie.domain.states import OrderState
from ollie.domain.validate import validate_snapshot

logger = logging.getLogger(__name__)

SWEEP_INTERVAL_SECONDS = 300


async def sweep_once(conn: sqlite3.Connection, bot: Bot, config: Config, *, now: int) -> None:
    await _expire_unpaid_orders(conn, bot, config, now=now)
    await _expire_unretried_rejections(conn, bot, config, now=now)
    await _alert_on_invariant_violations(conn, bot, config, now=now)


async def _expire_unpaid_orders(
    conn: sqlite3.Connection, bot: Bot, config: Config, *, now: int
) -> None:
    for order in orders_repo.list_awaiting_receipt_past_expiry(conn, now):
        orders_repo.transition(
            conn, order.code, OrderState.EXPIRED, actor="system", at=now, expires_at=None
        )
        await send_or_alert(
            bot,
            order.customer_telegram_id,
            copy_fa.C15_EXPIRED_NOTICE.format(order_code=order.code),
            owner_chat_id=config.bot.owner_telegram_id,
            order_code=order.code,
        )


async def _expire_unretried_rejections(
    conn: sqlite3.Connection, bot: Bot, config: Config, *, now: int
) -> None:
    window_seconds = config.order.payment_window_hours * 3600
    for order in orders_repo.list_rejected_past_retry_window(
        conn, window_seconds=window_seconds, now=now
    ):
        orders_repo.transition(conn, order.code, OrderState.EXPIRED, actor="system", at=now)
        await send_or_alert(
            bot,
            order.customer_telegram_id,
            copy_fa.C15_EXPIRED_NOTICE.format(order_code=order.code),
            owner_chat_id=config.bot.owner_telegram_id,
            order_code=order.code,
        )


async def _alert_on_invariant_violations(
    conn: sqlite3.Connection, bot: Bot, config: Config, *, now: int
) -> None:
    # validate_snapshot needs every order in scope, not just the open
    # ones — a credential legitimately delivered against a fulfilled
    # order would otherwise look like it "references an order that
    # does not exist in this snapshot" (see validate.py's own check).
    all_orders = _all_orders(conn)
    all_credentials = credentials_repo.list_all(conn)
    report = validate_snapshot(all_orders, all_credentials, now=now)
    if not report.ok:
        lines = "\n".join(f"- {error}" for error in report.errors)
        logger.error("sweeper found invariant violations:\n%s", lines)
        await send_or_alert(
            bot,
            config.bot.owner_telegram_id,
            f"⚠️ Ollie invariant check failed:\n{lines}",
            owner_chat_id=config.bot.owner_telegram_id,
        )


def _all_orders(conn: sqlite3.Connection) -> list[Order]:
    rows = conn.execute('SELECT code FROM "order"').fetchall()
    return [order for row in rows if (order := orders_repo.get(conn, row["code"])) is not None]


async def run_forever(config: Config, bot: Bot) -> None:
    """Scheduled by main.py as a background task; runs until cancelled."""
    conn = connect(config.runtime.db_path)
    try:
        while True:
            try:
                await sweep_once(conn, bot, config, now=int(time.time()))
            except Exception:  # noqa: BLE001 - one bad sweep must not kill the loop
                logger.exception("sweeper iteration failed")
            await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
    finally:
        conn.close()
