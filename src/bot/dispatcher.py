"""Dispatcher and router configuration."""

import traceback
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from src.bot.handlers import buyer_handlers, common_handlers, owner_handlers
from src.bot.middlewares.auth_middleware import OwnerAuthMiddleware
from src.bot.middlewares.blocked_user_middleware import BlockedUserMiddleware
from src.bot.middlewares.db_middleware import DatabaseSessionMiddleware
from src.bot.middlewares.reaction_middleware import ReactionMiddleware
from src.config import Settings
from src.services.notification_service import NotificationService
from src.utils.logger import logger


def setup_dispatcher(settings: Settings) -> Dispatcher:
    """Configures the aiogram Dispatcher with routers, middlewares, and error boundaries."""
    # Lightweight memory storage for FSM (minimal RAM consumption on free tier)
    dp = Dispatcher(storage=MemoryStorage())

    # 1. Automatically react with salute emoji (🫡) to all incoming messages
    dp.message.outer_middleware(ReactionMiddleware())

    # 2. Register Database & Service Dependency Injection as outer middleware
    dp.update.outer_middleware(DatabaseSessionMiddleware(settings))

    # 3. Register Owner Authorization Guard on owner router
    owner_handlers.router.message.middleware(OwnerAuthMiddleware(settings.owner_id))
    owner_handlers.router.callback_query.middleware(OwnerAuthMiddleware(settings.owner_id))

    # 4. Register Blocked User guard on buyer and common routers
    buyer_handlers.router.message.middleware(BlockedUserMiddleware())
    buyer_handlers.router.callback_query.middleware(BlockedUserMiddleware())
    common_handlers.router.message.middleware(BlockedUserMiddleware())

    # 5. Register Routers (order matters: specific handlers before common fallback)
    dp.include_router(buyer_handlers.router)
    dp.include_router(owner_handlers.router)
    dp.include_router(common_handlers.router)

    # 4. Global Unhandled Error Boundary
    notification_service = NotificationService(
        owner_id=settings.owner_id,
        developer_id=settings.developer_id,
    )

    @dp.error()
    async def global_error_handler(event: ErrorEvent, bot: Bot):
        exc = event.exception
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        logger.critical(f"Unhandled bot exception: {exc}\n{tb}")

        context = "Global Dispatcher Exception"
        if event.update.message:
            context = f"Message from user {event.update.message.from_user.id}: {event.update.message.text}"
        elif event.update.callback_query:
            context = f"Callback from user {event.update.callback_query.from_user.id}: {event.update.callback_query.data}"

        # Alert Developer
        await notification_service.notify_developer_error(bot, context=context, error_details=tb)

    return dp
