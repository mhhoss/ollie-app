"""C15: order history."""

from __future__ import annotations

import sqlite3

from aiogram import F, Router
from aiogram.types import Message

from ollie.bot import copy_fa
from ollie.bot.keyboards import history_keyboard
from ollie.bot.rendering import history_row
from ollie.db.repo import orders

router = Router(name="history")


@router.message(F.text == copy_fa.BTN_MY_ORDERS)
async def show_history(message: Message, conn: sqlite3.Connection) -> None:
    if message.from_user is None:
        return
    customer_orders = orders.list_for_customer(conn, message.from_user.id)
    if not customer_orders:
        await message.answer(copy_fa.C15_EMPTY_HISTORY)
        return
    rows = [(order.code, history_row(order)) for order in customer_orders]
    await message.answer(copy_fa.C15_HISTORY_HEADER, reply_markup=history_keyboard(rows))
