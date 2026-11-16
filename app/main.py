"""Application entrypoint: initialize components and start polling."""

import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from app.config import settings
from app.db import init_db
from app.handlers import admin, link, start
from app.logging_setup import setup_logging
from app.services.autopromo import run_autopromo_scheduler

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

    # Optional proxy or custom Telegram Bot API server
    session = AiohttpSession(proxy=settings.proxy) if settings.proxy else None
    server = (
        TelegramAPIServer.from_base(settings.custom_bot_api_url)
        if settings.custom_bot_api_url
        else TelegramAPIServer.from_base("https://api.telegram.org")
    )

    # Bot & Dispatcher setup with in-memory FSM storage
    bot = Bot(
        token=settings.bot_token,
        session=session,
        server=server,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Register handlers
    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(link.router)

    try:
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Botni ishga tushirish"),
                BotCommand(command="taklif", description="Do'stlarni taklif qilish"),
                BotCommand(command="top", description="TOP taklifchilar"),
                BotCommand(command="help", description="Yordam"),
            ]
        )
    except Exception as e:  # noqa: BLE001 - commands menu is optional
        logger.warning("Could not set bot commands: %s", e)

    logger.info("Bot configured successfully. Starting polling...")
    promo_task = asyncio.create_task(run_autopromo_scheduler(bot, settings.db_path))
    try:
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query", "chat_join_request", "chat_member"],
        )
    finally:
        promo_task.cancel()
        await asyncio.gather(promo_task, return_exceptions=True)
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
