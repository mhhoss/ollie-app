from __future__ import annotations

from typing import Any

from ollie.domain.models import Credential, CredentialStatus, Order, OrderItem, ProductKind
from ollie.domain.states import OrderState
from ollie.domain.validate import validate_snapshot

NOW = 1_757_000_000
DAY = 24 * 60 * 60


def _item(**overrides: Any) -> OrderItem:
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


def _order(**overrides: Any) -> Order:
    fields = dict(
        code="ABCDEF",
        customer_telegram_id=1,
        state=OrderState.AWAITING_RECEIPT,
        items=(_item(),),
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


def _credential(**overrides: Any) -> Credential:
    fields = dict(
        id=1,
        product_id=1,
        payload="secret",
        status=CredentialStatus.AVAILABLE,
        order_code=None,
        delivered_at=None,
    )
    fields.update(overrides)
    return Credential(**fields)  # type: ignore[arg-type]


def test_empty_snapshot_is_ok() -> None:
    report = validate_snapshot([], [])
    assert report.ok
    assert report.errors == ()


def test_two_open_orders_sharing_payable_amount_is_an_error() -> None:
    a = _order(code="AAAAAA")
    b = _order(code="BBBBBB")
    report = validate_snapshot([a, b], [])
    assert not report.ok
    assert any("share payable_amount" in e for e in report.errors)


def test_shared_amount_across_closed_orders_is_not_an_error() -> None:
    a = _order(code="AAAAAA", state=OrderState.CANCELLED, expires_at=None)
    b = _order(code="BBBBBB", state=OrderState.CANCELLED, expires_at=None)
    report = validate_snapshot([a, b], [])
    assert report.ok


def test_reserved_credential_against_rejected_order_is_fine() -> None:
    # The spec keeps reservations through rejection so the customer can
    # retry — this must not be flagged as an error.
    rejected = _order(state=OrderState.RECEIPT_SUBMITTED, expires_at=None).with_state(
        OrderState.REJECTED
    )
    credential = _credential(status=CredentialStatus.RESERVED, order_code=rejected.code)
    report = validate_snapshot([rejected], [credential])
    assert report.ok


def test_reserved_credential_against_cancelled_order_is_an_error() -> None:
    cancelled = _order(state=OrderState.CANCELLED, expires_at=None)
    credential = _credential(status=CredentialStatus.RESERVED, order_code=cancelled.code)
    report = validate_snapshot([cancelled], [credential])
    assert not report.ok
    assert any("should have been released" in e for e in report.errors)


def test_reserved_credential_against_a_rejected_order_that_then_expired_is_an_error() -> None:
    """
    The leak the (rejected -> expired) edge exists to close, made
    concrete: a credential that stayed RESERVED through a rejection and
    was never released once the retry window lapsed must be flagged
    here, exactly as it would be for any other terminal order. Proves
    the fix is actually enforceable, not just legal to construct.
    """
    expired = (
        _order(state=OrderState.RECEIPT_SUBMITTED, expires_at=None)
        .with_state(OrderState.REJECTED)
        .with_state(OrderState.EXPIRED)
    )
    credential = _credential(status=CredentialStatus.RESERVED, order_code=expired.code)
    report = validate_snapshot([expired], [credential])
    assert not report.ok
    assert any("should have been released" in e for e in report.errors)


def test_delivered_credential_against_non_fulfilled_order_is_an_error() -> None:
    approved = _order(state=OrderState.RECEIPT_SUBMITTED, expires_at=None).with_state(
        OrderState.APPROVED, approved_at=NOW
    )
    credential = _credential(
        status=CredentialStatus.DELIVERED, order_code=approved.code, delivered_at=NOW
    )
    report = validate_snapshot([approved], [credential])
    assert not report.ok
    assert any("rather than fulfilled" in e for e in report.errors)


def test_delivered_credential_against_fulfilled_order_is_fine() -> None:
    fulfilled = (
        _order(state=OrderState.RECEIPT_SUBMITTED, expires_at=None)
        .with_state(OrderState.APPROVED, approved_at=NOW)
        .with_state(OrderState.FULFILLED, fulfilled_at=NOW)
    )
    credential = _credential(
        status=CredentialStatus.DELIVERED, order_code=fulfilled.code, delivered_at=NOW
    )
    report = validate_snapshot([fulfilled], [credential])
    assert report.ok


def test_credential_referencing_unknown_order_is_an_error() -> None:
    credential = _credential(status=CredentialStatus.RESERVED, order_code="ZZZZZZ")
    report = validate_snapshot([], [credential])
    assert not report.ok
    assert any("does not exist" in e for e in report.errors)


def test_available_credential_is_never_flagged() -> None:
    credential = _credential()  # available, order_code=None
    report = validate_snapshot([], [credential])
    assert report.ok


def test_overdue_awaiting_receipt_order_warns_when_now_given() -> None:
    order = _order(expires_at=NOW - 60)  # already past its expiry
    report = validate_snapshot([order], [], now=NOW)
    assert report.ok  # a warning, not an error
    assert any("past its expiry" in w for w in report.warnings)


def test_no_time_warnings_when_now_is_omitted() -> None:
    order = _order(expires_at=NOW - 60)
    report = validate_snapshot([order], [])  # now defaults to None
    assert report.warnings == ()


def test_duplicate_order_code_is_an_error() -> None:
    a = _order(code="AAAAAA", payable_amount=600_347)
    b = _order(code="AAAAAA", amount_tail=348, payable_amount=600_348)
    report = validate_snapshot([a, b], [])
    assert not report.ok
    assert any("duplicate order code" in e for e in report.errors)
