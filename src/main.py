"""Application entrypoint launching the Telegram bot with long-polling."""

import asyncio
import os
import sys

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties

from src.bot.dispatcher import setup_dispatcher
from src.config import Settings, get_settings
from src.database.session import close_db, init_db
from src.utils.logger import logger


async def main() -> None:
    """Initializes and runs the bot service."""
    # Check if .env file exists, otherwise warn
    if not os.path.exists(".env"):
        logger.warning("No .env file found. Attempting to load configuration from environment variables.")

    try:
        settings = get_settings()
    except Exception as e:
        logger.critical(f"Configuration error: {e}")
        logger.critical("Please ensure BOT_TOKEN and TON_WALLET_ADDRESS are properly configured in .env or environment.")
        sys.exit(1)

    logger.info("Initializing database...")
    await init_db(settings.database_url)

    logger.info("Configuring Telegram bot...")
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode="Markdown"),
    )

    dp = setup_dispatcher(settings)

    logger.info("Bot starting in Long Polling mode (drop_pending_updates=True)...")
    try:
        await dp.start_polling(bot, drop_pending_updates=True)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutdown signal received.")
    finally:
        logger.info("Closing bot session and database connections...")
        await bot.session.close()
        await close_db()
        logger.info("Clean shutdown completed.")


if __name__ == "__main__":
    asyncio.run(main())
