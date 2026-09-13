"""
The state machine is the load-bearing part of the whole domain layer.
This file's job is to make "flawless idempotency" a checked fact, not
an adjective: every one of the 8x8=64 (from, to) pairs is exercised,
not just the nine that are supposed to work.
"""

from __future__ import annotations

import itertools

import pytest

from ollie.domain.errors import IllegalTransition
from ollie.domain.states import ALLOWED, TERMINAL, OrderState, check_transition

# Transcribed independently, as a redundant safety net against ALLOWED
# silently drifting in a future edit — this test fails if the two ever
# disagree. Eight of these nine edges come straight from
# docs/m1-spec.html's transition table; (REJECTED, EXPIRED) does not —
# it was added deliberately during the Phase 4 review to close a real
# leak (a rejected order that's never retried held its reservation
# forever) and is documented as such in states.py.
_EXPECTED_EDGES = frozenset(
    {
        (OrderState.DRAFT, OrderState.AWAITING_RECEIPT),
        (OrderState.AWAITING_RECEIPT, OrderState.RECEIPT_SUBMITTED),
        (OrderState.AWAITING_RECEIPT, OrderState.CANCELLED),
        (OrderState.AWAITING_RECEIPT, OrderState.EXPIRED),
        (OrderState.RECEIPT_SUBMITTED, OrderState.APPROVED),
        (OrderState.RECEIPT_SUBMITTED, OrderState.REJECTED),
        (OrderState.REJECTED, OrderState.AWAITING_RECEIPT),
        (OrderState.REJECTED, OrderState.EXPIRED),
        (OrderState.APPROVED, OrderState.FULFILLED),
    }
)


def test_allowed_matches_spec_exactly() -> None:
    assert ALLOWED == _EXPECTED_EDGES
    assert len(ALLOWED) == 9


def test_full_cartesian_product_of_transitions() -> None:
    """Every one of the 64 (from, to) pairs: legal iff it's a spec'd edge."""
    all_states = list(OrderState)
    assert len(all_states) == 8  # guards the "8x8=64" claim itself

    checked = 0
    for frm, to in itertools.product(all_states, all_states):
        checked += 1
        if (frm, to) in ALLOWED:
            check_transition(frm, to)  # must not raise
        else:
            with pytest.raises(IllegalTransition) as exc_info:
                check_transition(frm, to)
            assert exc_info.value.from_state == frm
            assert exc_info.value.to_state == to

    assert checked == 64


def test_terminal_excludes_rejected() -> None:
    """
    The spec's diagram colours `rejected` the same red as the terminal
    failure states, but the transition table gives it a real outgoing
    edge (-> awaiting_receipt, the C14 retry). TERMINAL must reflect
    the table, not the diagram's colour legend.
    """
    assert OrderState.REJECTED not in TERMINAL


def test_terminal_is_exactly_the_three_sink_states() -> None:
    assert TERMINAL == frozenset({OrderState.FULFILLED, OrderState.CANCELLED, OrderState.EXPIRED})


def test_terminal_states_have_no_outgoing_edges() -> None:
    for state in TERMINAL:
        outgoing = [to for frm, to in ALLOWED if frm == state]
        assert outgoing == [], f"{state} is TERMINAL but has outgoing edges: {outgoing}"


def test_receipt_submitted_only_reachable_forward_to_approved_or_rejected() -> None:
    """The one rule the spec calls out as the most damaging to get wrong:
    an order awaiting human review must never silently expire or vanish."""
    outgoing = {to for frm, to in ALLOWED if frm == OrderState.RECEIPT_SUBMITTED}
    assert outgoing == {OrderState.APPROVED, OrderState.REJECTED}


def test_nothing_transitions_into_draft() -> None:
    incoming = {frm for frm, to in ALLOWED if to == OrderState.DRAFT}
    assert incoming == set()


def test_rejected_can_expire() -> None:
    """
    The fix: a rejected order the customer never retries must have a
    path to release its reservation, not sit reserved forever. Named
    separately from the cartesian-product test above so this specific
    regression has its own readable failure message if it ever breaks.
    """
    check_transition(OrderState.REJECTED, OrderState.EXPIRED)  # must not raise


def test_expired_is_reachable_from_two_different_states() -> None:
    """
    EXPIRED now has two distinct incoming edges — a plain unpaid order
    (awaiting_receipt) and one that was rejected and never retried
    (rejected). Both must lead to the same terminal state so the sweep
    only needs one release path, not two.
    """
    incoming = {frm for frm, to in ALLOWED if to == OrderState.EXPIRED}
    assert incoming == {OrderState.AWAITING_RECEIPT, OrderState.REJECTED}
