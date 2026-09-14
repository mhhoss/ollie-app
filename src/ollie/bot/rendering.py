"""
Shared text-assembly helpers used by more than one handler module —
kept here instead of duplicated so the cart total, the invoice, and
order history all compute a line price exactly one way.

Every function here composes `copy_fa` templates with `ollie.fmt`-
rendered values; none of it does its own number/date formatting or
holds any Persian literal of its own — consistent with copy_fa.py's
own rule 4 (Callers, not templates, render numbers and dates).
"""

from __future__ import annotations

import sqlite3

from ollie.bot import copy_fa
from ollie.db.repo import products as products_repo
from ollie.domain.models import Order, OrderItem, Product, Variant
from ollie.domain.states import OrderState
from ollie.fmt.jalali import format_jalali, gregorian_to_jalali
from ollie.fmt.money import toman


def item_price(product: Product, variant: Variant | None) -> int:
    return product.price + (variant.price_delta if variant is not None else 0)


def format_date(unix_ts: int) -> str:
    import datetime

    dt = datetime.datetime.fromtimestamp(unix_ts, tz=datetime.UTC)
    jy, jm, jd = gregorian_to_jalali(dt.year, dt.month, dt.day)
    return format_jalali(jy, jm, jd)


def _order_item_lines(items: tuple[OrderItem, ...], template: str) -> str:
    lines = [
        template.format(
            product_name=item.name_snapshot,
            quantity=item.quantity,
            line_total=toman(item.line_total),
        )
        for item in items
    ]
    return "\n".join(lines)


def build_invoice_text(
    order: Order, *, card_number: str, card_holder: str, window_hours: int
) -> str:
    return copy_fa.C9_INVOICE.format(
        order_code=order.code,
        date=format_date(order.created_at),
        items_block=_order_item_lines(order.items, copy_fa.C9_ITEM_LINE),
        shipping_cost=toman(order.shipping_cost),
        payable_amount=toman(order.payable_amount),
        card_number=card_number,
        card_holder=card_holder,
        payment_window_hours=window_hours,
    )


def build_sales_invoice_text(order: Order, *, buyer_name: str, reviewed_at: int) -> str:
    return copy_fa.C12_INVOICE.format(
        order_code=order.code,
        datetime=format_date(reviewed_at),
        buyer_name=buyer_name,
        items_block=_order_item_lines(order.items, copy_fa.C9_ITEM_LINE),
        paid_amount=toman(order.payable_amount),
    )


def build_owner_receipt_items_block(items: tuple[OrderItem, ...]) -> str:
    return _order_item_lines(items, copy_fa.O1_ITEM_LINE)


def history_row(order: Order) -> str:
    return copy_fa.C15_HISTORY_ROW.format(
        order_code=order.code,
        date=format_date(order.created_at),
        status_label=copy_fa.STATUS_LABELS[order.state],
    )


def cart_text(conn: sqlite3.Connection, telegram_id: int) -> tuple[str, int]:
    """Returns (rendered cart body, total). Caller decides whether the
    cart is empty and which keyboard to attach."""
    from ollie.db.repo import cart as cart_repo

    lines = cart_repo.list_items(conn, telegram_id)
    body_lines = [copy_fa.C5_CART_HEADER, ""]
    total = 0
    for index, line in enumerate(lines, start=1):
        product = products_repo.get_product(conn, line.product_id)
        variant = products_repo.get_variant(conn, line.variant_id) if line.variant_id else None
        if product is None:
            continue
        price = item_price(product, variant)
        line_total = price * line.quantity
        total += line_total
        body_lines.append(
            copy_fa.C5_CART_LINE.format(
                index=index,
                product_name=product.name,
                quantity=line.quantity,
                line_total=toman(line_total),
            )
        )
    body_lines.append("")
    body_lines.append(copy_fa.C5_CART_TOTAL.format(total=toman(total)))
    return "\n".join(body_lines), total


def is_order_open_for_receipt(order: Order) -> bool:
    return order.state in (OrderState.AWAITING_RECEIPT, OrderState.REJECTED)
