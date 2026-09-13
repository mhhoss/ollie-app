from __future__ import annotations

import pytest

from ollie.domain.money import TAIL_MAX, TAIL_MIN, next_tail, payable, random_tail


def test_random_tail_always_in_range() -> None:
    for _ in range(1000):
        tail = random_tail()
        assert TAIL_MIN <= tail <= TAIL_MAX


def test_next_tail_steps_by_one() -> None:
    assert next_tail(100) == 101
    assert next_tail(500) == 501
    assert next_tail(998) == 999


def test_next_tail_wraps_around_at_the_top() -> None:
    # Wraps rather than escaping [100, 999] — the invoice's "3-digit
    # tail" promise, and Order.amount_tail's own invariant, must never
    # break even after many collisions.
    assert next_tail(999) == 100


def test_next_tail_rejects_out_of_range_input() -> None:
    with pytest.raises(ValueError):
        next_tail(99)
    with pytest.raises(ValueError):
        next_tail(1000)


def test_payable_arithmetic() -> None:
    assert payable(subtotal=1_450_000, shipping_cost=0, tail=347) == 1_450_347
    assert payable(subtotal=0, shipping_cost=50_000, tail=100) == 50_100


def test_payable_rejects_negative_subtotal() -> None:
    with pytest.raises(ValueError):
        payable(subtotal=-1, shipping_cost=0, tail=100)


def test_payable_rejects_negative_shipping() -> None:
    with pytest.raises(ValueError):
        payable(subtotal=0, shipping_cost=-1, tail=100)


def test_payable_rejects_out_of_range_tail() -> None:
    with pytest.raises(ValueError):
        payable(subtotal=0, shipping_cost=0, tail=99)
    with pytest.raises(ValueError):
        payable(subtotal=0, shipping_cost=0, tail=1000)
