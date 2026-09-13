"""
Cross-record validation: invariants no single Order or Credential can
see about itself, only about its relationship to the rest of the open
book. Mirrors the two-severity split the project's earlier dataset
layer used — errors mean the data is provably broken, warnings mean
it's suspicious and worth a human or a sweep's attention.

This operates on plain in-memory collections and has no database
dependency. Phase 7's sweeper is expected to load live rows into these
same domain objects and call this module against them; Phase 4's own
tests call it directly with hand-built objects.
"""

from __future__ import annotations

from dataclasses import dataclass

from ollie.domain.models import Credential, CredentialStatus, Order
from ollie.domain.states import OrderState

# Orders whose payable_amount must stay unique — the exact scope
# docs/m1-spec.html specifies for the unique-tail mechanism.
_OPEN_STATES = frozenset({OrderState.AWAITING_RECEIPT, OrderState.RECEIPT_SUBMITTED})

# States in which a credential may legitimately still be RESERVED.
# Includes REJECTED: the spec keeps reservations through rejection so
# the customer can retry with a corrected receipt.
_RESERVABLE_STATES = frozenset(
    {OrderState.AWAITING_RECEIPT, OrderState.RECEIPT_SUBMITTED, OrderState.REJECTED}
)


@dataclass(frozen=True, slots=True)
class ValidationReport:
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_snapshot(
    orders: list[Order],
    credentials: list[Credential],
    *,
    now: int | None = None,
) -> ValidationReport:
    """
    Validate a snapshot of orders and credentials against each other.

    `now`, if given, enables time-dependent warnings (an awaiting_receipt
    order already past its expiry that the sweep hasn't processed yet).
    It's optional and never defaulted to the wall clock internally —
    domain code never calls datetime.now() itself, so this function
    stays a pure, deterministic function of its arguments and is safe
    to unit test without any time-based flakiness.
    """
    errors: list[str] = []
    warnings: list[str] = []

    orders_by_code: dict[str, Order] = {}
    for order in orders:
        if order.code in orders_by_code:
            errors.append(f"duplicate order code {order.code!r} appears more than once")
        else:
            orders_by_code[order.code] = order

    _check_duplicate_payable_amounts(orders, errors)
    _check_credential_consistency(credentials, orders_by_code, errors)

    if now is not None:
        _check_overdue_expiry(orders, now, warnings)

    return ValidationReport(errors=tuple(errors), warnings=tuple(warnings))


def _check_duplicate_payable_amounts(orders: list[Order], errors: list[str]) -> None:
    seen: dict[int, str] = {}
    for order in orders:
        if order.state not in _OPEN_STATES:
            continue
        prior_code = seen.get(order.payable_amount)
        if prior_code is not None:
            errors.append(
                f"orders {prior_code!r} and {order.code!r} are both open and share "
                f"payable_amount={order.payable_amount} — the unique-tail mechanism "
                f"has failed"
            )
        else:
            seen[order.payable_amount] = order.code


def _check_credential_consistency(
    credentials: list[Credential],
    orders_by_code: dict[str, Order],
    errors: list[str],
) -> None:
    for credential in credentials:
        if credential.order_code is None:
            continue  # available credentials aren't tied to an order

        order = orders_by_code.get(credential.order_code)
        if order is None:
            errors.append(
                f"credential {credential.id} references order {credential.order_code!r}, "
                f"which does not exist in this snapshot"
            )
            continue

        if credential.status == CredentialStatus.RESERVED and order.state not in _RESERVABLE_STATES:
            errors.append(
                f"credential {credential.id} is reserved against order {order.code!r}, "
                f"which is in state {order.state.value!r} — its reservation should "
                f"have been released"
            )

        if credential.status == CredentialStatus.DELIVERED and order.state != OrderState.FULFILLED:
            errors.append(
                f"credential {credential.id} is marked delivered against order "
                f"{order.code!r}, which is in state {order.state.value!r} rather "
                f"than fulfilled"
            )


def _check_overdue_expiry(orders: list[Order], now: int, warnings: list[str]) -> None:
    for order in orders:
        if (
            order.state == OrderState.AWAITING_RECEIPT
            and order.expires_at is not None
            and order.expires_at < now
        ):
            warnings.append(
                f"order {order.code!r} is past its expiry ({order.expires_at} < {now}) "
                f"and the sweep has not processed it yet"
            )
