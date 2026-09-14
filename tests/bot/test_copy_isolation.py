"""
The guardrail that keeps the bot's customer-visible surface in one
reviewable file: no Persian character may appear anywhere under
`src/ollie/bot/` except inside `copy_fa.py`. If a handler ever hardcodes
a Persian string instead of importing it from `copy_fa`, this fails the
build instead of silently forking the copy across two places.

Scoped to `src/ollie/bot/` — not the whole `src/ollie/` tree. `ollie.fmt`
and `ollie.domain` legitimately contain a small amount of Persian text
of their own (money.py's "تومان" suffix, digits.py's digit/letter
translation tables, docstring examples) that is formatting *data*, not
customer-facing message copy, and Phase 4's AST isolation test
(`tests/domain/test_no_external_deps.py`) already guarantees neither of
those packages can import from or be imported by the bot layer — so a
real customer-facing string could never end up in one of them without
also breaking that separate, independent test.
"""

from __future__ import annotations

import re
from pathlib import Path

_ARABIC_BLOCK_RE = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")

_BOT_DIR = Path(__file__).resolve().parents[2] / "src" / "ollie" / "bot"


def _bot_python_files() -> list[Path]:
    return sorted(p for p in _BOT_DIR.rglob("*.py") if p.name != "copy_fa.py")


def test_bot_layer_has_python_files_to_check() -> None:
    assert _bot_python_files(), f"expected at least one file under {_BOT_DIR}"


def test_no_persian_text_outside_copy_fa() -> None:
    offenders: list[str] = []
    for path in _bot_python_files():
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _ARABIC_BLOCK_RE.search(line):
                offenders.append(f"{path.relative_to(_BOT_DIR.parents[2])}:{lineno}: {line!r}")

    assert not offenders, "Persian text found outside copy_fa.py — move it there:\n" + "\n".join(
        offenders
    )
