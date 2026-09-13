"""
Protects the record-level contract (what makes a single object valid on
its own) and, for Order specifically, the replace-and-revalidate
mechanism that with_state() relies on: every transition reconstructs
the object through dataclasses.replace(), which reruns __post_init__,
so an incomplete transition must fail loudly rather than produce a
silently inconsistent Order.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from ollie.domain.models import (
    Credential,
    CredentialStatus,
    Customer,
    Order,
    OrderItem,
    Product,
    ProductKind,
    Receipt,
    ReceiptVerdict,
    Variant,
)
from ollie.domain.states import OrderState

NOW = 1_757_000_000
DAY = 24 * 60 * 60


# ---------------------------------------------------------------------------
# Factories — valid-by-default, override only what a test cares about.
# ---------------------------------------------------------------------------
def make_product(**overrides: Any) -> Product:
    fields = dict(
        id=1,
        kind=ProductKind.DIGITAL,
        name="اشتراک سه‌ماهه",
        description="دسترسی کامل به سرویس برای ۹۰ روز",
        price=600_000,
        cost_price=200_000,
        is_active=True,
    )
    fields.update(overrides)
    return Product(**fields)  # type: ignore[arg-type]


def make_variant(**overrides: Any) -> Variant:
    fields = dict(id=1, product_id=1, label="۳ ماهه", price_delta=0, stock=10, reserved=0)
    fields.update(overrides)
    return Variant(**fields)  # type: ignore[arg-type]


def make_credential(**overrides: Any) -> Credential:
    fields = dict(
        id=1,
        product_id=1,
        payload="user:demo\npass:secret",
        status=CredentialStatus.AVAILABLE,
        order_code=None,
        delivered_at=None,
    )
    fields.update(overrides)
    return Credential(**fields)  # type: ignore[arg-type]


def make_customer(**overrides: Any) -> Customer:
    fields = dict(telegram_id=111222333, full_name="علی محمدی", phone="09121234567")
    fields.update(overrides)
    return Customer(**fields)  # type: ignore[arg-type]


def make_item(**overrides: Any) -> OrderItem:
    fields = dict(
        product_id=1,
        variant_id=1,
        kind=ProductKind.DIGITAL,
        name_snapshot="اشتراک سه‌ماهه",
        unit_price=600_000,
        cost_price_snapshot=200_000,
        quantity=1,
    )
    fields.update(overrides)
    return OrderItem(**fields)  # type: ignore[arg-type]


def make_digital_order(**overrides: Any) -> Order:
    items = overrides.pop("items", (make_item(),))
    fields = dict(
        code="ABCDEF",
        customer_telegram_id=111222333,
        state=OrderState.AWAITING_RECEIPT,
        items=tuple(items),
        subtotal=600_000,
        shipping_cost=0,
        amount_tail=347,
        payable_amount=600_347,
        is_physical=False,
        ship_name=None,
        ship_phone=None,
        ship_address=None,
        tracking_number=None,
        carrier=None,
        reject_count=0,
        invoice_message_id=None,
        expires_at=NOW + DAY,
        created_at=NOW,
        approved_at=None,
        fulfilled_at=None,
    )
    fields.update(overrides)
    return Order(**fields)  # type: ignore[arg-type]


def make_physical_order(**overrides: Any) -> Order:
    fields = dict(
        items=(make_item(kind=ProductKind.PHYSICAL, cost_price_snapshot=50_000),),
        shipping_cost=30_000,
        payable_amount=630_347,
        is_physical=True,
        ship_name="علی محمدی",
        ship_phone="09121234567",
        ship_address="تهران، خیابان آزادی، پلاک ۱۲",
    )
    fields.update(overrides)
    return make_digital_order(**fields)


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------
def test_product_valid() -> None:
    make_product()  # must not raise


def test_product_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="name cannot be empty"):
        make_product(name="  ")


def test_product_rejects_negative_price() -> None:
    with pytest.raises(ValueError, match="price cannot be negative"):
        make_product(price=-1)


def test_product_rejects_oversized_description() -> None:
    with pytest.raises(ValueError, match="300 chars"):
        make_product(description="x" * 301)


def test_product_allows_description_at_the_limit() -> None:
    make_product(description="x" * 300)  # must not raise


# ---------------------------------------------------------------------------
# Variant
# ---------------------------------------------------------------------------
def test_variant_valid() -> None:
    make_variant()  # must not raise


def test_variant_rejects_reserved_exceeding_stock() -> None:
    with pytest.raises(ValueError, match="cannot exceed stock"):
        make_variant(stock=5, reserved=6)


def test_variant_allows_negative_price_delta() -> None:
    make_variant(price_delta=-50_000)  # a discount variant — must not raise


# ---------------------------------------------------------------------------
# Credential
# ---------------------------------------------------------------------------
def test_credential_available_has_no_order() -> None:
    make_credential()  # must not raise


def test_credential_available_rejects_order_code() -> None:
    with pytest.raises(ValueError, match="available"):
        make_credential(order_code="ABCDEF")


def test_credential_reserved_requires_order_code() -> None:
    with pytest.raises(ValueError, match="no order_code"):
        make_credential(status=CredentialStatus.RESERVED, order_code=None)


def test_credential_reserved_valid() -> None:
    make_credential(status=CredentialStatus.RESERVED, order_code="ABCDEF")


def test_credential_delivered_requires_delivered_at() -> None:
    with pytest.raises(ValueError, match="delivered_at is not set"):
        make_credential(status=CredentialStatus.DELIVERED, order_code="ABCDEF", delivered_at=None)


def test_credential_delivered_valid() -> None:
    make_credential(status=CredentialStatus.DELIVERED, order_code="ABCDEF", delivered_at=NOW)


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------
def test_customer_valid() -> None:
    make_customer()  # must not raise


def test_customer_rejects_malformed_phone() -> None:
    with pytest.raises(ValueError, match="phone"):
        make_customer(phone="123456")


def test_customer_rejects_malformed_postal_code() -> None:
    with pytest.raises(ValueError, match="postal_code"):
        make_customer(postal_code="12345")


def test_customer_allows_missing_optional_fields() -> None:
    Customer(telegram_id=1)  # must not raise


# ---------------------------------------------------------------------------
# OrderItem
# ---------------------------------------------------------------------------
def test_order_item_valid() -> None:
    make_item()  # must not raise


def test_order_item_rejects_negative_unit_price() -> None:
    with pytest.raises(ValueError, match="unit_price cannot be negative"):
        make_item(unit_price=-1)


def test_order_item_rejects_zero_quantity() -> None:
    with pytest.raises(ValueError, match="quantity must be at least 1"):
        make_item(quantity=0)


def test_order_item_line_total() -> None:
    item = make_item(unit_price=100, quantity=3)
    assert item.line_total == 300


# ---------------------------------------------------------------------------
# Order — construction and cross-checks
# ---------------------------------------------------------------------------
def test_digital_order_valid() -> None:
    make_digital_order()  # must not raise


def test_physical_order_valid() -> None:
    make_physical_order()  # must not raise


def test_order_rejects_subtotal_mismatch() -> None:
    with pytest.raises(ValueError, match="subtotal"):
        make_digital_order(subtotal=999)


def test_order_rejects_is_physical_mismatch() -> None:
    with pytest.raises(ValueError, match="is_physical"):
        make_digital_order(is_physical=True)


def test_order_rejects_payable_amount_mismatch() -> None:
    with pytest.raises(ValueError, match="payable_amount"):
        make_digital_order(payable_amount=1)


def test_order_rejects_shipping_cost_on_digital_order() -> None:
    with pytest.raises(ValueError, match="digital order cannot carry"):
        make_digital_order(shipping_cost=1000, payable_amount=601_347)


def test_order_rejects_missing_shipping_snapshot_on_physical_order() -> None:
    with pytest.raises(ValueError, match="missing ship_name"):
        make_physical_order(ship_name=None)


def test_order_rejects_shipping_snapshot_on_digital_order() -> None:
    with pytest.raises(ValueError, match="digital-only but carries a shipping snapshot"):
        make_digital_order(ship_name="علی محمدی")


def test_order_rejects_empty_items() -> None:
    with pytest.raises(ValueError, match="no items"):
        make_digital_order(items=(), subtotal=0, payable_amount=347)


def test_order_rejects_invalid_code() -> None:
    with pytest.raises(ValueError, match="not a valid order code"):
        make_digital_order(code="short")


def test_order_rejects_tracking_without_carrier() -> None:
    with pytest.raises(ValueError, match="tracking_number and carrier must be set together"):
        make_physical_order(
            state=OrderState.FULFILLED,
            expires_at=None,
            approved_at=NOW,
            fulfilled_at=NOW,
            tracking_number="12345678901234567890",
            carrier=None,
        )


def test_order_rejects_tracking_on_a_digital_order() -> None:
    with pytest.raises(ValueError, match="tracking_number presence"):
        make_digital_order(
            state=OrderState.FULFILLED,
            expires_at=None,
            approved_at=NOW,
            fulfilled_at=NOW,
            tracking_number="12345678901234567890",
            carrier="پست پیشتاز",
        )


def test_order_rejects_expires_at_outside_awaiting_receipt() -> None:
    with pytest.raises(ValueError, match="expires_at"):
        make_digital_order(state=OrderState.RECEIPT_SUBMITTED, expires_at=NOW + DAY)


def test_order_rejects_missing_expires_at_in_awaiting_receipt() -> None:
    with pytest.raises(ValueError, match="expires_at"):
        make_digital_order(expires_at=None)


def test_order_rejects_approved_at_without_matching_state() -> None:
    with pytest.raises(ValueError, match="approved_at"):
        make_digital_order(approved_at=NOW)


def test_order_rejects_fulfilled_at_without_matching_state() -> None:
    with pytest.raises(ValueError, match="fulfilled_at"):
        make_digital_order(state=OrderState.RECEIPT_SUBMITTED, expires_at=None, fulfilled_at=NOW)


# ---------------------------------------------------------------------------
# Order.create() — the checkout factory
# ---------------------------------------------------------------------------
def test_create_derives_subtotal_is_physical_and_payable() -> None:
    order = Order.create(
        code="ABCDEF",
        customer_telegram_id=111222333,
        items=[make_item(unit_price=600_000, quantity=2)],
        shipping_cost=0,
        amount_tail=347,
        expires_at=NOW + DAY,
        created_at=NOW,
    )
    assert order.state == OrderState.AWAITING_RECEIPT
    assert order.subtotal == 1_200_000
    assert order.is_physical is False
    assert order.payable_amount == 1_200_347


def test_create_physical_requires_valid_shipping_snapshot() -> None:
    with pytest.raises(ValueError, match="missing ship_name"):
        Order.create(
            code="ABCDEF",
            customer_telegram_id=111222333,
            items=[make_item(kind=ProductKind.PHYSICAL)],
            shipping_cost=30_000,
            amount_tail=347,
            expires_at=NOW + DAY,
            created_at=NOW,
        )


# ---------------------------------------------------------------------------
# Order.with_state() — the replace-and-revalidate mechanism
# ---------------------------------------------------------------------------
def test_with_state_receipt_submitted_clears_expiry() -> None:
    order = make_digital_order()
    submitted = order.with_state(OrderState.RECEIPT_SUBMITTED, expires_at=None)
    assert submitted.state == OrderState.RECEIPT_SUBMITTED
    assert submitted.expires_at is None
    # with_state returns a new object; the original is untouched (frozen).
    assert order.state == OrderState.AWAITING_RECEIPT


def test_with_state_forgetting_to_clear_expiry_is_rejected() -> None:
    """
    The mechanism this test exists to prove: with_state() does not
    know that entering receipt_submitted should clear expires_at — it
    only checks FSM legality and replaces fields. It is __post_init__,
    re-run by dataclasses.replace(), that catches a caller who forgot
    the override, by finding the *old* expires_at value now paired
    with a state that forbids it.
    """
    order = make_digital_order()
    with pytest.raises(ValueError, match="expires_at"):
        order.with_state(OrderState.RECEIPT_SUBMITTED)  # no expires_at override


def test_with_state_rejected_to_awaiting_receipt_requires_fresh_expiry() -> None:
    rejected = make_digital_order(state=OrderState.RECEIPT_SUBMITTED, expires_at=None).with_state(
        OrderState.REJECTED, reject_count=1
    )
    assert rejected.state == OrderState.REJECTED
    assert rejected.expires_at is None

    retried = rejected.with_state(OrderState.AWAITING_RECEIPT, expires_at=NOW + 2 * DAY)
    assert retried.state == OrderState.AWAITING_RECEIPT
    assert retried.expires_at == NOW + 2 * DAY
    assert retried.reject_count == 1  # carried forward, not reset


def test_with_state_retry_forgetting_fresh_expiry_is_rejected() -> None:
    rejected = make_digital_order(state=OrderState.RECEIPT_SUBMITTED, expires_at=None).with_state(
        OrderState.REJECTED
    )
    with pytest.raises(ValueError, match="expires_at"):
        rejected.with_state(OrderState.AWAITING_RECEIPT)  # no fresh expires_at supplied


def test_with_state_approve_then_fulfill_digital() -> None:
    order = make_digital_order(state=OrderState.RECEIPT_SUBMITTED, expires_at=None)
    approved = order.with_state(OrderState.APPROVED, approved_at=NOW)
    assert approved.approved_at == NOW
    assert approved.fulfilled_at is None

    fulfilled = approved.with_state(OrderState.FULFILLED, fulfilled_at=NOW + 60)
    assert fulfilled.fulfilled_at == NOW + 60
    assert fulfilled.tracking_number is None  # digital: never gets one


def test_with_state_approve_then_fulfill_physical_requires_tracking() -> None:
    order = make_physical_order(state=OrderState.RECEIPT_SUBMITTED, expires_at=None)
    approved = order.with_state(OrderState.APPROVED, approved_at=NOW)

    with pytest.raises(ValueError, match="tracking_number presence"):
        approved.with_state(OrderState.FULFILLED, fulfilled_at=NOW + 60)  # forgot tracking

    fulfilled = approved.with_state(
        OrderState.FULFILLED,
        fulfilled_at=NOW + 60,
        tracking_number="12345678901234567890",
        carrier="پست پیشتاز",
    )
    assert fulfilled.tracking_number == "12345678901234567890"


def test_with_state_cancel_requires_clearing_expiry() -> None:
    order = make_digital_order()
    with pytest.raises(ValueError, match="expires_at"):
        order.with_state(OrderState.CANCELLED)  # forgot to clear expires_at

    cancelled = order.with_state(OrderState.CANCELLED, expires_at=None)
    assert cancelled.state == OrderState.CANCELLED


def test_with_state_rejected_can_expire_with_no_field_overrides() -> None:
    """
    The fix, exercised at the model level rather than just the bare
    FSM-legality level test_states.py covers: a REJECTED order already
    has expires_at, approved_at, fulfilled_at, tracking_number and
    carrier all cleared (nothing was ever approved), so expiring it out
    from under an abandoned retry requires no field overrides at all —
    a pure state flip. If this ever started requiring an override, that
    would mean REJECTED had stopped being the "quiescent" state the
    invariants assume, which is worth knowing immediately.
    """
    rejected = make_digital_order(state=OrderState.RECEIPT_SUBMITTED, expires_at=None).with_state(
        OrderState.REJECTED, reject_count=1
    )
    expired = rejected.with_state(OrderState.EXPIRED)  # no overrides needed
    assert expired.state == OrderState.EXPIRED
    assert expired.reject_count == 1  # history carried forward, not lost


def test_with_state_illegal_transition_raises_before_replace() -> None:
    from ollie.domain.errors import IllegalTransition

    order = make_digital_order()
    with pytest.raises(IllegalTransition):
        order.with_state(OrderState.FULFILLED)


def test_dataclasses_replace_works_on_frozen_slotted_order() -> None:
    """
    Narrow sanity check for the mechanism with_state() is built on:
    dataclasses.replace() must actually reconstruct the object through
    __init__ (rerunning __post_init__) on a frozen, slots=True
    dataclass with a tuple-typed field, on this Python version.
    """
    order = make_digital_order()
    replaced = dataclasses.replace(order, reject_count=5)
    assert replaced.reject_count == 5
    assert replaced is not order
    assert order.reject_count == 0  # original untouched


# ---------------------------------------------------------------------------
# Receipt
# ---------------------------------------------------------------------------
def test_receipt_pending_valid() -> None:
    Receipt(
        order_code="ABCDEF",
        file_id="file123",
        file_unique_id="unique123",
        image_hash="deadbeef",
        is_active=True,
        submitted_at=NOW,
    )


def test_receipt_rejected_requires_reason() -> None:
    with pytest.raises(ValueError, match="reject_reason"):
        Receipt(
            order_code="ABCDEF",
            file_id="file123",
            file_unique_id="unique123",
            image_hash="deadbeef",
            is_active=False,
            submitted_at=NOW,
            verdict=ReceiptVerdict.REJECTED,
            reviewed_at=NOW + 60,
            reject_reason=None,
        )


def test_receipt_approved_forbids_reject_reason() -> None:
    with pytest.raises(ValueError, match="carries a reject_reason"):
        Receipt(
            order_code="ABCDEF",
            file_id="file123",
            file_unique_id="unique123",
            image_hash="deadbeef",
            is_active=True,
            submitted_at=NOW,
            verdict=ReceiptVerdict.APPROVED,
            reviewed_at=NOW + 60,
            reject_reason="مبلغ مطابقت ندارد",
        )
