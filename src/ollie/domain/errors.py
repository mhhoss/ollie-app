"""
Domain-level exceptions.

Two failure categories live here, and they are deliberately not unified
into one exception type:

  - IllegalTransition names a static fact about the order state machine
    (states.py): the (from, to) pair is never valid, full stop. Domain
    code raises this directly, and it always means either a caller bug
    or an attempt to do something the business process forbids.

  - InsufficientStock, DuplicateReceipt, and AmountCollision name a
    business-rule violation at reservation/allocation time, not a
    state-machine violation.

Deliberately absent from this module: any notion of "the order moved
on since you last read it" (a stale/already-processed condition, e.g.
two near-simultaneous approval taps on the same order). That is a live
concurrency concern that only the persistence layer can detect, since
it requires re-reading current state from storage — it belongs to
Phase 5's repository code, as its own distinct exception, specifically
so callers (bot handlers) can tell "a real defect" (IllegalTransition)
apart from "a normal race that just needs a quiet re-check" and handle
the two completely differently.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Type-only: avoids a runtime import cycle with states.py, which
    # imports IllegalTransition from this module.
    from ollie.domain.states import OrderState


class IllegalTransition(Exception):
    """Raised when (from_state, to_state) is not an edge in states.ALLOWED."""

    def __init__(self, from_state: OrderState, to_state: OrderState) -> None:
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(f"illegal order transition: {from_state!r} -> {to_state!r}")


class InsufficientStock(Exception):
    """Raised when a reservation is attempted against stock/credentials that aren't available."""


class DuplicateReceipt(Exception):
    """Raised when a receipt image's hash matches one already submitted on another order."""


class AmountCollision(Exception):
    """Raised when no unique payable_amount could be allocated for a new order."""
