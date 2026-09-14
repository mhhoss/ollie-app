"""
C2-C4: category list, product list, product detail.

One known gap, inherited from the spec rather than introduced here:
`docs/m1-spec.html`'s own schema has no `category` table — only
`product.category_id INTEGER NULL` with no name attached to a category
id anywhere. Product management is explicitly out of M1's scope (the
spec's own "Deliberately out" list), so there is currently no source
for a human-readable category name at all. Where more than one
category_id is in use, this module labels each one with
copy_fa.C2_CATEGORY_LABEL (a numbered placeholder) defensively rather
than crashing or inventing a fake name table — a real fix needs an M2
product-management conversation, not a Phase 7 workaround.
"""

from __future__ import annotations

import sqlite3

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from ollie.bot import copy_fa
from ollie.bot.keyboards import (
    categories_keyboard,
    parse_cb,
    product_detail_keyboard,
    product_list_keyboard,
)
from ollie.db.repo import cart as cart_repo
from ollie.db.repo import products as products_repo
from ollie.fmt.money import toman

router = Router(name="catalog")


@router.message(F.text == copy_fa.BTN_PRODUCTS)
async def show_root(message: Message, conn: sqlite3.Connection) -> None:
    await _show_categories_or_products(message, conn)


@router.callback_query(F.data == "nav:root:_")
async def nav_root(callback: CallbackQuery, conn: sqlite3.Connection) -> None:
    if callback.message is None:
        return
    await callback.answer()
    await _show_categories_or_products(callback.message, conn)  # type: ignore[arg-type]


async def _show_categories_or_products(message: Message, conn: sqlite3.Connection) -> None:
    products = products_repo.list_active_products(conn)
    category_ids = {p.category_id for p in products if p.category_id is not None}
    if len(category_ids) <= 1:
        await _render_product_list(message, conn, category_id=None)
        return
    categories = [
        (cid, copy_fa.C2_CATEGORY_LABEL.format(category_id=cid)) for cid in sorted(category_ids)
    ]
    await message.answer(copy_fa.C2_CHOOSE_CATEGORY, reply_markup=categories_keyboard(categories))


@router.callback_query(F.data.startswith("cat:"))
async def choose_category(callback: CallbackQuery, conn: sqlite3.Connection) -> None:
    if callback.message is None:
        return
    _, category_id, _ = parse_cb(callback.data or "")
    await callback.answer()
    await _render_product_list(callback.message, conn, category_id=int(category_id))  # type: ignore[arg-type]


async def _render_product_list(
    message: Message, conn: sqlite3.Connection, *, category_id: int | None
) -> None:
    products = products_repo.list_active_products(conn, category_id=category_id)
    if not products:
        await message.answer(copy_fa.C2_EMPTY_CATALOG)
        return
    rows = []
    for product in products:
        variants = products_repo.list_variants(conn, product.id)
        in_stock = (
            any(v.stock - v.reserved > 0 for v in variants) if variants else product.is_active
        )
        label_template = (
            copy_fa.BTN_PRODUCT_LABEL if in_stock else copy_fa.BTN_PRODUCT_LABEL_OUT_OF_STOCK
        )
        label = label_template.format(product_name=product.name, price=toman(product.price))
        rows.append((product.id, label))
    await message.answer(
        copy_fa.C3_PRODUCT_LIST_HEADER.format(category_name=copy_fa.C3_ALL_PRODUCTS_LABEL),
        reply_markup=product_list_keyboard(rows),
    )


@router.callback_query(F.data.startswith("prod:"))
async def product_detail_callback(callback: CallbackQuery, conn: sqlite3.Connection) -> None:
    if callback.message is None:
        return
    _, product_id, _ = parse_cb(callback.data or "")
    await callback.answer()
    await send_product_detail(callback.message, conn, int(product_id))  # type: ignore[arg-type]


async def send_product_detail(message: Message, conn: sqlite3.Connection, product_id: int) -> None:
    product = products_repo.get_product(conn, product_id)
    if product is None or not product.is_active:
        await message.answer(copy_fa.C2_EMPTY_CATALOG)
        return

    variants = products_repo.list_variants(conn, product_id)
    available = any(v.stock - v.reserved > 0 for v in variants) if variants else product.is_active
    telegram_id = message.chat.id
    cart_lines = cart_repo.list_items(conn, telegram_id)
    cart_count = sum(line.quantity for line in cart_lines)

    text = copy_fa.C4_PRODUCT_DETAIL.format(
        product_name=product.name,
        description=product.description,
        price=toman(product.price),
        availability_line=copy_fa.C4_AVAILABLE if available else copy_fa.C4_OUT_OF_STOCK,
    )
    keyboard = product_detail_keyboard(product, variants, cart_count)
    if product.photo_file_id:
        await message.answer_photo(product.photo_file_id, caption=text, reply_markup=keyboard)
    else:
        await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("addcart:"))
async def add_to_cart(callback: CallbackQuery, conn: sqlite3.Connection) -> None:
    if callback.message is None or callback.from_user is None:
        return
    _, key, _ = parse_cb(callback.data or "")
    product_id_str, _, variant_id_str = key.partition(".")
    product_id = int(product_id_str)
    variant_id = int(variant_id_str) if variant_id_str != "0" else None

    cart_repo.add_item(
        conn, callback.from_user.id, product_id=product_id, variant_id=variant_id, quantity=1
    )
    await callback.answer()
    await send_product_detail(callback.message, conn, product_id)  # type: ignore[arg-type]
