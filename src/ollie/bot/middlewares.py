"""
Two cross-cutting concerns, kept as middleware rather than repeated in
every owner handler or every handler generally.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from ollie.bot import copy_fa

logger = logging.getLogger(__name__)


class OwnerOnlyMiddleware(BaseMiddleware):
    """
    Gates the owner router. Per O4's spec note: "A non-owner sending
    /panel gets no response at all — not an error. Don't advertise that
    the door exists." A non-owner update reaching this router is
    silently dropped (the handler is never called) rather than
    answered with any message, error or otherwise.
    """

    def __init__(self, owner_telegram_id: int) -> None:
        self._owner_telegram_id = owner_telegram_id

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None or user.id != self._owner_telegram_id:
            return None
        return await handler(event, data)


class ErrorAlertMiddleware(BaseMiddleware):
    """
    Catches anything a handler raises, logs it, and answers the update
    rather than letting aiogram's own default (silent, or a stack trace
    only an operator sees) reach the user. The spec has no string for
    "an unhandled exception just happened" specifically — E6's "can't
    continue from before, please start over" is the closest honest
    thing to tell someone whose conversation just broke underneath
    them, so that's what this sends, on both the customer and owner
    side alike.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception:
            logger.exception("unhandled error while processing update: %r", event)
            chat = _chat_from_event(event)
            if chat is not None:
                bot = data.get("bot")
                if bot is not None:
                    try:
                        await bot.send_message(chat, copy_fa.E6_STATE_LOST)
                    except Exception:  # noqa: BLE001 - already handling one failure
                        logger.exception("failed to notify chat %s of the error", chat)
            return None


def _chat_from_event(event: TelegramObject) -> int | None:
    """
    Deliberately duck-typed rather than pattern-matched against
    aiogram's exact update shapes: this only needs "is there a chat id
    to reply to somewhere in here", and a test double (a plain
    SimpleNamespace standing in for a Message) should be able to
    answer that too without importing real aiogram types.
    """
    candidates: list[Any] = [event]
    if isinstance(event, Update):
        candidates = [event.message, event.callback_query]

    for candidate in candidates:
        target: Any = getattr(candidate, "message", candidate)
        chat = getattr(target, "chat", None)
        if chat is not None:
            return int(chat.id)
    return None
