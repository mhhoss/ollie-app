"""
Persistence-level exceptions — "this row doesn't exist" and "you're
acting on a stale read," as distinct from `ollie.domain.errors`'s
"this operation is not a legal fact about the business process."

`OrderNotFound` / `CustomerNotFound` / `CredentialNotFound` mean a
lookup key doesn't resolve to a row. They are not FSM violations
(`IllegalTransition`, still raised directly by `Order.with_state`) and
not business-rule violations (`InsufficientStock`, `DuplicateReceipt`,
`AmountCollision`, raised from `ollie.domain.errors` by the repo
functions in this package) — they're a third thing this layer needed
its own vocabulary for, exactly as `ollie.domain.errors`'s module
docstring anticipated.
"""

from __future__ import annotations


class OrderNotFound(Exception):
    """Raised when a lookup by order code matches no row."""


class CustomerNotFound(Exception):
    """Raised when a lookup by telegram_id matches no row."""


class CredentialNotFound(Exception):
    """Raised when a lookup by credential id matches no row."""
