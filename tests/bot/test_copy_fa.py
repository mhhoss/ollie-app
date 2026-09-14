"""
Mechanical checks over every string constant in copy_fa.py: it's
non-empty, it renders with sample data, and it never smuggles a Latin
numeral into Persian prose. These don't check the *content* is good
Persian — that's a native speaker's job (docs/roadmap.md's Phase 6
checkpoint) — only that the module is internally consistent.
"""

from __future__ import annotations

import re
import string

import pytest

from ollie.bot import copy_fa
from ollie.domain.states import OrderState

_FIELD_PLACEHOLDER_RE = re.compile(r"\{[^{}]*\}")


def _string_constants() -> dict[str, str]:
    return {
        name: value
        for name, value in vars(copy_fa).items()
        if name.isupper() and isinstance(value, str)
    }


def _template_field_names(template: str) -> set[str]:
    return {field_name for _, field_name, _, _ in string.Formatter().parse(template) if field_name}


@pytest.mark.parametrize("name", sorted(_string_constants()))
def test_constant_is_non_empty(name: str) -> None:
    assert _string_constants()[name].strip() != ""


@pytest.mark.parametrize("name", sorted(_string_constants()))
def test_template_renders_with_sample_kwargs(name: str) -> None:
    template = _string_constants()[name]
    fields = _template_field_names(template)
    sample = {field: "نمونه" for field in fields}
    template.format(**sample)  # must not raise


@pytest.mark.parametrize("name", sorted(_string_constants()))
def test_no_ascii_digit_outside_a_placeholder(name: str) -> None:
    template = _string_constants()[name]
    without_placeholders = _FIELD_PLACEHOLDER_RE.sub("", template)
    assert not re.search(r"[0-9]", without_placeholders), (
        f"{name} contains a Latin digit outside a {{placeholder}}: {template!r}"
    )


def test_every_order_state_has_a_status_label() -> None:
    for state in OrderState:
        assert state in copy_fa.STATUS_LABELS
        assert copy_fa.STATUS_LABELS[state].strip() != ""


def test_reject_reasons_shape() -> None:
    assert len(copy_fa.REJECT_REASONS) >= 1
    keys = [key for key, _, _ in copy_fa.REJECT_REASONS]
    assert len(keys) == len(set(keys)), "REJECT_REASONS keys must be unique"
    for key, owner_label, customer_sentence in copy_fa.REJECT_REASONS:
        assert key.strip() != ""
        assert owner_label.strip() != ""
        if key != "custom":
            assert customer_sentence is not None
            assert customer_sentence.strip() != ""


def test_owner_label_and_customer_sentence_are_never_the_same_string() -> None:
    for _, owner_label, customer_sentence in copy_fa.REJECT_REASONS:
        if customer_sentence is not None:
            assert owner_label != customer_sentence
