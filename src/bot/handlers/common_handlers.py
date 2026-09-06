"""Common and fallback handlers for unhandled messages and errors."""

from aiogram import Router
from aiogram.types import Message
from src.bot.keyboards.buyer_keyboards import get_start_keyboard

router = Router(name="common_router")


@router.message()
async def fallback_unknown_message(message: Message):
    """Graceful fallback for unknown user inputs, directing them to /start."""
    await message.answer(
        "👋 Welcome! To browse or purchase the **AI Side Hustle** guide, please use the button below:",
        parse_mode="Markdown",
        reply_markup=get_start_keyboard(),
    )
