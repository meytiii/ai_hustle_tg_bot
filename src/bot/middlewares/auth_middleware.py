"""Authentication middleware ensuring only the verified Owner can execute administrative actions."""

from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from src.utils.logger import logger


class OwnerAuthMiddleware(BaseMiddleware):
    """Guards administrative handlers against unauthorized execution."""

    def __init__(self, owner_id: int):
        self.owner_id = owner_id

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if not user or user.id != self.owner_id:
            user_id = user.id if user else "Unknown"
            logger.warning(f"Unauthorized admin action attempt by user ID {user_id}")

            if isinstance(event, CallbackQuery) or (hasattr(event, "answer") and not isinstance(event, Message)):
                try:
                    await event.answer("⚠️ Access denied. You are not authorized to perform this action.", show_alert=True)
                except TypeError:
                    await event.answer("⚠️ Access denied. You are not authorized to perform this action.")
            elif isinstance(event, Message) or hasattr(event, "answer"):
                await event.answer("⚠️ Access denied.")
            return None

        return await handler(event, data)
