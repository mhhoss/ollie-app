"""
One builder per screen, every label sourced from `copy_fa` — never a
literal here (`test_copy_isolation` enforces that mechanically).

`callback_data` is always `action:entity_id:expected_state`
(docs/m1-spec.html's own convention): a handler re-reads the entity's
*current* state before acting and compares it to the third field. A
stale button — the owner's phone showing an already-approved order's
notification, a customer double-tapping — is then a no-op answered
with E2, never a double action, without every handler re-deriving that
check by hand. `cb()`/`parse_cb()` are the one place that format is
assembled and parsed.
"""

from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ollie.bot import copy_fa
from ollie.domain.models import Product, Variant

_NO_STATE = "_"


def cb(action: str, entity_id: object = "_", expected_state: str = _NO_STATE) -> str:
    return f"{action}:{entity_id}:{expected_state}"


def parse_cb(data: str) -> tuple[str, str, str]:
    action, _, rest = data.partition(":")
    entity_id, _, expected_state = rest.partition(":")
    return action, entity_id, expected_state


# ── Root / persistent ────────────────────────────────────────────────
def root_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=copy_fa.BTN_PRODUCTS)],
            [KeyboardButton(text=copy_fa.BTN_MY_ORDERS), KeyboardButton(text=copy_fa.BTN_SUPPORT)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def phone_request_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=copy_fa.BTN_SEND_MY_CONTACT, request_contact=True)],
            [KeyboardButton(text=copy_fa.BTN_BACK)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def remove_reply_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


# ── Catalog: C2–C4 ────────────────────────────────────────────────────
def categories_keyboard(categories: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category_id, name in categories:
        builder.button(text=name, callback_data=cb("cat", category_id))
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text=copy_fa.BTN_BACK, callback_data=cb("nav", "root")))
    return builder.as_markup()


def product_list_keyboard(products: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    """`products` is (product_id, label) — the caller has already built
    each label with `copy_fa.BTN_PRODUCT_LABEL` or its out-of-stock
    variant, so an out-of-stock product still gets a tappable button
    (C3: tapping it opens C4, which explains why)."""
    builder = InlineKeyboardBuilder()
    for product_id, label in products:
        builder.row(InlineKeyboardButton(text=label, callback_data=cb("prod", product_id)))
    builder.row(InlineKeyboardButton(text=copy_fa.BTN_BACK, callback_data=cb("nav", "root")))
    return builder.as_markup()


def product_detail_keyboard(
    product: Product, variants: list[Variant], cart_count: int
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if variants:
        for variant in variants:
            available = variant.stock - variant.reserved
            if available > 0:
                builder.button(
                    text=variant.label, callback_data=cb("addcart", f"{product.id}.{variant.id}")
                )
        builder.adjust(2)
    elif product.is_active:
        builder.row(
            InlineKeyboardButton(
                text=copy_fa.BTN_ADD_TO_CART, callback_data=cb("addcart", f"{product.id}.0")
            )
        )
    if cart_count > 0:
        builder.row(
            InlineKeyboardButton(
                text=copy_fa.BTN_CART.format(count=cart_count), callback_data=cb("cart", "view")
            )
        )
    builder.row(InlineKeyboardButton(text=copy_fa.BTN_BACK, callback_data=cb("nav", "back")))
    return builder.as_markup()


# ── Cart: C5 ──────────────────────────────────────────────────────────
def cart_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=copy_fa.BTN_CHECKOUT, callback_data=cb("cart", "checkout"))
    )
    builder.row(
        InlineKeyboardButton(text=copy_fa.BTN_EDIT_CART, callback_data=cb("cart", "edit")),
        InlineKeyboardButton(text=copy_fa.BTN_CONTINUE_SHOPPING, callback_data=cb("nav", "root")),
    )
    return builder.as_markup()


def cart_empty_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=copy_fa.BTN_PRODUCTS, callback_data=cb("nav", "root")))
    return builder.as_markup()


def cart_edit_keyboard(lines: list[tuple[int, int | None, str]]) -> InlineKeyboardMarkup:
    """`lines` is (product_id, variant_id, label)."""
    builder = InlineKeyboardBuilder()
    for product_id, variant_id, label in lines:
        key = f"{product_id}.{variant_id or 0}"
        builder.row(
            InlineKeyboardButton(text=copy_fa.BTN_DECREMENT, callback_data=cb("dec", key)),
            InlineKeyboardButton(text=label, callback_data=cb("noop", key)),
            InlineKeyboardButton(text=copy_fa.BTN_INCREMENT, callback_data=cb("inc", key)),
            InlineKeyboardButton(text=copy_fa.BTN_REMOVE_ITEM, callback_data=cb("rm", key)),
        )
    builder.row(
        InlineKeyboardButton(text=copy_fa.BTN_DONE_EDITING, callback_data=cb("cart", "view"))
    )
    return builder.as_markup()


# ── Checkout: C6–C9 ───────────────────────────────────────────────────
def saved_profile_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=copy_fa.BTN_USE_SAVED_PROFILE, callback_data=cb("profile", "use")
        ),
        InlineKeyboardButton(
            text=copy_fa.BTN_CHANGE_PROFILE, callback_data=cb("profile", "change")
        ),
    )
    return builder.as_markup()


def back_to_cart_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=copy_fa.BTN_BACK_TO_CART)]], resize_keyboard=True
    )


def invoice_keyboard(order_code: str, state: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=copy_fa.BTN_SEND_RECEIPT, callback_data=cb("send_receipt", order_code, state)
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=copy_fa.BTN_CANCEL_ORDER, callback_data=cb("cancel_order", order_code, state)
        )
    )
    return builder.as_markup()


# ── Receipt / rejection: C10, C14 ────────────────────────────────────
def receipt_prompt_keyboard(order_code: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=copy_fa.BTN_BACK_TO_INVOICE, callback_data=cb("view_invoice", order_code)
        )
    )
    return builder.as_markup()


def rejected_keyboard(order_code: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=copy_fa.BTN_RESEND_RECEIPT, callback_data=cb("send_receipt", order_code)
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=copy_fa.BTN_VIEW_INVOICE, callback_data=cb("view_invoice", order_code)
        ),
        InlineKeyboardButton(text=copy_fa.BTN_SUPPORT, callback_data=cb("support", "start")),
    )
    return builder.as_markup()


# ── History: C15 ──────────────────────────────────────────────────────
def history_keyboard(orders: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    """`orders` is (order_code, row_label)."""
    builder = InlineKeyboardBuilder()
    for order_code, label in orders:
        builder.row(InlineKeyboardButton(text=label, callback_data=cb("order", order_code)))
    builder.row(InlineKeyboardButton(text=copy_fa.BTN_BACK, callback_data=cb("nav", "root")))
    return builder.as_markup()


# ── Owner: O1–O5 ──────────────────────────────────────────────────────
def owner_new_receipt_keyboard(order_code: str, expected_state: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=copy_fa.BTN_APPROVE, callback_data=cb("approve", order_code, expected_state)
        ),
        InlineKeyboardButton(
            text=copy_fa.BTN_REJECT, callback_data=cb("reject", order_code, expected_state)
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=copy_fa.BTN_MSG_CUSTOMER, callback_data=cb("msg_customer", order_code)
        ),
        InlineKeyboardButton(
            text=copy_fa.BTN_VIEW_CUSTOMER, callback_data=cb("view_customer", order_code)
        ),
    )
    return builder.as_markup()


def owner_reject_reasons_keyboard(order_code: str, expected_state: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, label, _ in copy_fa.REJECT_REASONS:
        if key == "custom":
            continue
        builder.row(
            InlineKeyboardButton(
                text=label, callback_data=cb(f"reason_{key}", order_code, expected_state)
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=copy_fa.BTN_CUSTOM_REASON,
            callback_data=cb("reason_custom", order_code, expected_state),
        ),
        InlineKeyboardButton(
            text=copy_fa.BTN_CANCEL, callback_data=cb("reason_cancel", order_code, expected_state)
        ),
    )
    return builder.as_markup()


def owner_stock_warning_keyboard(order_code: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=copy_fa.BTN_ADD_STOCK, callback_data=cb("add_stock", order_code)),
        InlineKeyboardButton(
            text=copy_fa.BTN_MANUAL_SEND, callback_data=cb("manual_send", order_code)
        ),
    )
    return builder.as_markup()


def owner_approved_physical_keyboard(order_code: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=copy_fa.BTN_ENTER_TRACKING, callback_data=cb("enter_tracking", order_code)
        )
    )
    return builder.as_markup()


def owner_panel_keyboard(pending_count: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=copy_fa.BTN_PENDING_ORDERS.format(count=pending_count),
            callback_data=cb("panel", "pending"),
        )
    )
    builder.row(
        InlineKeyboardButton(text=copy_fa.BTN_ALL_ORDERS, callback_data=cb("panel", "all")),
        InlineKeyboardButton(
            text=copy_fa.BTN_CREDENTIAL_POOL, callback_data=cb("panel", "credentials")
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=copy_fa.BTN_SUPPORT_MESSAGES, callback_data=cb("panel", "support")
        ),
        InlineKeyboardButton(text=copy_fa.BTN_BACKUP, callback_data=cb("panel", "backup")),
    )
    return builder.as_markup()


def support_reply_keyboard(customer_telegram_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=copy_fa.BTN_REPLY, callback_data=cb("support_reply", customer_telegram_id)
        )
    )
    return builder.as_markup()
