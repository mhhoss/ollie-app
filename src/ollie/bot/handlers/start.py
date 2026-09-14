"""C1: welcome, first-contact upsert, and the `/start p_<product_id>` deep link."""

from __future__ import annotations

import sqlite3

from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message

from ollie.bot import copy_fa
from ollie.bot.handlers import catalog
from ollie.bot.keyboards import root_reply_keyboard
from ollie.config import Config
from ollie.db.repo import customers

router = Router(name="start")


@router.message(CommandStart())
async def start(
    message: Message, command: CommandObject, conn: sqlite3.Connection, config: Config
) -> None:
    if message.from_user is None:
        return
    customers.get_or_create(conn, message.from_user.id)

    await message.answer(
        copy_fa.C1_WELCOME.format(store_name=config.store.name),
        reply_markup=root_reply_keyboard(),
    )

    payload = command.args
    if payload and payload.startswith("p_"):
        product_id_raw = payload.removeprefix("p_")
        if product_id_raw.isdigit():
            await catalog.send_product_detail(message, conn, int(product_id_raw))
