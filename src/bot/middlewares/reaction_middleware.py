"""Middleware that manages emoji reactions to incoming messages."""

from typing import Any, Awaitable, Callable, Dict, Optional
from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReactionTypeEmoji, TelegramObject

from src.bot.states import BuyerOrderStates
from src.services.order_service import OrderService

SALUTE_EMOJI = "🫡"
STOP_EMOJI = "✋"
SOB_EMOJI = "😭"
THUMBS_UP_EMOJI = "👍"


async def react_to_message(message: Message, emoji: str) -> None:
    """Safely adds or updates an emoji reaction on a Telegram message."""
    try:
        await message.react([ReactionTypeEmoji(emoji=emoji)])
    except Exception:
        # Silently ignore if reactions are disabled in the client or chat
        pass


class ReactionMiddleware(BaseMiddleware):
    """Reacts with a salute emoji (🫡) to legitimate commands and messages,

    while deferring to specialized reactions (✋, 😭, 👍) for blocked users,
    proof submission states, or error conditions.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            user = data.get("event_from_user")
            order_service: Optional[OrderService] = data.get("order_service")
            state: Optional[FSMContext] = data.get("state")

            is_blocked = False
            if user and order_service:
                try:
                    is_blocked = await order_service.is_user_blocked(user.id)
                except Exception:
                    is_blocked = False

            is_submitting_proof = False
            if state:
                try:
                    current_state = await state.get_state()
                    if current_state in (
                        BuyerOrderStates.waiting_for_tx_hash.state,
                        BuyerOrderStates.waiting_for_receipt.state,
                    ):
                        is_submitting_proof = True
                except Exception:
                    is_submitting_proof = False

            # Normal commands & messages receive salute 🫡
            if not is_blocked and not is_submitting_proof:
                await react_to_message(event, SALUTE_EMOJI)

        return await handler(event, data)

