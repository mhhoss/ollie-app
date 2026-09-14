from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ollie.bot import copy_fa
from ollie.bot.middlewares import ErrorAlertMiddleware, OwnerOnlyMiddleware

OWNER_ID = 1
STRANGER_ID = 999


@pytest.mark.asyncio
async def test_owner_gate_calls_handler_for_the_owner() -> None:
    middleware = OwnerOnlyMiddleware(owner_telegram_id=OWNER_ID)
    handler = AsyncMock(return_value="handled")
    event = SimpleNamespace()
    data = {"event_from_user": SimpleNamespace(id=OWNER_ID)}

    result = await middleware(handler, event, data)  # type: ignore[arg-type]

    assert result == "handled"
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_owner_gate_silently_drops_a_stranger() -> None:
    middleware = OwnerOnlyMiddleware(owner_telegram_id=OWNER_ID)
    handler = AsyncMock(return_value="handled")
    event = SimpleNamespace()
    data = {"event_from_user": SimpleNamespace(id=STRANGER_ID)}

    result = await middleware(handler, event, data)  # type: ignore[arg-type]

    assert result is None
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_owner_gate_drops_when_no_user_is_present() -> None:
    middleware = OwnerOnlyMiddleware(owner_telegram_id=OWNER_ID)
    handler = AsyncMock()
    result = await middleware(handler, SimpleNamespace(), {"event_from_user": None})  # type: ignore[arg-type]
    assert result is None
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_error_middleware_lets_a_clean_call_through() -> None:
    middleware = ErrorAlertMiddleware()
    handler = AsyncMock(return_value="ok")
    result = await middleware(handler, SimpleNamespace(), {})  # type: ignore[arg-type]
    assert result == "ok"


@pytest.mark.asyncio
async def test_error_middleware_catches_exception_and_notifies_the_chat() -> None:
    middleware = ErrorAlertMiddleware()

    async def boom(event: object, data: dict[str, object]) -> None:
        raise RuntimeError("handler exploded")

    bot = AsyncMock()
    message = SimpleNamespace(chat=SimpleNamespace(id=42))
    data = {"bot": bot}

    result = await middleware(boom, message, data)  # type: ignore[arg-type]

    assert result is None
    bot.send_message.assert_awaited_once_with(42, copy_fa.E6_STATE_LOST)


@pytest.mark.asyncio
async def test_error_middleware_swallows_a_failed_notification_too() -> None:
    middleware = ErrorAlertMiddleware()

    async def boom(event: object, data: dict[str, object]) -> None:
        raise RuntimeError("handler exploded")

    bot = AsyncMock()
    bot.send_message.side_effect = RuntimeError("can't even notify")
    message = SimpleNamespace(chat=SimpleNamespace(id=42))

    result = await middleware(boom, message, {"bot": bot})  # type: ignore[arg-type]  # must not raise
    assert result is None
