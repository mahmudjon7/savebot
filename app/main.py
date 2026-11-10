"""Application entrypoint: initialize components and start polling."""

import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import settings
from app.db import init_db
from app.handlers import admin, link, start
from app.logging_setup import setup_logging

logger = logging.getLogger("clipgrab.main")


async def main() -> None:
    """Initialize database, register routers, and run polling loop."""
    setup_logging(settings.log_level)
    logger.info("Starting ClipGrab Bot...")

    if not settings.bot_token:
        logger.critical("BOT_TOKEN is not configured! Please check your environment or .env file.")
        sys.exit(1)

    # Initialize SQLite database
    logger.info("Initializing database at: %s", settings.db_path)
    await init_db(settings.db_path)

    # Bot & Dispatcher setup with in-memory FSM storage
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Register handlers
    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(link.router)

    logger.info("Bot configured successfully. Starting polling...")
    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
