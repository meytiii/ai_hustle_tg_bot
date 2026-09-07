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
        """Sends new order submission card in Persian (FA) to the Owner with the attached receipt screenshot."""
        buyer_handle = f"@{escape_md(order.username)}" if order.username else "ندارد"
        buyer_name = escape_md(order.full_name)
        shamsi_date = format_shamsi_datetime(order.created_at)

        caption = (
            f"🔔 **سفارش جدید جهت بررسی و تایید**\n\n"
            f"🏷️ **شماره سفارش:** `{order.order_number}`\n"
            f"👤 **خریدار:** {buyer_name} ({buyer_handle})\n"
            f"🆔 **شناسه تلگرام خریدار:** `{order.user_id}`\n\n"
            f"💰 **مبلغ سفارش:** ${order.amount_usd:g}\n"
            f"🔗 **هش تراکنش:**\n`{order.tx_hash}`\n\n"
            f"📅 **تاریخ ثبت:** {shamsi_date}\n"
            f"📌 **وضعیت:** در انتظار تایید\n\n"
            f"لطفاً ولت خود را بررسی نموده و تصمیم خود را ثبت نمایید:"
        )

        try:
            if order.receipt_file_id:
                # Receipt can be sent as photo
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
            f"✅ **سفارش `{order.order_number}` با موفقیت تایید شد.**\n\n"
            f"فایل کتاب **AI Side Hustle** مستقیماً برای خریدار ارسال گردید."
        )
        try:
            await bot.send_message(chat_id=self.owner_id, text=text, parse_mode="Markdown")
        except TelegramAPIError as e:
            logger.warning(f"Could not notify Owner of approval: {e}")

    async def notify_owner_rejected(
        self,
        bot: Bot,
        order: Order,
        reason: str,
    ) -> None:
        """Sends rejection confirmation in Persian to Owner."""
        text = (
            f"❌ **سفارش `{order.order_number}` رد شد.**\n\n"
            f"علت رد سفارش:\n_{reason}_\n\n"
            f"پیام متناسب به زبان انگلیسی برای خریدار ارسال گردید."
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

    async def notify_buyer_rejected(
        self,
        bot: Bot,
        user_id: int,
        order_number: str,
        reason: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
    ) -> None:
        """Delivers rejection explanation to Buyer in English."""
        text = (
            f"❌ **Your order #{order_number} could not be approved.**\n\n"
            f"**Reason provided:**\n{reason}\n\n"
            f"If you believe this was an error or would like to submit a corrected payment, "
            f"you may start a new order below."
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
