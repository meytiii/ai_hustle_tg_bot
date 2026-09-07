"""Middleware that automatically reacts with a salute emoji (🫡) to incoming messages."""

from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import Message, ReactionTypeEmoji, TelegramObject

SALUTE_EMOJI = "🫡"


class ReactionMiddleware(BaseMiddleware):
    """Reacts with a salute emoji whenever a message is received from a user, owner, or admin."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            try:
                await event.react([ReactionTypeEmoji(emoji=SALUTE_EMOJI)])
            except Exception:
                # Silently ignore if reactions are disabled in the user's client or chat
                pass

        return await handler(event, data)
