"""
`send_or_alert()`: the one place every "must reach the customer"
message in this codebase goes through. Its entire reason to exist is
one guarantee, load-bearing everywhere it's called from — the
credential-delivery transaction in particular depends on it: **it
never returns `True` unless Telegram actually accepted the message.**

- A transient failure (`TelegramRetryAfter`, `TelegramNetworkError`, or
  any other `TelegramAPIError`) is retried with backoff, up to
  `max_retries` times (E8: "retry 3x with backoff").
- `TelegramForbiddenError` (the customer blocked the bot) is not
  retried — retrying a block can't succeed — and raises E7 to the
  owner by name, since that's a distinct, actionable fact ("this
  specific customer can't be reached") rather than a generic failure.
- Exhausting every retry raises E8 to the owner instead: order held at
  its current state, never advanced on an unsent message.

Both owner alerts are best-effort (`_alert_owner` swallows its own
send failures rather than raising) — a failure notifying the owner
must never mask the original failure this function is reporting.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup

from ollie.bot import copy_fa

logger = logging.getLogger(__name__)

_BASE_BACKOFF_SECONDS = 1.0


async def send_or_alert(
    bot: Bot,
    chat_id: int,
    text: str,
    *,
    owner_chat_id: int,
    order_code: str | None = None,
    reply_markup: InlineKeyboardMarkup | None = None,
    max_retries: int = 3,
) -> bool:
    last_error: Exception | None = None

    for attempt in range(max_retries):
        try:
            await bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode="HTML")
            return True
        except TelegramForbiddenError as exc:
            logger.warning("send blocked by chat %s: %s", chat_id, exc)
            if order_code is not None:
                await _alert_owner(
                    bot,
                    owner_chat_id,
                    copy_fa.E7_OWNER_BLOCKED_ALERT.format(order_code=order_code),
                )
            return False
        except TelegramRetryAfter as exc:
            last_error = exc
            await asyncio.sleep(exc.retry_after)
        except TelegramNetworkError as exc:
            last_error = exc
            await asyncio.sleep(_BASE_BACKOFF_SECONDS * (2**attempt))
        except Exception as exc:  # noqa: BLE001 - any other TelegramAPIError, treated the same
            last_error = exc
            await asyncio.sleep(_BASE_BACKOFF_SECONDS * (2**attempt))

    logger.error("send to chat %s failed after %d attempts: %s", chat_id, max_retries, last_error)
    if order_code is not None:
        await _alert_owner(
            bot, owner_chat_id, copy_fa.E8_SEND_FAILED_ALERT.format(order_code=order_code)
        )
    return False


async def _alert_owner(bot: Bot, owner_chat_id: int, text: str) -> None:
    try:
        await bot.send_message(owner_chat_id, text, parse_mode="HTML")
    except Exception:  # noqa: BLE001 - a failed alert must never mask the original failure
        logger.exception("failed to alert owner (chat %s)", owner_chat_id)
