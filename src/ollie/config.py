"""
Store configuration: load, validate, fail loudly.

One TOML file per deployed store (see config.example.toml for the
template and every field's meaning). `load()` is the only entry point
— it either returns a fully valid Config or raises ConfigError naming
the file and the field that's wrong. Nothing downstream re-validates;
by the time a Config object exists, every value in it is trustworthy.

This module is deliberately eager: it must fail at boot, before the
bot binds to Telegram and before the first order — not three weeks
later when a malformed card number reaches a customer.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_TOKEN_RE = re.compile(r"^\d+:[A-Za-z0-9_-]{30,}$")
_CARD_DIGITS_RE = re.compile(r"^\d{16}$")


class ConfigError(Exception):
    """Raised when a config file is missing a field or a field's value is invalid."""


@dataclass(frozen=True, slots=True)
class BotConfig:
    token: str
    owner_telegram_id: int


@dataclass(frozen=True, slots=True)
class StoreConfig:
    name: str
    card_number: str  # normalized: digits only, exactly 16
    card_holder: str
    shipping_cost: int
    default_carrier: str


@dataclass(frozen=True, slots=True)
class OrderConfig:
    payment_window_hours: int
    reject_flag_threshold: int


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    db_path: Path
    proxy_url: str | None  # None means "no proxy", not an empty string downstream


@dataclass(frozen=True, slots=True)
class Config:
    bot: BotConfig
    store: StoreConfig
    order: OrderConfig
    runtime: RuntimeConfig


def load(path: str | Path) -> Config:
    """Load and fully validate a config.toml. Raises ConfigError on any problem."""
    path = Path(path)
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: invalid TOML: {exc}") from exc

    return _config_from_dict(raw, source=path)


def _config_from_dict(raw: dict[str, Any], *, source: Path) -> Config:
    bot = _section(raw, "bot", source=source)
    store = _section(raw, "store", source=source)
    order = _section(raw, "order", source=source)
    runtime = _section(raw, "runtime", source=source)

    return Config(
        bot=_build_bot(bot, source=source),
        store=_build_store(store, source=source),
        order=_build_order(order, source=source),
        runtime=_build_runtime(runtime, source=source),
    )


def _build_bot(data: dict[str, Any], *, source: Path) -> BotConfig:
    token = _require_str(data, "bot.token", source=source)
    if not _TOKEN_RE.match(token):
        raise ConfigError(
            f"{source}: bot.token does not look like a real BotFather token "
            f"(expected '<digits>:<35+ chars>', got {token!r})"
        )

    owner_id = _require_int(data, "bot.owner_telegram_id", source=source)
    if owner_id <= 0:
        raise ConfigError(
            f"{source}: bot.owner_telegram_id must be a positive Telegram user id, "
            f"got {owner_id}. Get it from @userinfobot — it must not be left as 0."
        )

    return BotConfig(token=token, owner_telegram_id=owner_id)


def _build_store(data: dict[str, Any], *, source: Path) -> StoreConfig:
    name = _require_str(data, "store.name", source=source)

    card_raw = _require_str(data, "store.card_number", source=source)
    card_digits = re.sub(r"[\s-]", "", card_raw)
    if not _CARD_DIGITS_RE.match(card_digits):
        raise ConfigError(
            f"{source}: store.card_number must be exactly 16 digits "
            f"(spaces/dashes allowed and stripped), got {card_raw!r}"
        )

    card_holder = _require_str(data, "store.card_holder", source=source)

    shipping_cost = _require_int(data, "store.shipping_cost", source=source)
    if shipping_cost < 0:
        raise ConfigError(f"{source}: store.shipping_cost cannot be negative, got {shipping_cost}")

    default_carrier = _require_str(data, "store.default_carrier", source=source)

    return StoreConfig(
        name=name,
        card_number=card_digits,
        card_holder=card_holder,
        shipping_cost=shipping_cost,
        default_carrier=default_carrier,
    )


def _build_order(data: dict[str, Any], *, source: Path) -> OrderConfig:
    payment_window_hours = _require_int(data, "order.payment_window_hours", source=source)
    if not (1 <= payment_window_hours <= 168):
        raise ConfigError(
            f"{source}: order.payment_window_hours must be between 1 and 168 "
            f"(one week), got {payment_window_hours}"
        )

    reject_flag_threshold = _require_int(data, "order.reject_flag_threshold", source=source)
    if reject_flag_threshold < 1:
        raise ConfigError(
            f"{source}: order.reject_flag_threshold must be at least 1, got {reject_flag_threshold}"
        )

    return OrderConfig(
        payment_window_hours=payment_window_hours,
        reject_flag_threshold=reject_flag_threshold,
    )


def _build_runtime(data: dict[str, Any], *, source: Path) -> RuntimeConfig:
    db_path_raw = _require_str(data, "runtime.db_path", source=source)
    if not db_path_raw.strip():
        raise ConfigError(f"{source}: runtime.db_path cannot be empty")

    proxy_url_raw = data.get("proxy_url", "")
    if not isinstance(proxy_url_raw, str):
        raise ConfigError(
            f"{source}: runtime.proxy_url must be a string, got {type(proxy_url_raw).__name__}"
        )
    proxy_url = proxy_url_raw.strip() or None
    if proxy_url is not None and not re.match(r"^https?://", proxy_url):
        raise ConfigError(
            f"{source}: runtime.proxy_url must start with http:// or https://, got {proxy_url!r}"
        )

    return RuntimeConfig(db_path=Path(db_path_raw), proxy_url=proxy_url)


# ---------------------------------------------------------------------------
# Small helpers: consistent "missing section" / "missing field" errors
# ---------------------------------------------------------------------------
def _section(raw: dict[str, Any], name: str, *, source: Path) -> dict[str, Any]:
    section = raw.get(name)
    if not isinstance(section, dict):
        raise ConfigError(f"{source}: missing required [{name}] section")
    return section


def _require_str(data: dict[str, Any], dotted_key: str, *, source: Path) -> str:
    _, _, field = dotted_key.partition(".")
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{source}: {dotted_key} is required and must be a non-empty string")
    return value.strip()


def _require_int(data: dict[str, Any], dotted_key: str, *, source: Path) -> int:
    _, _, field = dotted_key.partition(".")
    value = data.get(field)
    # bool is an int subclass in Python — reject it explicitly so a stray
    # `true`/`false` in the TOML doesn't silently become 1/0.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{source}: {dotted_key} is required and must be an integer")
    return value
