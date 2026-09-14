"""C5: view, edit, and hand off to checkout."""

from __future__ import annotations

import sqlite3

from aiogram import F, Router
from aiogram.types import CallbackQuery

from ollie.bot import copy_fa
from ollie.bot.keyboards import cart_edit_keyboard, cart_empty_keyboard, cart_keyboard, parse_cb
from ollie.bot.rendering import cart_text
from ollie.db.repo import cart as cart_repo
from ollie.db.repo import products as products_repo

router = Router(name="cart")


@router.callback_query(F.data == "cart:view:_")
async def view_cart(callback: CallbackQuery, conn: sqlite3.Connection) -> None:
    if callback.message is None or callback.from_user is None:
        return
    await callback.answer()
    await _render_cart(callback, conn)


async def _render_cart(callback: CallbackQuery, conn: sqlite3.Connection) -> None:
    telegram_id = callback.from_user.id
    lines = cart_repo.list_items(conn, telegram_id)
    if not lines:
        await callback.message.edit_text(copy_fa.C5_EMPTY_CART, reply_markup=cart_empty_keyboard())  # type: ignore[union-attr]
        return
    text, _ = cart_text(conn, telegram_id)
    await callback.message.edit_text(text, reply_markup=cart_keyboard())  # type: ignore[union-attr]


@router.callback_query(F.data == "cart:edit:_")
async def edit_cart(callback: CallbackQuery, conn: sqlite3.Connection) -> None:
    if callback.message is None or callback.from_user is None:
        return
    await callback.answer()
    await _render_edit(callback, conn)


async def _render_edit(callback: CallbackQuery, conn: sqlite3.Connection) -> None:
    telegram_id = callback.from_user.id
    lines = cart_repo.list_items(conn, telegram_id)
    rows = []
    for line in lines:
        product = products_repo.get_product(conn, line.product_id)
        if product is None:
            continue
        rows.append((line.product_id, line.variant_id, f"{product.name} × {line.quantity}"))
    text, _ = cart_text(conn, telegram_id)
    await callback.message.edit_text(text, reply_markup=cart_edit_keyboard(rows))  # type: ignore[union-attr]


@router.callback_query(F.data.startswith("inc:"))
async def increment(callback: CallbackQuery, conn: sqlite3.Connection) -> None:
    await _adjust(callback, conn, delta=1)


@router.callback_query(F.data.startswith("dec:"))
async def decrement(callback: CallbackQuery, conn: sqlite3.Connection) -> None:
    await _adjust(callback, conn, delta=-1)


async def _adjust(callback: CallbackQuery, conn: sqlite3.Connection, *, delta: int) -> None:
    if callback.from_user is None:
        return
    _, key, _ = parse_cb(callback.data or "")
    product_id_str, _, variant_id_str = key.partition(".")
    product_id = int(product_id_str)
    variant_id = int(variant_id_str) if variant_id_str != "0" else None

    current = next(
        (
            line
            for line in cart_repo.list_items(conn, callback.from_user.id)
            if line.product_id == product_id and line.variant_id == variant_id
        ),
        None,
    )
    new_quantity = (current.quantity if current else 0) + delta
    cart_repo.set_quantity(
        conn,
        callback.from_user.id,
        product_id=product_id,
        variant_id=variant_id,
        quantity=new_quantity,
    )
    await callback.answer()
    await _render_edit(callback, conn)


@router.callback_query(F.data.startswith("rm:"))
async def remove(callback: CallbackQuery, conn: sqlite3.Connection) -> None:
    if callback.from_user is None:
        return
    _, key, _ = parse_cb(callback.data or "")
    product_id_str, _, variant_id_str = key.partition(".")
    variant_id = int(variant_id_str) if variant_id_str != "0" else None
    cart_repo.remove_item(
        conn, callback.from_user.id, product_id=int(product_id_str), variant_id=variant_id
    )
    await callback.answer()
    await _render_edit(callback, conn)


@router.callback_query(F.data.startswith("noop:"))
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()
