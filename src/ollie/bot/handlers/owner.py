"""
O1-O5: approve/reject, the panel root, and tracking entry. Every
handler in this module is wired behind `OwnerOnlyMiddleware` in
`main.py` — none of them re-checks who's calling, that's the
middleware's one job, done once instead of in every handler here.

Every mutating callback re-reads the order and compares its state to
the `expected_state` field the button's own `callback_data` carries
(`docs/m1-spec.html`'s own convention) before acting — a stale button
(the owner's lock screen still showing an already-approved order) is a
no-op answered with E2, never a double action.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Awaitable, Callable

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ollie.bot import copy_fa
from ollie.bot.fsm import OwnerAction
from ollie.bot.keyboards import (
    owner_approved_physical_keyboard,
    owner_panel_keyboard,
    owner_reject_reasons_keyboard,
    owner_stock_warning_keyboard,
    parse_cb,
)
from ollie.bot.rendering import build_sales_invoice_text, history_row
from ollie.bot.send import send_or_alert
from ollie.config import Config
from ollie.db.repo import credentials as credentials_repo
from ollie.db.repo import customers, orders
from ollie.db.repo import products as products_repo
from ollie.domain.errors import IllegalTransition
from ollie.domain.models import CredentialStatus, Order, ProductKind
from ollie.domain.states import OrderState

router = Router(name="owner")


def _reason_sentence(key: str) -> str:
    for reason_key, _, sentence in copy_fa.REJECT_REASONS:
        if reason_key == key and sentence is not None:
            return sentence
    return ""


def _make_delivery_send(
    bot: Bot, order: Order, config: Config, *, product_name: str, payload: str
) -> Callable[[], Awaitable[bool]]:
    """A fresh closure per credential, with every value it needs bound
    as a default argument rather than captured from an enclosing loop
    — a closure that captured `item`/`credential` directly would see
    whatever the loop variable holds by the time `send()` actually
    runs, not the value it held when this closure was created."""

    async def send() -> bool:
        return await send_or_alert(
            bot,
            order.customer_telegram_id,
            copy_fa.C12_DELIVERY.format(product_name=product_name, credential_payload=payload),
            owner_chat_id=config.bot.owner_telegram_id,
            order_code=order.code,
        )

    return send


@router.callback_query(F.data.startswith("approve:"))
async def approve(
    callback: CallbackQuery, conn: sqlite3.Connection, bot: Bot, config: Config
) -> None:
    _, order_code, expected_state = parse_cb(callback.data or "")
    order = orders.get(conn, order_code)
    if order is None or order.state.value != expected_state:
        await callback.answer(copy_fa.E2_ALREADY_PROCESSED, show_alert=True)
        return

    now = int(time.time())
    try:
        updated = orders.transition(
            conn, order_code, OrderState.APPROVED, actor="owner", at=now, approved_at=now
        )
    except IllegalTransition:
        await callback.answer(copy_fa.E2_ALREADY_PROCESSED, show_alert=True)
        return

    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]

    if updated.is_physical:
        await _handle_approved_physical(updated, conn, bot, config, now)
    else:
        await _handle_approved_digital(updated, conn, bot, config, now)


async def _handle_approved_physical(
    order: Order, conn: sqlite3.Connection, bot: Bot, config: Config, now: int
) -> None:
    await send_or_alert(
        bot,
        order.customer_telegram_id,
        copy_fa.C13_APPROVED_PHYSICAL.format(order_code=order.code),
        owner_chat_id=config.bot.owner_telegram_id,
        order_code=order.code,
    )
    customer = customers.get(conn, order.customer_telegram_id)
    invoice_text = build_sales_invoice_text(
        order, buyer_name=(customer.full_name if customer else None) or "-", reviewed_at=now
    )
    await send_or_alert(
        bot, order.customer_telegram_id, invoice_text, owner_chat_id=config.bot.owner_telegram_id
    )
    await bot.send_message(
        config.bot.owner_telegram_id,
        copy_fa.O3_APPROVED_PHYSICAL.format(order_code=order.code),
        reply_markup=owner_approved_physical_keyboard(order.code),
    )


async def _handle_approved_digital(
    order: Order, conn: sqlite3.Connection, bot: Bot, config: Config, now: int
) -> None:
    lines: list[str] = []
    any_shortage = False

    for item in order.items:
        if item.kind == ProductKind.PHYSICAL:
            continue
        candidates = credentials_repo.list_reserved_for_order(conn, order.code, item.product_id)
        delivered_count = 0
        for credential in candidates[: item.quantity]:
            send = _make_delivery_send(
                bot, order, config, product_name=item.name_snapshot, payload=credential.payload
            )
            result = await credentials_repo.deliver(
                conn, credential.id, delivered_at=now, send=send
            )
            if result.status == CredentialStatus.DELIVERED:
                delivered_count += 1

        remaining = credentials_repo.count_available(conn, item.product_id)
        lines.append(
            copy_fa.O3_APPROVED_DIGITAL_ITEM_LINE.format(
                product_name=item.name_snapshot,
                delivered_qty=delivered_count,
                remaining_stock=remaining,
            )
        )
        if delivered_count < item.quantity:
            any_shortage = True
            await bot.send_message(
                config.bot.owner_telegram_id,
                copy_fa.O3_STOCK_EXHAUSTED_WARNING.format(
                    order_code=order.code, product_name=item.name_snapshot
                ),
                reply_markup=owner_stock_warning_keyboard(order.code),
            )

    await bot.send_message(
        config.bot.owner_telegram_id,
        copy_fa.O3_APPROVED_DIGITAL.format(order_code=order.code, items_block="\n".join(lines)),
    )

    if any_shortage:
        # Per O3's own spec note: "the order is still approved ... the
        # owner gets the manual-send path" — never auto-fail an
        # approval because inventory drifted. Fulfillment (and the
        # sales invoice) waits until the owner resolves the shortage.
        return

    fulfilled = orders.transition(
        conn, order.code, OrderState.FULFILLED, actor="system", at=now, fulfilled_at=now
    )
    customer = customers.get(conn, fulfilled.customer_telegram_id)
    invoice_text = build_sales_invoice_text(
        fulfilled, buyer_name=(customer.full_name if customer else None) or "-", reviewed_at=now
    )
    await send_or_alert(
        bot,
        fulfilled.customer_telegram_id,
        invoice_text,
        owner_chat_id=config.bot.owner_telegram_id,
        order_code=order.code,
    )


@router.callback_query(F.data.startswith("reject:"))
async def reject_prompt(callback: CallbackQuery, conn: sqlite3.Connection) -> None:
    _, order_code, expected_state = parse_cb(callback.data or "")
    order = orders.get(conn, order_code)
    if order is None or order.state.value != expected_state:
        await callback.answer(copy_fa.E2_ALREADY_PROCESSED, show_alert=True)
        return
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            copy_fa.O2_REASON_PROMPT.format(order_code=order_code),
            reply_markup=owner_reject_reasons_keyboard(order_code, expected_state),
        )


@router.callback_query(F.data.regexp(r"^reason_cancel:"))
async def reason_cancel(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data.regexp(r"^reason_custom:"))
async def reason_custom(callback: CallbackQuery, state: FSMContext) -> None:
    _, order_code, expected_state = parse_cb(callback.data or "")
    await state.set_state(OwnerAction.reject_custom_reason)
    await state.update_data(order_code=order_code, expected_state=expected_state)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(copy_fa.O2_CUSTOM_REASON_PROMPT)


@router.message(OwnerAction.reject_custom_reason)
async def reject_custom_message(
    message: Message, conn: sqlite3.Connection, bot: Bot, config: Config, state: FSMContext
) -> None:
    data = await state.get_data()
    await state.clear()
    order_code = data.get("order_code")
    expected_state = data.get("expected_state")
    if not isinstance(order_code, str) or not isinstance(expected_state, str):
        return
    reason = f"{copy_fa.O2_CUSTOM_REASON_PREFIX} {(message.text or '').strip()[:200]}"
    await _finalize_reject(conn, bot, config, order_code, expected_state, reason)


@router.callback_query(
    F.data.regexp(r"^reason_(amount_mismatch|unreadable|duplicate|not_recorded):")
)
async def reason_fixed(
    callback: CallbackQuery, conn: sqlite3.Connection, bot: Bot, config: Config
) -> None:
    action, order_code, expected_state = parse_cb(callback.data or "")
    key = action.removeprefix("reason_")
    await callback.answer()
    await _finalize_reject(conn, bot, config, order_code, expected_state, _reason_sentence(key))


async def _finalize_reject(
    conn: sqlite3.Connection,
    bot: Bot,
    config: Config,
    order_code: str,
    expected_state: str,
    reason_sentence: str,
) -> None:
    order = orders.get(conn, order_code)
    if order is None or order.state.value != expected_state:
        return
    now = int(time.time())
    try:
        updated = orders.transition(
            conn,
            order_code,
            OrderState.REJECTED,
            actor="owner",
            at=now,
            reject_count=order.reject_count + 1,
        )
    except IllegalTransition:
        return

    text = copy_fa.C14_REJECTED.format(order_code=order_code, reason=reason_sentence)
    if updated.reject_count >= config.order.reject_flag_threshold:
        text = f"{text}\n\n{copy_fa.C14_REPEAT_REJECTION_SUFFIX}"
        await bot.send_message(
            config.bot.owner_telegram_id,
            copy_fa.O2_REPEAT_REJECTION_OWNER_ALERT.format(
                order_code=order_code, reject_count=updated.reject_count
            ),
        )
    await send_or_alert(
        bot,
        updated.customer_telegram_id,
        text,
        owner_chat_id=config.bot.owner_telegram_id,
        order_code=order_code,
    )


@router.message(F.text == "/panel")
async def panel_root(message: Message, conn: sqlite3.Connection) -> None:
    pending = orders.count_by_state(conn, OrderState.RECEIPT_SUBMITTED)
    preparing = orders.count_by_state(conn, OrderState.APPROVED)
    low_stock = sum(
        1
        for product in products_repo.list_active_products(conn)
        if product.kind != ProductKind.PHYSICAL
        and credentials_repo.count_available(conn, product.id) == 0
    )
    await message.answer(
        copy_fa.O4_PANEL_ROOT.format(
            pending_count=pending, preparing_count=preparing, low_stock_count=low_stock
        ),
        reply_markup=owner_panel_keyboard(pending),
    )


@router.callback_query(F.data.startswith("panel:"))
async def panel_section(callback: CallbackQuery, conn: sqlite3.Connection, config: Config) -> None:
    _, section, _ = parse_cb(callback.data or "")
    await callback.answer()
    if callback.message is None:
        return

    if section in ("pending", "all"):
        recent = orders.list_recent(conn)
        if section == "pending":
            recent = [o for o in recent if o.state == OrderState.RECEIPT_SUBMITTED]
        if not recent:
            await callback.message.answer(copy_fa.O4_ALL_ORDERS_EMPTY)
            return
        body = "\n".join(history_row(o) for o in recent)
        await callback.message.answer(f"{copy_fa.O4_ALL_ORDERS_HEADER}\n\n{body}")
    elif section == "credentials":
        products = [
            p for p in products_repo.list_active_products(conn) if p.kind != ProductKind.PHYSICAL
        ]
        if not products:
            await callback.message.answer(copy_fa.O4_CREDENTIAL_POOL_EMPTY)
            return
        lines = [
            copy_fa.O4_CREDENTIAL_POOL_LINE.format(
                product_name=p.name,
                available=credentials_repo.count_available(conn, p.id),
                reserved=credentials_repo.count_by_status(conn, p.id, CredentialStatus.RESERVED),
                delivered=credentials_repo.count_by_status(conn, p.id, CredentialStatus.DELIVERED),
            )
            for p in products
        ]
        await callback.message.answer("\n".join(lines))
    elif section == "support":
        await callback.message.answer(copy_fa.O4_SUPPORT_PLACEHOLDER)
    elif section == "backup":
        from aiogram.types import FSInputFile

        await callback.message.answer_document(FSInputFile(config.runtime.db_path))
        await callback.message.answer(copy_fa.O4_BACKUP_SENT)


@router.callback_query(F.data.startswith("enter_tracking:"))
async def enter_tracking(callback: CallbackQuery, state: FSMContext) -> None:
    _, order_code, _ = parse_cb(callback.data or "")
    await state.set_state(OwnerAction.tracking_number)
    await state.update_data(order_code=order_code)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(copy_fa.O5_TRACKING_PROMPT.format(order_code=order_code))


@router.message(OwnerAction.tracking_number)
async def receive_tracking(
    message: Message, conn: sqlite3.Connection, bot: Bot, config: Config, state: FSMContext
) -> None:
    from ollie.fmt.digits import normalize_identifier

    data = await state.get_data()
    order_code = data.get("order_code")
    if order_code is None:
        await state.clear()
        return

    tracking_number = normalize_identifier(message.text or "")
    if not (10 <= len(tracking_number) <= 24 and tracking_number.isdigit()):
        await message.answer(copy_fa.O5_ERROR_INVALID_TRACKING)
        return

    await state.clear()
    now = int(time.time())
    try:
        updated = orders.transition(
            conn,
            order_code,
            OrderState.FULFILLED,
            actor="owner",
            at=now,
            fulfilled_at=now,
            tracking_number=tracking_number,
            carrier=config.store.default_carrier,
        )
    except IllegalTransition:
        await message.answer(copy_fa.E2_ALREADY_PROCESSED)
        return

    await message.answer(copy_fa.O5_TRACKING_SAVED)
    await send_or_alert(
        bot,
        updated.customer_telegram_id,
        copy_fa.C13_SHIPPED.format(
            order_code=order_code,
            tracking_number=tracking_number,
            carrier=updated.carrier,
            tracking_url=config.store.default_carrier,
        ),
        owner_chat_id=config.bot.owner_telegram_id,
        order_code=order_code,
    )


@router.callback_query(F.data.startswith("msg_customer:"))
async def msg_customer_stub(
    callback: CallbackQuery, conn: sqlite3.Connection, state: FSMContext
) -> None:
    """Minimal M1 wiring: reuses the support reply flow's own FSM state
    (`Support.owner_reply`, keyed by `customer_telegram_id`) so the
    owner can free-type a message straight to this order's customer,
    without a second FSM doing the same thing a different way."""
    from ollie.bot.fsm import Support

    _, order_code, _ = parse_cb(callback.data or "")
    order = orders.get(conn, order_code)
    await callback.answer()
    if order is None or callback.message is None:
        return
    await state.set_state(Support.owner_reply)
    await state.update_data(customer_telegram_id=order.customer_telegram_id)
    await callback.message.answer(copy_fa.O6_CUSTOMER_PROMPT)


@router.callback_query(F.data.startswith("view_customer:"))
async def view_customer(callback: CallbackQuery, conn: sqlite3.Connection) -> None:
    _, order_code, _ = parse_cb(callback.data or "")
    order = orders.get(conn, order_code)
    await callback.answer()
    if order is None or callback.message is None:
        return
    customer = customers.get(conn, order.customer_telegram_id)
    if customer is None:
        return
    lines = [
        f"👤 {customer.full_name or '-'}",
        f"📞 {customer.phone or '-'}",
    ]
    if customer.address:
        lines.append(f"📍 {customer.address}")
    await callback.message.answer("\n".join(lines))
