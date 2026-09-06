"""Digital product delivery engine with Telegram file_id caching."""

import os
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import FSInputFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import BotCache, utc_now
from src.utils.logger import logger

PDF_CACHE_KEY = "cached_pdf_file_id"


class DeliveryError(Exception):
    """Base error for delivery failures."""
    pass


class BuyerBlockedBotError(DeliveryError):
    """Raised when the user has blocked or deleted the bot."""
    pass


class DeliveryService:
    """Delivers the PDF digital product using cached Telegram file_ids to eliminate bandwidth overhead."""

    def __init__(self, session: AsyncSession, pdf_path: str):
        self.session = session
        self.pdf_path = pdf_path

    async def get_cached_file_id(self) -> Optional[str]:
        """Retrieves the cached Telegram file_id from the database."""
        stmt = select(BotCache).where(BotCache.key == PDF_CACHE_KEY)
        result = await self.session.execute(stmt)
        record = result.scalars().first()
        return record.value if record else None

    async def set_cached_file_id(self, file_id: str) -> None:
        """Stores or updates the cached Telegram file_id in the database."""
        stmt = select(BotCache).where(BotCache.key == PDF_CACHE_KEY)
        result = await self.session.execute(stmt)
        record = result.scalars().first()
        if record:
            record.value = file_id
            record.updated_at = utc_now()
        else:
            record = BotCache(key=PDF_CACHE_KEY, value=file_id, updated_at=utc_now())
            self.session.add(record)
        await self.session.flush()
        logger.info(f"Cached PDF file_id updated: {file_id[:16]}...")

    async def deliver_pdf(self, bot: Bot, user_id: int, order_number: str) -> str:
        """Delivers the 'AI Side Hustle' PDF guide to the buyer.

        Returns the file_id used for delivery.
        """
        caption = (
            f"🎉 **Congratulations! Your order #{order_number} has been approved!**\n\n"
            f"Here is your complete guide: **AI Side Hustle**.\n\n"
            f"Thank you for your purchase and we wish you tremendous success on your journey!"
        )

        cached_file_id = await self.get_cached_file_id()

        # Attempt 1: Deliver using cached file_id (0 MB server bandwidth)
        if cached_file_id:
            try:
                sent_msg = await bot.send_document(
                    chat_id=user_id,
                    document=cached_file_id,
                    caption=caption,
                    parse_mode="Markdown",
                )
                logger.info(f"Delivered PDF to user {user_id} using cached file_id for order {order_number}.")
                return cached_file_id
            except TelegramForbiddenError:
                logger.error(f"Cannot deliver PDF to user {user_id}: User has blocked the bot.")
                raise BuyerBlockedBotError("User has blocked the bot.")
            except TelegramBadRequest as e:
                logger.warning(f"Cached file_id delivery failed ({e}). Falling back to local file upload.")

        # Attempt 2: Deliver using local file and update cache
        if not os.path.exists(self.pdf_path):
            raise DeliveryError(f"PDF asset not found at path: {self.pdf_path}")

        try:
            document_file = FSInputFile(self.pdf_path, filename="AI_Side_Hustle.pdf")
            sent_msg = await bot.send_document(
                chat_id=user_id,
                document=document_file,
                caption=caption,
                parse_mode="Markdown",
            )
            new_file_id = str(sent_msg.document.file_id)
            await self.set_cached_file_id(new_file_id)
            logger.info(f"Uploaded and delivered local PDF to user {user_id}. Cached new file_id.")
            return new_file_id
        except TelegramForbiddenError:
            logger.error(f"Cannot deliver PDF to user {user_id}: User has blocked the bot.")
            raise BuyerBlockedBotError("User has blocked the bot.")
        except Exception as e:
            logger.error(f"Failed to deliver PDF to user {user_id}: {e}")
            raise DeliveryError(f"Telegram file delivery failed: {e}")
