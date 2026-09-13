"""
The order state machine — the single source of truth for legal
transitions. Nothing else in this codebase (not a repository function,
not a bot handler) is permitted to hardcode a transition rule; every
caller that needs to know whether a transition is legal calls
check_transition().

ALLOWED is transcribed directly from docs/m1-spec.html's transition
table — not from the state diagram's colour legend. The diagram groups
`rejected` visually with the terminal failure states ("red = terminal
or recoverable failure"), but the table is unambiguous: REJECTED ->
AWAITING_RECEIPT is a real, spec'd retry edge (C14). Treating rejected
as terminal would silently break every retry. One edge, REJECTED ->
EXPIRED, is not in the spec's table at all — it closes a real leak (a
rejected order that's never retried held its reservation forever) and
was added deliberately; see the comment on ALLOWED below.

TERMINAL is *derived* from ALLOWED's actual sink nodes (states with no
outgoing edge), not hand-maintained — so it can never drift from the
transition table by a careless edit.
"""

from __future__ import annotations

from enum import StrEnum

from ollie.domain.errors import IllegalTransition


class OrderState(StrEnum):
    DRAFT = "draft"
    AWAITING_RECEIPT = "awaiting_receipt"
    RECEIPT_SUBMITTED = "receipt_submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FULFILLED = "fulfilled"


# The nine edges of the order state machine.
#
#   draft              -> awaiting_receipt     (C9: checkout)
#   awaiting_receipt    -> receipt_submitted    (C10: receipt accepted)
#   awaiting_receipt    -> cancelled            (C9: customer cancels)
#   awaiting_receipt    -> expired              (sweep: 24h elapsed)
#   receipt_submitted   -> approved             (O1: owner approves)
#   receipt_submitted   -> rejected             (O2: owner rejects)
#   rejected            -> awaiting_receipt     (C14: customer retries)
#   rejected            -> expired              (sweep: retry window elapsed)
#   approved            -> fulfilled            (auto/O5: delivered)
#
# The eight edges above the line are transcribed directly from
# docs/m1-spec.html's transition table. rejected -> expired is not: the
# original table had no path out of a rejected order that's never
# retried, which meant its reserved stock/credentials would be held
# forever. That was a genuine gap, caught in review and fixed here
# rather than left in place — this is the one edge in this module that
# the spec itself doesn't (yet) show, and docs/m1-spec.html should be
# read as superseded by this file on this specific point.
#
# What this module does NOT decide: how long a rejected order waits
# before the sweep expires it, or where that clock starts (most likely
# the event_log row for the receipt_submitted -> rejected transition,
# once persistence exists, rather than a new field on Order itself).
# That policy belongs to Phase 7's sweeper — see docs/roadmap.md.
ALLOWED: frozenset[tuple[OrderState, OrderState]] = frozenset(
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

# Sink nodes: every state ALLOWED has no outgoing edge from. Computed,
# not listed by hand — REJECTED correctly falls outside this set
# because it has an outgoing edge (-> AWAITING_RECEIPT).
TERMINAL: frozenset[OrderState] = frozenset(
    state for state in OrderState if not any(frm == state for frm, _ in ALLOWED)
)


def check_transition(frm: OrderState, to: OrderState) -> None:
    """Raise IllegalTransition unless (frm, to) is one of the nine edges in ALLOWED."""
    if (frm, to) not in ALLOWED:
        raise IllegalTransition(frm, to)
