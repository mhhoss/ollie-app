"""
C6-C9: name, phone, (address, postal for a physical cart), then the
invoice itself. `orders.create()` does the actual reservation and
allocation as one transaction (Phase 5) — this module's job is only
collecting and validating the typed fields the spec calls for, then
handing a fully-formed item list to that transaction.

Validation patterns mirror `ollie.domain.models`'s own private regexes
(`^09\\d{9}$` for phone, `^\\d{10}$` for postal) rather than importing
them — those are private to that module by design (each domain
invariant is re-checked at construction time regardless of what a
caller validated first), so this is deliberate duplication of a simple
pattern, not a shortcut around the domain layer's own checks.
"""

from __future__ import annotations

import re
import sqlite3
import time

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ollie.bot import copy_fa
from ollie.bot.fsm import Checkout
from ollie.bot.keyboards import (
    back_to_cart_keyboard,
    invoice_keyboard,
    parse_cb,
    phone_request_keyboard,
    receipt_prompt_keyboard,
    remove_reply_keyboard,
    saved_profile_keyboard,
)
from ollie.bot.rendering import build_invoice_text, item_price
from ollie.config import Config
from ollie.db.errors import OrderNotFound
from ollie.db.repo import cart as cart_repo
from ollie.db.repo import customers, orders
from ollie.db.repo import products as products_repo
from ollie.domain.errors import IllegalTransition, InsufficientStock
from ollie.domain.models import OrderItem, ProductKind
from ollie.domain.states import OrderState
from ollie.fmt.digits import normalize_identifier, normalize_text

router = Router(name="checkout")

_PHONE_RE = re.compile(r"^09\d{9}$")
_POSTAL_RE = re.compile(r"^\d{10}$")


@router.callback_query(F.data == "cart:checkout:_")
async def begin_checkout(
    callback: CallbackQuery, conn: sqlite3.Connection, state: FSMContext
) -> None:
    if callback.from_user is None:
        return
    await callback.answer()
    customer = customers.get(conn, callback.from_user.id)
    if customer is not None and customer.full_name and customer.phone:
        await callback.message.answer(  # type: ignore[union-attr]
            copy_fa.C6_SAVED_PROFILE_PROMPT.format(
                full_name=customer.full_name, phone=customer.phone
            ),
            reply_markup=saved_profile_keyboard(),
        )
        return
    await state.set_state(Checkout.name)
    await callback.message.answer(copy_fa.C6_ASK_NAME, reply_markup=back_to_cart_keyboard())  # type: ignore[union-attr]


@router.callback_query(F.data.startswith("profile:"))
async def profile_choice(
    callback: CallbackQuery, conn: sqlite3.Connection, config: Config, state: FSMContext
) -> None:
    if callback.from_user is None:
        return
    _, action, _ = parse_cb(callback.data or "")
    await callback.answer()
    if action == "change":
        await state.set_state(Checkout.name)
        await callback.message.answer(copy_fa.C6_ASK_NAME, reply_markup=back_to_cart_keyboard())  # type: ignore[union-attr]
        return

    customer = customers.get(conn, callback.from_user.id)
    if customer is None or not customer.full_name or not customer.phone:
        await state.set_state(Checkout.name)
        await callback.message.answer(copy_fa.C6_ASK_NAME, reply_markup=back_to_cart_keyboard())  # type: ignore[union-attr]
        return
    await state.update_data(full_name=customer.full_name, phone=customer.phone)
    if _cart_has_physical_item(conn, callback.from_user.id):
        if customer.address and customer.postal_code:
            await state.update_data(address=customer.address, postal_code=customer.postal_code)
            await _finalize(callback.message, conn, config, state, callback.from_user.id)  # type: ignore[arg-type]
        else:
            await state.set_state(Checkout.address)
            await callback.message.answer(copy_fa.C8_ASK_ADDRESS)  # type: ignore[union-attr]
    else:
        await _finalize(callback.message, conn, config, state, callback.from_user.id)  # type: ignore[arg-type]


@router.message(Checkout.name)
async def receive_name(message: Message, state: FSMContext) -> None:
    name = normalize_text(message.text or "")
    if len(name) < 5 or len(name) > 60 or " " not in name or any(ch.isdigit() for ch in name):
        await message.answer(copy_fa.C6_ERROR_INVALID_NAME)
        return
    await state.update_data(full_name=name)
    await state.set_state(Checkout.phone)
    await message.answer(copy_fa.C7_ASK_PHONE, reply_markup=phone_request_keyboard())


@router.message(Checkout.phone, F.contact)
async def receive_contact(
    message: Message, conn: sqlite3.Connection, config: Config, state: FSMContext
) -> None:
    if message.contact is None or message.from_user is None:
        return
    await _handle_phone(
        message, conn, config, state, message.contact.phone_number, message.from_user.id
    )


@router.message(Checkout.phone)
async def receive_phone_text(
    message: Message, conn: sqlite3.Connection, config: Config, state: FSMContext
) -> None:
    if message.from_user is None:
        return
    await _handle_phone(message, conn, config, state, message.text or "", message.from_user.id)


async def _handle_phone(
    message: Message,
    conn: sqlite3.Connection,
    config: Config,
    state: FSMContext,
    raw_phone: str,
    telegram_id: int,
) -> None:
    phone = normalize_identifier(raw_phone)
    phone = re.sub(r"^(\+98|0098)", "0", phone)
    if not _PHONE_RE.match(phone):
        await message.answer(copy_fa.C7_ERROR_INVALID_PHONE)
        return
    await state.update_data(phone=phone)
    await message.answer(copy_fa.BTN_BACK, reply_markup=remove_reply_keyboard())
    if _cart_has_physical_item(conn, telegram_id):
        await state.set_state(Checkout.address)
        await message.answer(copy_fa.C8_ASK_ADDRESS)
    else:
        await _finalize(message, conn, config, state, telegram_id)


@router.message(Checkout.address)
async def receive_address(message: Message, state: FSMContext) -> None:
    address = normalize_text(message.text or "")
    if len(address) < 20:
        await message.answer(copy_fa.C8_ERROR_ADDRESS_TOO_SHORT)
        return
    await state.update_data(address=address)
    await state.set_state(Checkout.postal_code)
    await message.answer(copy_fa.C8_ASK_POSTAL_CODE)


@router.message(Checkout.postal_code)
async def receive_postal_code(
    message: Message, conn: sqlite3.Connection, config: Config, state: FSMContext
) -> None:
    if message.from_user is None:
        return
    postal_code = normalize_identifier(message.text or "")
    if not _POSTAL_RE.match(postal_code):
        await message.answer(copy_fa.C8_ERROR_INVALID_POSTAL_CODE)
        return
    await state.update_data(postal_code=postal_code)
    await _finalize(message, conn, config, state, message.from_user.id)


def _cart_has_physical_item(conn: sqlite3.Connection, telegram_id: int) -> bool:
    for line in cart_repo.list_items(conn, telegram_id):
        product = products_repo.get_product(conn, line.product_id)
        if product is not None and product.kind == ProductKind.PHYSICAL:
            return True
    return False


async def _finalize(
    message: Message, conn: sqlite3.Connection, config: Config, state: FSMContext, telegram_id: int
) -> None:
    data = await state.get_data()
    lines = cart_repo.list_items(conn, telegram_id)
    if not lines:
        await state.clear()
        await message.answer(copy_fa.C5_EMPTY_CART)
        return

    items: list[OrderItem] = []
    for line in lines:
        product = products_repo.get_product(conn, line.product_id)
        if product is None:
            continue
        variant = products_repo.get_variant(conn, line.variant_id) if line.variant_id else None
        items.append(
            OrderItem(
                product_id=product.id,
                variant_id=variant.id if variant is not None else None,
                kind=product.kind,
                name_snapshot=product.name,
                unit_price=item_price(product, variant),
                cost_price_snapshot=product.cost_price,
                quantity=line.quantity,
            )
        )

    customers.update_profile(
        conn,
        telegram_id,
        full_name=data.get("full_name"),
        phone=data.get("phone"),
        address=data.get("address"),
        postal_code=data.get("postal_code"),
    )

    try:
        order = orders.create(
            conn,
            customer_telegram_id=telegram_id,
            items=items,
            shipping_cost=config.store.shipping_cost
            if any(i.kind == ProductKind.PHYSICAL for i in items)
            else 0,
            payment_window_hours=config.order.payment_window_hours,
            created_at=int(time.time()),
            ship_name=data.get("full_name") if data.get("address") else None,
            ship_phone=data.get("phone") if data.get("address") else None,
            ship_address=data.get("address"),
        )
    except InsufficientStock:
        await state.clear()
        await message.answer(copy_fa.E5_STOCK_REDUCED.format(product_name="", new_quantity="0"))
        return

    await state.clear()
    cart_repo.clear(conn, telegram_id)

    text = build_invoice_text(
        order,
        card_number=config.store.card_number,
        card_holder=config.store.card_holder,
        window_hours=config.order.payment_window_hours,
    )
    sent = await message.answer(text, reply_markup=invoice_keyboard(order.code, order.state.value))
    orders.set_invoice_message_id(conn, order.code, sent.message_id)
    try:
        await sent.pin(disable_notification=True)
    except Exception:  # noqa: BLE001 - pinning is best-effort (needs admin rights in groups)
        pass


@router.callback_query(F.data.startswith("send_receipt:"))
async def prompt_receipt(callback: CallbackQuery, conn: sqlite3.Connection) -> None:
    _, order_code, _ = parse_cb(callback.data or "")
    await callback.answer()
    await callback.message.answer(  # type: ignore[union-attr]
        copy_fa.C10_ASK_RECEIPT, reply_markup=receipt_prompt_keyboard(order_code)
    )


@router.callback_query(F.data.startswith("view_invoice:"))
async def view_invoice(callback: CallbackQuery, conn: sqlite3.Connection, config: Config) -> None:
    _, order_code, _ = parse_cb(callback.data or "")
    order = orders.get(conn, order_code)
    await callback.answer()
    if order is None or callback.message is None:
        return
    text = build_invoice_text(
        order,
        card_number=config.store.card_number,
        card_holder=config.store.card_holder,
        window_hours=config.order.payment_window_hours,
    )
    await callback.message.answer(
        text, reply_markup=invoice_keyboard(order.code, order.state.value)
    )


@router.callback_query(F.data.startswith("cancel_order:"))
async def cancel_order(callback: CallbackQuery, conn: sqlite3.Connection) -> None:
    action, order_code, expected_state = parse_cb(callback.data or "")
    order = orders.get(conn, order_code)
    if order is None or order.state.value != expected_state:
        await callback.answer(copy_fa.E2_ALREADY_PROCESSED, show_alert=True)
        return
    try:
        orders.transition(
            conn,
            order_code,
            OrderState.CANCELLED,
            actor="customer",
            at=int(time.time()),
            expires_at=None,
        )
    except (OrderNotFound, IllegalTransition):
        await callback.answer(copy_fa.E2_ALREADY_PROCESSED, show_alert=True)
        return
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
