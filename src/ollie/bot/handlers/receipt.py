"""
C10-C11: receipt upload, duplicate-image rejection, and the handoff to
the owner's O1 notification — the product's "heartbeat", per its own
spec note.

Which order a photo belongs to is resolved by looking at the
customer's own orders for the single one currently open for a receipt
(`awaiting_receipt` or `rejected`) — M1 assumes a customer has at most
one such order at a time, consistent with the spec's single-order-at-
a-time walkthrough; a customer who somehow has two simultaneously open
orders is a real edge case this module doesn't disambiguate and picks
the most recently created one, documented here rather than silently.
"""

from __future__ import annotations

import hashlib
import sqlite3
import time

from aiogram import Bot, F, Router
from aiogram.types import Message

from ollie.bot import copy_fa
from ollie.bot.keyboards import owner_new_receipt_keyboard
from ollie.bot.rendering import (
    build_owner_receipt_items_block,
    format_date,
    is_order_open_for_receipt,
)
from ollie.bot.send import send_or_alert
from ollie.config import Config
from ollie.db.repo import customers, orders
from ollie.db.repo import receipts as receipts_repo
from ollie.domain.errors import DuplicateReceipt
from ollie.domain.models import Order
from ollie.domain.states import OrderState
from ollie.fmt.money import toman

router = Router(name="receipt")


def _find_open_order(conn: sqlite3.Connection, telegram_id: int) -> Order | None:
    candidates = [
        o for o in orders.list_for_customer(conn, telegram_id) if is_order_open_for_receipt(o)
    ]
    return candidates[0] if candidates else None


@router.message(F.photo)
async def receive_photo(
    message: Message, conn: sqlite3.Connection, bot: Bot, config: Config
) -> None:
    if message.from_user is None:
        return
    order = _find_open_order(conn, message.from_user.id)
    if order is None:
        return
    if not message.photo:
        return
    largest = message.photo[-1]
    file_bytes = await bot.download(largest.file_id)
    image_hash = hashlib.sha256(file_bytes.read()).hexdigest()  # type: ignore[union-attr]
    await _process_receipt(
        message, conn, bot, config, order, largest.file_id, largest.file_unique_id, image_hash
    )


@router.message(F.document)
async def receive_document(
    message: Message, conn: sqlite3.Connection, bot: Bot, config: Config
) -> None:
    if message.from_user is None or message.document is None:
        return
    order = _find_open_order(conn, message.from_user.id)
    if order is None:
        return
    if not (message.document.mime_type or "").startswith("image/"):
        await message.answer(copy_fa.C10_ERROR_WRONG_FILE_TYPE)
        return
    file_bytes = await bot.download(message.document.file_id)
    image_hash = hashlib.sha256(file_bytes.read()).hexdigest()  # type: ignore[union-attr]
    await _process_receipt(
        message,
        conn,
        bot,
        config,
        order,
        message.document.file_id,
        message.document.file_unique_id,
        image_hash,
    )


async def _process_receipt(
    message: Message,
    conn: sqlite3.Connection,
    bot: Bot,
    config: Config,
    order: Order,
    file_id: str,
    file_unique_id: str,
    image_hash: str,
) -> None:
    now = int(time.time())
    try:
        receipts_repo.submit(
            conn,
            order_code=order.code,
            file_id=file_id,
            file_unique_id=file_unique_id,
            image_hash=image_hash,
            submitted_at=now,
        )
    except DuplicateReceipt:
        await message.answer(copy_fa.C10_ERROR_DUPLICATE_IMAGE)
        await send_or_alert(
            bot,
            config.bot.owner_telegram_id,
            copy_fa.O1_DUPLICATE_WARNING.format(other_order_code=order.code),
            owner_chat_id=config.bot.owner_telegram_id,
        )
        return

    updated = orders.transition(
        conn, order.code, OrderState.RECEIPT_SUBMITTED, actor="customer", at=now, expires_at=None
    )
    await message.answer(copy_fa.C11_AWAITING_APPROVAL.format(order_code=order.code))

    customer = customers.get(conn, order.customer_telegram_id)
    owner_text = copy_fa.O1_NEW_RECEIPT.format(
        order_code=order.code,
        customer_name=(customer.full_name if customer else None) or "-",
        phone=(customer.phone if customer else None) or "-",
        payable_amount=toman(updated.payable_amount),
        datetime=format_date(now),
        items_block=build_owner_receipt_items_block(updated.items),
    )
    keyboard = owner_new_receipt_keyboard(order.code, OrderState.RECEIPT_SUBMITTED.value)
    try:
        await bot.send_photo(
            config.bot.owner_telegram_id, file_id, caption=owner_text, reply_markup=keyboard
        )
    except Exception:  # noqa: BLE001 - fall back to a text-only notification rather than lose it
        await send_or_alert(
            bot,
            config.bot.owner_telegram_id,
            owner_text,
            owner_chat_id=config.bot.owner_telegram_id,
            order_code=order.code,
        )
