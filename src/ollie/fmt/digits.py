"""
Digit and character normalization for customer-typed input.

Persian and Arabic-Indic digits, plus Arabic letter variants some
keyboards produce instead of their Persian equivalents, are common in
real customer input (phone numbers, postal codes, names). Everything
downstream — domain validation included — expects ASCII digits and
Persian letter forms; this module is where that conversion happens,
once, so it never has to happen twice.

Two normalizers, not one, because they don't agree on whitespace:
normalize_text() is safe for free text like a name or an address
(where a space is meaningful and must survive), while
normalize_identifier() also strips spaces and dashes, for fields that
are really just digit strings a customer typed with cosmetic grouping
(phone numbers, postal codes, tracking numbers).
"""

from __future__ import annotations

_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_ASCII_DIGITS = "0123456789"

_TO_ASCII_DIGITS = str.maketrans(_PERSIAN_DIGITS + _ARABIC_DIGITS, _ASCII_DIGITS * 2)
_TO_PERSIAN_DIGITS = str.maketrans(_ASCII_DIGITS, _PERSIAN_DIGITS)

# Arabic ي/ك typed on some keyboards instead of Persian ی/ک.
_ARABIC_TO_PERSIAN_LETTERS = str.maketrans({"ي": "ی", "ك": "ک"})

_ZERO_WIDTH_NON_JOINER = "‌"


def to_ascii_digits(text: str) -> str:
    """Convert Persian/Arabic-Indic digits in text to ASCII 0-9. Other characters pass through."""
    return text.translate(_TO_ASCII_DIGITS)


def to_persian_digits(text: str) -> str:
    """Convert ASCII digits in text to Persian digits. For display only — never for storage."""
    return text.translate(_TO_PERSIAN_DIGITS)


def normalize_text(text: str) -> str:
    """
    Normalize free text a customer typed (a name, an address): digits
    and ي/ك become their ASCII/Persian forms, zero-width non-joiners
    are stripped, and the result is trimmed — but internal whitespace
    is preserved, since a name like "علی محمدی" depends on its space
    to pass the "contains a space" check at C6.
    """
    text = to_ascii_digits(text)
    text = text.translate(_ARABIC_TO_PERSIAN_LETTERS)
    text = text.replace(_ZERO_WIDTH_NON_JOINER, "")
    return text.strip()


def normalize_identifier(text: str) -> str:
    """
    Normalize a field that is really just digits with cosmetic
    formatting (phone, postal code, tracking number, card number):
    everything normalize_text() does, plus stripping spaces and
    dashes, so "0912 123 4567" and "0912-123-4567" and "09121234567"
    all validate identically.
    """
    text = normalize_text(text)
    return text.replace(" ", "").replace("-", "")
