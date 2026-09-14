"""
One constant per spec screen, no exceptions: every C1–C15, O1–O6, and
E1–E9 id from docs/m1-spec.html must have at least one module-level
name in copy_fa.py prefixed with it. A screen with no copy constant is
a screen nobody built yet, and this fails loudly instead of a customer
finding the gap first.
"""

from __future__ import annotations

import pytest

from ollie.bot import copy_fa

_SPEC_IDS = (
    [f"C{n}" for n in range(1, 16)]
    + [f"O{n}" for n in range(1, 7)]
    + [f"E{n}" for n in range(1, 10)]
)


@pytest.mark.parametrize("spec_id", _SPEC_IDS)
def test_spec_id_has_a_copy_constant(spec_id: str) -> None:
    matches = [name for name in vars(copy_fa) if name.startswith(f"{spec_id}_")]
    assert matches, f"no copy_fa constant found for spec screen {spec_id}"


def test_all_thirty_spec_ids_are_covered() -> None:
    assert len(_SPEC_IDS) == 30
