from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from ollie.config import BotConfig, Config, OrderConfig, RuntimeConfig, StoreConfig
from ollie.db.conn import connect
from ollie.db.migrate import migrate

OWNER_TELEGRAM_ID = 1


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(tmp_path / "ollie-test.db")
    migrate(connection)
    yield connection
    connection.close()


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(
        bot=BotConfig(
            token="123456:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", owner_telegram_id=OWNER_TELEGRAM_ID
        ),
        store=StoreConfig(
            name="فروشگاه تست",
            card_number="6037997512345678",
            card_holder="مریم رضایی",
            shipping_cost=30_000,
            default_carrier="پست پیشتاز",
        ),
        order=OrderConfig(payment_window_hours=24, reject_flag_threshold=3),
        runtime=RuntimeConfig(db_path=tmp_path / "ollie-test.db", proxy_url=None),
    )


class FakeBot:
    """A minimal stand-in for aiogram.Bot: records every send_message
    call instead of hitting the network, so tests can assert on what
    would have been sent without any real Telegram interaction."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs: object) -> None:
        self.sent.append((chat_id, text))


@pytest.fixture
def fake_bot() -> FakeBot:
    return FakeBot()


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """send_or_alert's backoff sleeps for real seconds by design (it's
    the actual retry delay production needs) — tests that don't care
    about the exact delay shouldn't have to wait on it. A test that
    does care (test_retry_after_is_honored_before_retrying) overrides
    this again with its own monkeypatch, which wins."""

    async def fast_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr("ollie.bot.send.asyncio.sleep", fast_sleep)
