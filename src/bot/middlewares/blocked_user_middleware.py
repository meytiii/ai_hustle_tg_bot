"""Middleware checking if a buyer has been blocked by the administrator."""

from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from src.services.order_service import OrderService


class BlockedUserMiddleware(BaseMiddleware):
    """Halts interaction if the user is present in the blocked_users table."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        order_service: OrderService = data.get("order_service")

        if user and order_service:
            if await order_service.is_user_blocked(user.id):
                if isinstance(event, CallbackQuery):
                    await event.answer("⚠️ Your account has been suspended.", show_alert=True)
                elif isinstance(event, Message):
                    await event.answer("⚠️ Your account has been suspended.")
                return None

        return await handler(event, data)
