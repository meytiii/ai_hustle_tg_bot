"""Notification service handling bilingual notifications (EN for Buyer/Dev, FA for Owner)."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup
import jdatetime

from src.database.models import Order
from src.utils.logger import logger

# Tehran Timezone configuration (with fallback for systems without tzdata)
try:
    from zoneinfo import ZoneInfo
    TEHRAN_TZ = ZoneInfo("Asia/Tehran")
except Exception:
    TEHRAN_TZ = timezone(timedelta(hours=3, minutes=30))


def escape_md(text: Optional[str]) -> str:
    """Escapes Markdown special characters to prevent broken formatting like italics from underscores."""
    if not text:
        return ""
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text


def format_shamsi_datetime(dt: datetime) -> str:
    """Converts a UTC datetime to a Hijri Shamsi (Jalali) string in Tehran timezone."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    tehran_dt = dt.astimezone(TEHRAN_TZ)
    shamsi_dt = jdatetime.datetime.fromgregorian(datetime=tehran_dt)
    return shamsi_dt.strftime("%Y/%m/%d %H:%M:%S")


class NotificationService:
    """Manages dispatch of messages, cards, and technical alerts across Buyer, Owner, and Developer."""

    def __init__(self, owner_id: int, developer_id: int):
        self.owner_id = owner_id
        self.developer_id = developer_id

    async def notify_owner_new_order(
        self,
        bot: Bot,
        order: Order,
        reply_markup: InlineKeyboardMarkup,
    ) -> Optional[int]:
        """Sends new order submission card in Persian to the Owner."""
        buyer_handle = f"@{escape_md(order.username)}" if order.username else "ندارد"
        buyer_name = escape_md(order.full_name)

        caption = (
            f"🔔 **بررسی پرداخت جدید**\n\n"
            f"📦 **محصول:** AI Side Hustle Launch System\n"
            f"💰 **مبلغ:** ${order.amount_usd:g} (79 USDT)\n"
            f"👤 **خریدار:** {buyer_handle} ({buyer_name})\n"
            f"🆔 **شناسه تلگرام:** `{order.user_id}`\n"
            f"🔗 **هش تراکنش:**\n`{order.tx_hash}`\n\n"
            f"لطفاً تراکنش را در شبکه TON بررسی نمایید:"
        )

        try:
            if order.receipt_file_id:
                msg = await bot.send_photo(
                    chat_id=self.owner_id,
                    photo=order.receipt_file_id,
                    caption=caption,
                    parse_mode="Markdown",
                    reply_markup=reply_markup,
                )
                return getattr(msg, "message_id", None)
            else:
                msg = await bot.send_message(
                    chat_id=self.owner_id,
                    text=caption,
                    parse_mode="Markdown",
                    reply_markup=reply_markup,
                )
                return getattr(msg, "message_id", None)
        except TelegramAPIError as e:
            logger.error(f"Failed to send order review card to Owner ({self.owner_id}): {e}")
            return None

    async def notify_owner_approved(
        self,
        bot: Bot,
        order: Order,
    ) -> None:
        """Sends confirmation in Persian to Owner after successful approval."""
        text = (
            f"✅ **پرداخت برای سفارش `{order.order_number}` تایید شد.**\n\n"
            f"پیام حاوی دکمه دریافت فایل برای خریدار ارسال گردید."
        )
        try:
            await bot.send_message(chat_id=self.owner_id, text=text, parse_mode="Markdown")
        except TelegramAPIError as e:
            logger.warning(f"Could not notify Owner of approval: {e}")

    async def notify_owner_rejected(
        self,
        bot: Bot,
        order: Order,
        reason: str = "",
    ) -> None:
        """Sends rejection confirmation in Persian to Owner."""
        text = (
            f"❌ **پرداخت برای سفارش `{order.order_number}` رد شد.**\n\n"
            f"اطلاعیه عدم تایید پرداخت برای خریدار ارسال گردید."
        )
        try:
            await bot.send_message(chat_id=self.owner_id, text=text, parse_mode="Markdown")
        except TelegramAPIError as e:
            logger.warning(f"Could not notify Owner of rejection: {e}")

    async def notify_developer_completed(self, bot: Bot, order: Order) -> None:
        """Sends completed order report in English to the Developer."""
        buyer_handle = f"@{escape_md(order.username)}" if order.username else "N/A"
        buyer_name = escape_md(order.full_name)
        shamsi_date = format_shamsi_datetime(order.updated_at)

        text = (
            f"📊 **[SALES REPORT: APPROVED]**\n"
            f"• **Order:** `{order.order_number}`\n"
            f"• **Buyer:** {buyer_name} ({buyer_handle})\n"
            f"• **Buyer ID:** `{order.user_id}`\n"
            f"• **Amount:** ${order.amount_usd:g}\n"
            f"• **TX Hash:** `{order.tx_hash}`\n"
            f"• **Status:** APPROVED & DELIVERED\n"
            f"• **Timestamp:** {shamsi_date} (Tehran)"
        )
        try:
            await bot.send_message(chat_id=self.developer_id, text=text, parse_mode="Markdown")
        except TelegramAPIError as e:
            logger.warning(f"Could not send sales report to Developer ({self.developer_id}): {e}")

    async def notify_developer_rejected(self, bot: Bot, order: Order, reason: str) -> None:
        """Sends rejection report in English to the Developer."""
        buyer_handle = f"@{escape_md(order.username)}" if order.username else "N/A"
        buyer_name = escape_md(order.full_name)
        shamsi_date = format_shamsi_datetime(order.updated_at)

        text = (
            f"⚠️ **[SALES REPORT: REJECTED]**\n"
            f"• **Order:** `{order.order_number}`\n"
            f"• **Buyer:** {buyer_name} ({buyer_handle})\n"
            f"• **Buyer ID:** `{order.user_id}`\n"
            f"• **Reason:** {reason}\n"
            f"• **Status:** REJECTED\n"
            f"• **Timestamp:** {shamsi_date} (Tehran)"
        )
        try:
            await bot.send_message(chat_id=self.developer_id, text=text, parse_mode="Markdown")
        except TelegramAPIError as e:
            logger.warning(f"Could not send rejection report to Developer ({self.developer_id}): {e}")

    async def notify_developer_error(self, bot: Bot, context: str, error_details: str) -> None:
        """Sends technical error alert in English to Developer."""
        text = (
            f"🚨 **[SYSTEM EXCEPTION ALERT]**\n"
            f"• **Context:** `{context}`\n"
            f"• **Details:**\n```{error_details[:800]}```"
        )
        try:
            await bot.send_message(chat_id=self.developer_id, text=text, parse_mode="Markdown")
        except TelegramAPIError as e:
            logger.error(f"Failed to dispatch error alert to Developer: {e}")

    async def notify_buyer_approved(
        self,
        bot: Bot,
        user_id: int,
        order_number: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
    ) -> None:
        """Sends Step 9 payment confirmation message with download button to Buyer in English."""
        text = (
            "🎉 **Payment Confirmed!**\n\n"
            "Your payment has been successfully verified.\n"
            "Thank you for your purchase!\n"
            "Your AI Side Hustle Launch System — Visual Pro Edition is ready.\n"
            "📥 Download your product below:\n\n"
            "We hope the system helps you turn your idea into action.\n"
            "🚀 Good luck with your launch!"
        )
        try:
            await bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
        except TelegramAPIError as e:
            logger.warning(f"Failed to deliver approval confirmation to user {user_id}: {e}")

    async def notify_buyer_rejected(
        self,
        bot: Bot,
        user_id: int,
        order_number: str,
        reason: Optional[str] = None,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
    ) -> None:
        """Delivers Step 11 rejection message to Buyer in English."""
        text = (
            "❌ **Payment Could Not Be Confirmed**\n\n"
            "We could not confirm your payment yet.\n"
            "Please check that:\n"
            "• You sent the correct amount\n"
            "• You used the TON Network\n"
            "• You sent the payment to the correct wallet address\n\n"
            "If you believe you completed the payment correctly, please contact support and send your transaction hash."
        )
        try:
            await bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
        except TelegramAPIError as e:
            logger.warning(f"Failed to deliver rejection message to user {user_id}: {e}")

    async def notify_owner_support_message(
        self,
        bot: Bot,
        user_id: int,
        username: Optional[str],
        full_name: str,
        message_text: str,
        reply_markup: InlineKeyboardMarkup,
    ) -> bool:
        """Forwards a user's support inquiry to the Owner in Persian."""
        buyer_handle = f"@{escape_md(username)}" if username else "ندارد"
        buyer_name = escape_md(full_name)
        shamsi_date = format_shamsi_datetime(datetime.now(timezone.utc))

        caption = (
            f"📩 **پیام جدید از بخش پشتیبانی**\n\n"
            f"👤 **کاربر:** {buyer_name} ({buyer_handle})\n"
            f"🆔 **شناسه عددی:** `{user_id}`\n"
            f"📅 **تاریخ:** {shamsi_date}\n\n"
            f"💬 **متن پیام:**\n"
            f"{message_text}\n\n"
            f"جهت پاسخ دادن به این کاربر، دکمه زیر را لمس نمایید:"
        )
        try:
            await bot.send_message(
                chat_id=self.owner_id,
                text=caption,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
            return True
        except TelegramAPIError as e:
            logger.error(f"Failed to forward support message to Owner ({self.owner_id}): {e}")
            return False

    async def notify_user_support_reply(
        self,
        bot: Bot,
        user_id: int,
        reply_text: str,
    ) -> bool:
        """Delivers the Owner's support response back to the user in English."""
        text = (
            f"💬 **Support Team Response:**\n\n"
            f"{reply_text}\n\n"
            f"If you have further questions, you can contact support again at any time."
        )
        try:
            await bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode="Markdown",
            )
            return True
        except TelegramAPIError as e:
            logger.error(f"Failed to deliver support reply to user {user_id}: {e}")
            return False

    async def notify_user_unblocked(
        self,
        bot: Bot,
        user_id: int,
    ) -> bool:
        """Notifies a reinstated user in polite, professional English that their suspension has been lifted."""
        text = (
            f"🛡️ **Account Reinstated**\n\n"
            f"Hello,\n"
            f"Following a comprehensive review of your account and message history by our administration team, "
            f"your account suspension has been officially lifted.\n\n"
            f"Full access to our bot services, product orders, and customer support has been restored. "
            f"If you need any assistance or wish to explore available options, please send /start."
        )
        try:
            await bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode="Markdown",
            )
            return True
        except TelegramAPIError as e:
            logger.error(f"Failed to deliver account reinstatement notification to user {user_id}: {e}")
            return False

