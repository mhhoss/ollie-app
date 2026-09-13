"""
Domain models — the business objects Ollie's order flow is built from.

All frozen, all slotted, all self-validating in __post_init__: a record
that fails these checks cannot be constructed at all, the same
discipline the project's earlier dataset layer used. State transitions
happen through Order.with_state(), which calls dataclasses.replace()
under the hood — since replace() reconstructs the object through
__init__, __post_init__ reruns automatically on every transition, so
every invariant below is re-checked on every single state change for
free, with no second validation path that could drift out of sync with
the constructor's.

Two identity conventions, deliberately not a uniform "everything gets
a surrogate int id":

  - Product, Variant, and Credential are catalog/inventory rows with no
    natural key of their own — they carry the database's surrogate
    `id: int`, assigned before an Order ever references them.
  - Order and Customer already have a perfect natural key each — the
    order `code` (what a human reads aloud) and the customer's Telegram
    `telegram_id` — so nothing here invents a surrogate id for them.
    Credential.order_code and Order.customer_telegram_id reference
    those natural keys directly. Phase 5's repository layer is
    responsible for mapping this onto whatever actual foreign-key
    columns the schema uses; that mapping is a storage concern, not a
    domain one.

OrderItem and Receipt are snapshots taken at a point in time (what the
customer was actually charged, what a receipt image actually showed) —
they carry no id of their own; they exist only inside an Order or
alongside one.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from ollie.domain import money
from ollie.domain.codes import is_valid_code
from ollie.domain.states import OrderState, check_transition

_PHONE_RE = re.compile(r"^09\d{9}$")
_POSTAL_RE = re.compile(r"^\d{10}$")


class ProductKind(StrEnum):
    DIGITAL = "digital"
    PHYSICAL = "physical"


class CredentialStatus(StrEnum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    DELIVERED = "delivered"


class ReceiptVerdict(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Product:
    id: int
    kind: ProductKind
    name: str
    description: str
    price: int
    cost_price: int
    is_active: bool
    category_id: int | None = None
    photo_file_id: str | None = None

    def __post_init__(self) -> None:
        if self.id <= 0:
            raise ValueError(f"Product.id must be positive, got {self.id}")
        if not self.name.strip():
            raise ValueError(f"Product.name cannot be empty (id={self.id})")
        if len(self.description) > 300:
            raise ValueError(
                f"Product.description exceeds 300 chars ({len(self.description)}) — "
                f"longer breaks Telegram's photo caption limit (id={self.id})"
            )
        if self.price < 0:
            raise ValueError(f"Product.price cannot be negative, got {self.price} (id={self.id})")
        if self.cost_price < 0:
            raise ValueError(
                f"Product.cost_price cannot be negative, got {self.cost_price} (id={self.id})"
            )


@dataclass(frozen=True, slots=True)
class Variant:
    id: int
    product_id: int
    label: str
    price_delta: int  # may be negative (a discount variant); usually 0
    stock: int
    reserved: int

    def __post_init__(self) -> None:
        if self.id <= 0:
            raise ValueError(f"Variant.id must be positive, got {self.id}")
        if not self.label.strip():
            raise ValueError(f"Variant.label cannot be empty (id={self.id})")
        if self.stock < 0:
            raise ValueError(f"Variant.stock cannot be negative, got {self.stock} (id={self.id})")
        if self.reserved < 0:
            raise ValueError(
                f"Variant.reserved cannot be negative, got {self.reserved} (id={self.id})"
            )
        if self.reserved > self.stock:
            raise ValueError(
                f"Variant.reserved ({self.reserved}) cannot exceed stock "
                f"({self.stock}) (id={self.id})"
            )


@dataclass(frozen=True, slots=True)
class Credential:
    id: int
    product_id: int
    payload: str
    status: CredentialStatus
    order_code: str | None = None  # the Order.code it's reserved/delivered against
    delivered_at: int | None = None

    def __post_init__(self) -> None:
        if self.id <= 0:
            raise ValueError(f"Credential.id must be positive, got {self.id}")
        if not self.payload.strip():
            raise ValueError(f"Credential.payload cannot be empty (id={self.id})")

        if self.status == CredentialStatus.AVAILABLE:
            if self.order_code is not None:
                raise ValueError(
                    f"Credential {self.id} is available but has order_code={self.order_code!r} "
                    f"— an available credential must not be tied to an order"
                )
            if self.delivered_at is not None:
                raise ValueError(f"Credential {self.id} is available but has delivered_at set")
        else:
            if self.order_code is None:
                raise ValueError(
                    f"Credential {self.id} has status={self.status.value} but no order_code "
                    f"— reserved/delivered credentials must be tied to an order"
                )

        if self.status == CredentialStatus.DELIVERED and self.delivered_at is None:
            raise ValueError(f"Credential {self.id} is delivered but delivered_at is not set")
        if self.status == CredentialStatus.RESERVED and self.delivered_at is not None:
            raise ValueError(f"Credential {self.id} is reserved but already has delivered_at set")


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Customer:
    telegram_id: int
    full_name: str | None = None
    phone: str | None = None  # expects already-normalized ASCII, see ollie.fmt.digits
    address: str | None = None
    postal_code: str | None = None
    is_blocked: bool = False

    def __post_init__(self) -> None:
        if self.telegram_id <= 0:
            raise ValueError(f"Customer.telegram_id must be positive, got {self.telegram_id}")
        if self.phone is not None and not _PHONE_RE.match(self.phone):
            raise ValueError(
                f"Customer.phone must match normalized 09XXXXXXXXX, got {self.phone!r}"
            )
        if self.postal_code is not None and not _POSTAL_RE.match(self.postal_code):
            raise ValueError(
                f"Customer.postal_code must be exactly 10 digits, got {self.postal_code!r}"
            )


# ---------------------------------------------------------------------------
# Order
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class OrderItem:
    """A snapshot of one catalog line at the moment an order was placed.
    Prices and the name are copied in, not looked up live, so an invoice
    renders identically no matter what happens to the catalog afterwards."""

    product_id: int
    variant_id: int | None
    kind: ProductKind
    name_snapshot: str
    unit_price: int
    cost_price_snapshot: int
    quantity: int

    def __post_init__(self) -> None:
        if self.product_id <= 0:
            raise ValueError(f"OrderItem.product_id must be positive, got {self.product_id}")
        if not self.name_snapshot.strip():
            raise ValueError("OrderItem.name_snapshot cannot be empty")
        if self.unit_price < 0:
            raise ValueError(
                f"OrderItem.unit_price cannot be negative, got {self.unit_price} "
                f"({self.name_snapshot!r}) — a variant's price_delta may be negative, "
                f"but the price actually charged never is"
            )
        if self.cost_price_snapshot < 0:
            raise ValueError(
                f"OrderItem.cost_price_snapshot cannot be negative, got "
                f"{self.cost_price_snapshot} ({self.name_snapshot!r})"
            )
        if self.quantity < 1:
            raise ValueError(
                f"OrderItem.quantity must be at least 1, got {self.quantity} "
                f"({self.name_snapshot!r})"
            )

    @property
    def line_total(self) -> int:
        return self.unit_price * self.quantity


@dataclass(frozen=True, slots=True)
class Order:
    code: str
    customer_telegram_id: int
    state: OrderState
    items: tuple[OrderItem, ...]
    subtotal: int
    shipping_cost: int
    amount_tail: int
    payable_amount: int
    is_physical: bool
    ship_name: str | None
    ship_phone: str | None
    ship_address: str | None
    tracking_number: str | None
    carrier: str | None
    reject_count: int
    invoice_message_id: int | None
    expires_at: int | None
    created_at: int
    approved_at: int | None
    fulfilled_at: int | None

    def __post_init__(self) -> None:
        if not is_valid_code(self.code):
            raise ValueError(f"Order.code {self.code!r} is not a valid order code")
        if self.customer_telegram_id <= 0:
            raise ValueError(
                f"Order.customer_telegram_id must be positive, got {self.customer_telegram_id}"
            )
        if not self.items:
            raise ValueError(f"Order {self.code!r} has no items")
        if self.reject_count < 0:
            raise ValueError(f"Order {self.code!r}: reject_count cannot be negative")
        if self.created_at <= 0:
            raise ValueError(f"Order {self.code!r}: created_at must be a positive timestamp")

        # --- cross-checks derived from items: catch drift between what
        # was computed and what the items actually say. ---
        expected_subtotal = sum(item.line_total for item in self.items)
        if self.subtotal != expected_subtotal:
            raise ValueError(
                f"Order {self.code!r}: subtotal={self.subtotal} does not match "
                f"sum of item totals ({expected_subtotal})"
            )

        expected_is_physical = any(item.kind == ProductKind.PHYSICAL for item in self.items)
        if self.is_physical != expected_is_physical:
            raise ValueError(
                f"Order {self.code!r}: is_physical={self.is_physical} does not match "
                f"its items (expected {expected_is_physical})"
            )

        # --- money ---
        if self.shipping_cost < 0:
            raise ValueError(f"Order {self.code!r}: shipping_cost cannot be negative")
        if not self.is_physical and self.shipping_cost != 0:
            raise ValueError(
                f"Order {self.code!r}: a purely digital order cannot carry a "
                f"shipping_cost ({self.shipping_cost})"
            )
        expected_payable = money.payable(self.subtotal, self.shipping_cost, self.amount_tail)
        if self.payable_amount != expected_payable:
            raise ValueError(
                f"Order {self.code!r}: payable_amount={self.payable_amount} does not equal "
                f"subtotal + shipping_cost + amount_tail ({expected_payable})"
            )

        # --- shipping snapshot: all-or-nothing, tied to is_physical ---
        ship_fields = (self.ship_name, self.ship_phone, self.ship_address)
        if self.is_physical:
            if any(f is None or not f.strip() for f in ship_fields):
                raise ValueError(
                    f"Order {self.code!r} is physical but is missing ship_name/"
                    f"ship_phone/ship_address"
                )
        else:
            if any(f is not None for f in ship_fields):
                raise ValueError(
                    f"Order {self.code!r} is digital-only but carries a shipping snapshot"
                )

        # --- tracking: only ever present once a physical order is fulfilled ---
        has_tracking = self.tracking_number is not None
        has_carrier = self.carrier is not None
        if has_tracking != has_carrier:
            raise ValueError(
                f"Order {self.code!r}: tracking_number and carrier must be set together "
                f"(tracking_number={self.tracking_number!r}, carrier={self.carrier!r})"
            )
        should_have_tracking = self.is_physical and self.state == OrderState.FULFILLED
        if has_tracking != should_have_tracking:
            raise ValueError(
                f"Order {self.code!r}: tracking_number presence ({has_tracking}) is "
                f"inconsistent with state={self.state.value} / is_physical={self.is_physical} "
                f"(a tracking number exists only for a physical order once fulfilled)"
            )

        # --- the expiry invariant: the whole reason this exists is the
        # 24h payment sweep, which only ever looks at awaiting_receipt
        # rows. Every other state — receipt_submitted included, per the
        # spec's "never expire while a human is reviewing" rule — must
        # carry no expiry at all. ---
        should_have_expiry = self.state == OrderState.AWAITING_RECEIPT
        if (self.expires_at is not None) != should_have_expiry:
            raise ValueError(
                f"Order {self.code!r}: expires_at={self.expires_at!r} is inconsistent with "
                f"state={self.state.value} (expected non-null only in awaiting_receipt)"
            )

        # --- timestamps track their state, not just their own field ---
        should_have_approved_at = self.state in (OrderState.APPROVED, OrderState.FULFILLED)
        if (self.approved_at is not None) != should_have_approved_at:
            raise ValueError(
                f"Order {self.code!r}: approved_at={self.approved_at!r} is inconsistent with "
                f"state={self.state.value}"
            )

        should_have_fulfilled_at = self.state == OrderState.FULFILLED
        if (self.fulfilled_at is not None) != should_have_fulfilled_at:
            raise ValueError(
                f"Order {self.code!r}: fulfilled_at={self.fulfilled_at!r} is inconsistent with "
                f"state={self.state.value}"
            )

    def with_state(self, to: OrderState, **field_overrides: Any) -> Order:
        """
        Transition to a new state, producing a new Order.

        check_transition() is called first — an illegal (from, to) pair
        never reaches dataclasses.replace() at all. Any field this
        transition changes besides `state` (expires_at, approved_at,
        tracking_number, ...) must be passed explicitly as a keyword
        override; anything not overridden carries its old value
        forward untouched, and __post_init__ re-validates the whole
        object against that combination.

        This is deliberately not "smart" about what a transition
        implies — it does not, for example, automatically clear
        expires_at when leaving awaiting_receipt. That is what makes
        it safe: a caller who forgets to pass the right override gets
        a loud ValueError from __post_init__ (the old, now-invalid
        value carried forward), not a silently wrong Order.
        """
        check_transition(self.state, to)
        return dataclasses.replace(self, state=to, **field_overrides)

    @classmethod
    def create(
        cls,
        *,
        code: str,
        customer_telegram_id: int,
        items: list[OrderItem] | tuple[OrderItem, ...],
        shipping_cost: int,
        amount_tail: int,
        expires_at: int,
        created_at: int,
        ship_name: str | None = None,
        ship_phone: str | None = None,
        ship_address: str | None = None,
        invoice_message_id: int | None = None,
    ) -> Order:
        """
        The C9 checkout operation: build a brand-new Order directly in
        AWAITING_RECEIPT. There is no prior Order instance to transition
        from — `draft` is never a state any persisted Order occupies —
        so this factory proves the (draft -> awaiting_receipt) edge is
        FSM-legal itself, via check_transition, rather than relying on
        with_state() against an object that was never constructed.

        subtotal, is_physical, and payable_amount are derived here from
        `items` rather than accepted as caller-supplied arguments, so
        there is exactly one place they can be computed and no way for
        a caller to pass an out-of-sync value — __post_init__ would
        catch a mismatch if it did, but this factory doesn't give it
        the opportunity.
        """
        check_transition(OrderState.DRAFT, OrderState.AWAITING_RECEIPT)

        items = tuple(items)
        subtotal = sum(item.line_total for item in items)
        is_physical = any(item.kind == ProductKind.PHYSICAL for item in items)
        payable_amount = money.payable(subtotal, shipping_cost, amount_tail)

        return cls(
            code=code,
            customer_telegram_id=customer_telegram_id,
            state=OrderState.AWAITING_RECEIPT,
            items=items,
            subtotal=subtotal,
            shipping_cost=shipping_cost,
            amount_tail=amount_tail,
            payable_amount=payable_amount,
            is_physical=is_physical,
            ship_name=ship_name,
            ship_phone=ship_phone,
            ship_address=ship_address,
            tracking_number=None,
            carrier=None,
            reject_count=0,
            invoice_message_id=invoice_message_id,
            expires_at=expires_at,
            created_at=created_at,
            approved_at=None,
            fulfilled_at=None,
        )


# ---------------------------------------------------------------------------
# Receipt
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Receipt:
    order_code: str
    file_id: str
    file_unique_id: str
    image_hash: str
    is_active: bool
    submitted_at: int
    verdict: ReceiptVerdict | None = None
    reject_reason: str | None = None
    reviewed_at: int | None = None

    def __post_init__(self) -> None:
        if not is_valid_code(self.order_code):
            raise ValueError(f"Receipt.order_code {self.order_code!r} is not a valid order code")
        if not self.file_id.strip():
            raise ValueError("Receipt.file_id cannot be empty")
        if not self.file_unique_id.strip():
            raise ValueError("Receipt.file_unique_id cannot be empty")
        if not self.image_hash.strip():
            raise ValueError("Receipt.image_hash cannot be empty")
        if self.submitted_at <= 0:
            raise ValueError("Receipt.submitted_at must be a positive timestamp")

        if self.verdict is None:
            if self.reviewed_at is not None:
                raise ValueError("Receipt has no verdict yet but reviewed_at is set")
            if self.reject_reason is not None:
                raise ValueError("Receipt has no verdict yet but reject_reason is set")
        else:
            if self.reviewed_at is None:
                raise ValueError(f"Receipt has verdict={self.verdict.value} but no reviewed_at")
            if self.verdict == ReceiptVerdict.REJECTED and not self.reject_reason:
                raise ValueError("Receipt was rejected but has no reject_reason")
            if self.verdict == ReceiptVerdict.APPROVED and self.reject_reason is not None:
                raise ValueError("Receipt was approved but carries a reject_reason")
