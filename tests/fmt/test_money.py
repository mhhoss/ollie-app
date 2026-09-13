from __future__ import annotations

import pytest

from ollie.fmt.money import toman


def test_toman_matches_spec_example() -> None:
    assert toman(1_450_347) == "۱٬۴۵۰٬۳۴۷ تومان"


def test_toman_small_amount_no_separator() -> None:
    assert toman(347) == "۳۴۷ تومان"


def test_toman_zero() -> None:
    assert toman(0) == "۰ تومان"


def test_toman_exact_thousand() -> None:
    assert toman(1_000) == "۱٬۰۰۰ تومان"


def test_toman_rejects_negative() -> None:
    with pytest.raises(ValueError):
        toman(-1)
