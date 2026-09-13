from __future__ import annotations

from ollie.fmt.digits import (
    normalize_identifier,
    normalize_text,
    to_ascii_digits,
    to_persian_digits,
)


def test_to_ascii_digits_converts_persian() -> None:
    assert to_ascii_digits("۰۹۱۲۱۲۳۴۵۶۷") == "09121234567"


def test_to_ascii_digits_converts_arabic() -> None:
    assert to_ascii_digits("٠٩١٢١٢٣٤٥٦٧") == "09121234567"


def test_to_ascii_digits_leaves_other_text_untouched() -> None:
    assert to_ascii_digits("علی ۱۲۳") == "علی 123"


def test_to_persian_digits_round_trip() -> None:
    assert to_persian_digits("1450347") == "۱۴۵۰۳۴۷"


def test_normalize_text_converts_digits_and_letters() -> None:
    # Arabic ي/ك instead of Persian ی/ک — a real, common typing pattern.
    assert normalize_text("لباس زير زنانه از كجا") == "لباس زیر زنانه از کجا"


def test_normalize_text_preserves_internal_space() -> None:
    # Names must keep their space — C6's "contains a space" check depends on it.
    assert normalize_text("  علی محمدی  ") == "علی محمدی"


def test_normalize_text_strips_zero_width_non_joiner() -> None:
    assert normalize_text("می‌خواهم") == "می‌خواهم".replace("‌", "")


def test_normalize_identifier_strips_spaces_and_dashes() -> None:
    assert normalize_identifier("0912 123 4567") == "09121234567"
    assert normalize_identifier("0912-123-4567") == "09121234567"


def test_normalize_identifier_converts_persian_digits_and_strips_formatting() -> None:
    assert normalize_identifier("۰۹۱۲-۱۲۳-۴۵۶۷") == "09121234567"
