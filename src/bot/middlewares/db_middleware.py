"""Database session and dependency injection middleware for aiogram 3."""

from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from src.config import Settings
from src.database.session import get_session
from src.services.delivery_service import DeliveryService
from src.services.notification_service import NotificationService
from src.services.order_service import OrderService


class DatabaseSessionMiddleware(BaseMiddleware):
    """Injects database session, settings, and domain services into each update handler."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.notification_service = NotificationService(
            owner_id=settings.owner_id,
            developer_id=settings.developer_id,
        )

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        async with get_session(self.settings.database_url) as session:
            data["session"] = session
            data["order_service"] = OrderService(session)
            data["delivery_service"] = DeliveryService(session, self.settings.pdf_file_path)
            data["notification_service"] = self.notification_service
            data["settings"] = self.settings
            return await handler(event, data)
