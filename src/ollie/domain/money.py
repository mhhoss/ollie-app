"""
Money is always an int Toman. No float may touch a money value
anywhere in this module or its callers — floating point has no place
near an amount a customer is asked to pay.

This module owns the *arithmetic* of the unique-payment-amount
mechanism (picking a candidate tail, stepping to the next one on
collision) but never the uniqueness check itself — that requires
querying live orders, which only the persistence layer (Phase 5) can
do. Domain proposes a candidate; the database disposes of whether it's
actually free.
"""

from __future__ import annotations

import secrets

TAIL_MIN = 100
TAIL_MAX = 999
_TAIL_SPAN = TAIL_MAX - TAIL_MIN + 1


def random_tail() -> int:
    """A random 3-digit disambiguating tail in [100, 999]."""
    return TAIL_MIN + secrets.randbelow(_TAIL_SPAN)


def next_tail(tail: int) -> int:
    """
    The deterministic fallback step for the retry-until-free loop
    docs/m1-spec.html describes ("retry up to 50 times, then fall back
    to total + 1 upward until free"). Wraps around within [100, 999]
    rather than escaping the range, so the invoice's "3-digit tail"
    promise — and the Order.amount_tail invariant — never breaks even
    after many collisions.
    """
    if not (TAIL_MIN <= tail <= TAIL_MAX):
        raise ValueError(f"tail must be within [{TAIL_MIN}, {TAIL_MAX}], got {tail}")
    return TAIL_MIN + (tail - TAIL_MIN + 1) % _TAIL_SPAN


def payable(subtotal: int, shipping_cost: int, tail: int) -> int:
    """The amount actually shown on the invoice and expected by bank transfer."""
    if subtotal < 0:
        raise ValueError(f"subtotal cannot be negative, got {subtotal}")
    if shipping_cost < 0:
        raise ValueError(f"shipping_cost cannot be negative, got {shipping_cost}")
    if not (TAIL_MIN <= tail <= TAIL_MAX):
        raise ValueError(f"tail must be within [{TAIL_MIN}, {TAIL_MAX}], got {tail}")
    return subtotal + shipping_cost + tail
