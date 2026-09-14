from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter

from ollie.bot import copy_fa
from ollie.bot.send import send_or_alert

OWNER_ID = 1
CUSTOMER_ID = 500
ORDER_CODE = "A7K2M9"


class _Method:
    """Stand-in for aiogram's TelegramMethod, which the exception
    classes require but never inspect meaningfully in these tests."""


def _method() -> Any:
    return _Method()


@pytest.mark.asyncio
async def test_successful_send_returns_true_and_sends_once() -> None:
    bot = AsyncMock()
    result = await send_or_alert(bot, CUSTOMER_ID, "hello", owner_chat_id=OWNER_ID)
    assert result is True
    assert bot.send_message.call_count == 1


@pytest.mark.asyncio
async def test_blocked_customer_returns_false_without_retry_and_alerts_owner() -> None:
    bot = AsyncMock()
    bot.send_message.side_effect = [
        TelegramForbiddenError(_method(), "bot was blocked by the user"),
        None,  # the owner alert itself
    ]

    result = await send_or_alert(
        bot, CUSTOMER_ID, "hello", owner_chat_id=OWNER_ID, order_code=ORDER_CODE
    )

    assert result is False
    assert bot.send_message.call_count == 2  # one failed attempt, one owner alert — no retry
    owner_call = bot.send_message.call_args_list[1]
    assert owner_call.args[0] == OWNER_ID
    assert ORDER_CODE in owner_call.args[1]


@pytest.mark.asyncio
async def test_transient_network_error_is_retried_then_succeeds() -> None:
    bot = AsyncMock()
    bot.send_message.side_effect = [
        TelegramNetworkError(_method(), "connection reset"),
        None,  # succeeds on the second attempt
    ]

    result = await send_or_alert(bot, CUSTOMER_ID, "hello", owner_chat_id=OWNER_ID)

    assert result is True
    assert bot.send_message.call_count == 2


@pytest.mark.asyncio
async def test_exhausting_all_retries_returns_false_and_alerts_owner_with_e8() -> None:
    bot = AsyncMock()
    bot.send_message.side_effect = [
        TelegramNetworkError(_method(), "down"),
        TelegramNetworkError(_method(), "down"),
        TelegramNetworkError(_method(), "down"),
        None,  # the owner alert
    ]

    result = await send_or_alert(
        bot, CUSTOMER_ID, "hello", owner_chat_id=OWNER_ID, order_code=ORDER_CODE, max_retries=3
    )

    assert result is False
    assert bot.send_message.call_count == 4
    owner_call = bot.send_message.call_args_list[-1]
    assert owner_call.args[0] == OWNER_ID
    assert copy_fa.E8_SEND_FAILED_ALERT.split("{")[0] in owner_call.args[1]


@pytest.mark.asyncio
async def test_never_returns_true_without_an_actual_successful_send() -> None:
    """The one property everything else depends on."""
    bot = AsyncMock()
    bot.send_message.side_effect = TelegramNetworkError(_method(), "always down")

    result = await send_or_alert(bot, CUSTOMER_ID, "hello", owner_chat_id=OWNER_ID, max_retries=2)

    assert result is False


@pytest.mark.asyncio
async def test_retry_after_is_honored_before_retrying(monkeypatch: Any) -> None:
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr("ollie.bot.send.asyncio.sleep", fake_sleep)

    bot = AsyncMock()
    bot.send_message.side_effect = [
        TelegramRetryAfter(_method(), "flood control", retry_after=7),
        None,
    ]

    result = await send_or_alert(bot, CUSTOMER_ID, "hello", owner_chat_id=OWNER_ID)

    assert result is True
    assert 7 in slept


@pytest.mark.asyncio
async def test_owner_alert_failure_does_not_raise() -> None:
    """A failed owner alert must never mask the original send failure."""
    bot = AsyncMock()
    bot.send_message.side_effect = [
        TelegramForbiddenError(_method(), "blocked"),
        RuntimeError("owner alert also failed"),
    ]

    result = await send_or_alert(
        bot, CUSTOMER_ID, "hello", owner_chat_id=OWNER_ID, order_code=ORDER_CODE
    )

    assert result is False
