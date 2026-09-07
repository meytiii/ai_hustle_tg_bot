"""Common and fallback handlers for unhandled messages and errors."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from src.bot.keyboards.buyer_keyboards import get_start_keyboard
from src.config import Settings

router = Router(name="common_router")


@router.message(Command("help"))
@router.message(F.text.casefold() == "help")
async def handle_help(message: Message, settings: Settings):
    """Provides role-segregated help information for Owner/Dev vs Normal buyers."""
    user = message.from_user
    is_admin = user and user.id in (settings.owner_id, settings.developer_id)

    if is_admin:
        admin_help_text = (
            f"🛠️ **پنل مدیریت**\n\n"
            f"• **/blocklist** — مشاهده لیست کاربران مسدودشده و امکان رفع مسدودیت هر کاربر\n"
            f"• **/history** — مشاهده تاریخچه کامل تمام سفارشات ثبت شده\n"
            f"• **/start** — اجرای مجدد و مشاهده منوی اصلی ربات\n"
            f"• **/help** — نمایش این راهنمای اختصاصی"
        )
        await message.answer(text=admin_help_text, parse_mode="Markdown")
    else:
        buyer_help_text = (
            f"💡 **AI Side Hustle — Available Commands**\n\n"
            f"Here are the commands you can use:\n\n"
            f"• **/buy** — Start the purchase process for the AI Side Hustle guide ($79).\n"
            f"• **/info** — View product details, outline, and current launch pricing.\n"
            f"• **/contact** — Contact customer support directly with any questions.\n"
            f"• **/start** — Display the main welcome menu.\n"
            f"• **/help** — Show this help message."
        )
        await message.answer(
            text=buyer_help_text,
            parse_mode="Markdown",
            reply_markup=get_start_keyboard(),
        )


@router.message()
async def fallback_unknown_message(message: Message):
    """Graceful fallback for unknown user inputs, directing them to /start."""
    await message.answer(
        "👋 Welcome! To browse or purchase the **AI Side Hustle** guide, please use the button below:",
        parse_mode="Markdown",
        reply_markup=get_start_keyboard(),
    )

