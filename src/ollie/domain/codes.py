"""
Order codes — the customer-facing identifier read aloud over the
phone and typed into a tracking-history lookup.

The alphabet excludes 0/O/I/1: characters that are ambiguous when
spoken aloud or handwritten. Generated with `secrets`, not `random` —
order codes are enumeration-resistant by construction even though they
are not secrets in the security sense (see docs/m1-spec.html's
conventions section).
"""

from __future__ import annotations

import secrets

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6

_ALPHABET_SET = frozenset(ALPHABET)


def generate_code() -> str:
    """A fresh 6-character order code. Uniqueness against existing orders
    is a persistence-layer concern (Phase 5) — this function only
    guarantees the shape."""
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def is_valid_code(value: str) -> bool:
    """True if value has the right length and every character is in ALPHABET."""
    return len(value) == CODE_LENGTH and all(ch in _ALPHABET_SET for ch in value)
