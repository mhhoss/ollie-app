"""O6: the two-way support relay."""

from __future__ import annotations

import sqlite3

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ollie.bot import copy_fa
from ollie.bot.fsm import Support
from ollie.bot.keyboards import parse_cb, support_reply_keyboard
from ollie.bot.send import send_or_alert
from ollie.config import Config
from ollie.db.repo import customers, orders

router = Router(name="support")


@router.message(F.text == copy_fa.BTN_SUPPORT)
async def start_support_from_menu(message: Message, state: FSMContext) -> None:
    await state.set_state(Support.customer_message)
    await message.answer(copy_fa.O6_CUSTOMER_PROMPT)


@router.callback_query(F.data == "support:start:_")
async def start_support_from_button(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Support.customer_message)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(copy_fa.O6_CUSTOMER_PROMPT)


@router.message(Support.customer_message)
async def relay_to_owner(
    message: Message, conn: sqlite3.Connection, bot: Bot, config: Config, state: FSMContext
) -> None:
    if message.from_user is None:
        return
    await state.clear()

    customer = customers.get(conn, message.from_user.id)
    customer_orders = orders.list_for_customer(conn, message.from_user.id)
    last_order_code = customer_orders[0].code if customer_orders else "-"

    text = copy_fa.O6_SUPPORT_RELAY.format(
        customer_name=(customer.full_name if customer else None) or "-",
        phone=(customer.phone if customer else None) or "-",
        last_order_code=last_order_code,
        message_text=message.text or "",
    )
    await send_or_alert(
        bot,
        config.bot.owner_telegram_id,
        text,
        owner_chat_id=config.bot.owner_telegram_id,
    )
    # a plain send_message call above already carries no reply_markup;
    # send the reply button as a second, distinct message so the owner
    # always has an obvious "answer this" affordance to tap.
    await bot.send_message(
        config.bot.owner_telegram_id,
        copy_fa.BTN_REPLY,
        reply_markup=support_reply_keyboard(message.from_user.id),
    )
    await message.answer(copy_fa.O6_CUSTOMER_SENT_CONFIRMATION)


@router.callback_query(F.data.startswith("support_reply:"))
async def begin_reply(callback: CallbackQuery, state: FSMContext) -> None:
    _, customer_telegram_id, _ = parse_cb(callback.data or "")
    await state.set_state(Support.owner_reply)
    await state.update_data(customer_telegram_id=int(customer_telegram_id))
    await callback.answer()


@router.message(Support.owner_reply)
async def send_reply(message: Message, bot: Bot, state: FSMContext) -> None:
    data = await state.get_data()
    customer_telegram_id = data.get("customer_telegram_id")
    await state.clear()
    if customer_telegram_id is None:
        return
    await bot.send_message(
        int(customer_telegram_id), f"{copy_fa.O6_REPLY_PREFIX}\n\n{message.text or ''}"
    )
