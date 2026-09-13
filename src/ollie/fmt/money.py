"""
Toman display formatting — for showing an amount to a human, never for
storage or arithmetic. ollie.domain.money is where the actual int
values live and are computed; this module only turns one into the
string docs/m1-spec.html's conventions specify, e.g. "۱٬۴۵۰٬۳۴۷ تومان".
"""

from __future__ import annotations

from ollie.fmt.digits import to_persian_digits

_THOUSANDS_SEPARATOR = "٬"  # ARABIC THOUSANDS SEPARATOR ٬


def _grouped(n: int) -> str:
    digits = str(n)
    groups: list[str] = []
    while len(digits) > 3:
        groups.insert(0, digits[-3:])
        digits = digits[:-3]
    groups.insert(0, digits)
    return _THOUSANDS_SEPARATOR.join(groups)


def toman(amount: int) -> str:
    """Format a non-negative Toman amount for display, e.g. toman(1450347) -> '۱٬۴۵۰٬۳۴۷ تومان'."""
    if amount < 0:
        raise ValueError(f"toman() does not support negative amounts, got {amount}")
    return f"{to_persian_digits(_grouped(amount))} تومان"
