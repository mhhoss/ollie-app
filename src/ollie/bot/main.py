"""
Composition root: builds the `Bot`/`Dispatcher`, wires every router and
middleware, connects to SQLite, and starts long polling plus the
sweeper as a background task. Nothing here is business logic — every
handler module is independently the thing that actually does anything,
this file only assembles them.

`conn` and `config` are injected into every handler via aiogram's own
dependency-injection-by-parameter-name mechanism (`dp.start_polling`'s
kwargs become available to any handler that declares a same-named
parameter) — no handler imports a global connection or reaches for a
singleton; every one receives its dependencies explicitly.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from ollie.bot import sweeper
from ollie.bot.handlers import cart, catalog, checkout, history, owner, receipt, start, support
from ollie.bot.middlewares import ErrorAlertMiddleware, OwnerOnlyMiddleware
from ollie.config import Config, ConfigError, load
from ollie.db.conn import connect
from ollie.db.migrate import migrate

logger = logging.getLogger(__name__)


def build_dispatcher(config: Config) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    error_middleware = ErrorAlertMiddleware()
    dp.message.outer_middleware(error_middleware)
    dp.callback_query.outer_middleware(error_middleware)

    owner_gate = OwnerOnlyMiddleware(config.bot.owner_telegram_id)
    owner.router.message.outer_middleware(owner_gate)
    owner.router.callback_query.outer_middleware(owner_gate)

    # Order matters only where two routers could otherwise both match
    # the same update (they don't here — each router's filters are
    # disjoint by construction) but is kept deliberate and readable:
    # entry points first, then the flows they lead into.
    dp.include_router(start.router)
    dp.include_router(catalog.router)
    dp.include_router(cart.router)
    dp.include_router(checkout.router)
    dp.include_router(receipt.router)
    dp.include_router(history.router)
    dp.include_router(support.router)
    dp.include_router(owner.router)

    return dp


async def run(config_path: str) -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    try:
        config = load(config_path)
    except ConfigError as exc:
        logger.error("failed to load config: %s", exc)
        raise SystemExit(1) from exc

    conn = connect(config.runtime.db_path)
    migrate(conn)

    bot = Bot(
        token=config.bot.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher(config)

    sweeper_task = asyncio.create_task(sweeper.run_forever(config, bot))
    try:
        await dp.start_polling(
            bot, conn=conn, config=config, allowed_updates=dp.resolve_used_update_types()
        )
    finally:
        sweeper_task.cancel()
        conn.close()
        await bot.session.close()


def main() -> None:
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.toml"
    asyncio.run(run(config_path))


if __name__ == "__main__":
    main()
