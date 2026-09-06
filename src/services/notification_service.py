"""Notification service handling bilingual notifications (EN for Buyer/Dev, FA for Owner)."""

from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup

from src.database.models import Order
from src.utils.logger import logger


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
        buyer_handle = f"@{order.username}" if order.username else "ندارد"
        created_str = order.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")

        caption = (
            f"🔔 **سفارش جدید جهت بررسی و تایید**\n\n"
            f"🏷️ **شماره سفارش:** `{order.order_number}`\n"
            f"👤 **خریدار:** {order.full_name} ({buyer_handle})\n"
            f"🆔 **شناسه تلگرام خریدار:** `{order.user_id}`\n\n"
            f"💰 **مبلغ سفارش:** {order.amount_ton} TON (${order.amount_usd})\n"
            f"🔗 **هش تراکنش:**\n`{order.tx_hash}`\n\n"
            f"📅 **تاریخ ثبت:** {created_str}\n"
            f"📌 **وضعیت:** در انتظار تایید مالک\n\n"
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
        buyer_handle = f"@{order.username}" if order.username else "N/A"
        text = (
            f"📊 **[SALES REPORT: APPROVED]**\n"
            f"• **Order:** `{order.order_number}`\n"
            f"• **Buyer:** {order.full_name} ({buyer_handle})\n"
            f"• **Buyer ID:** `{order.user_id}`\n"
            f"• **Amount:** {order.amount_ton} TON (${order.amount_usd})\n"
            f"• **TX Hash:** `{order.tx_hash}`\n"
            f"• **Status:** APPROVED & DELIVERED\n"
            f"• **Timestamp:** {order.updated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
        try:
            await bot.send_message(chat_id=self.developer_id, text=text, parse_mode="Markdown")
        except TelegramAPIError as e:
            logger.warning(f"Could not send sales report to Developer ({self.developer_id}): {e}")

    async def notify_developer_rejected(self, bot: Bot, order: Order, reason: str) -> None:
        """Sends rejection report in English to the Developer."""
        buyer_handle = f"@{order.username}" if order.username else "N/A"
        text = (
            f"⚠️ **[SALES REPORT: REJECTED]**\n"
            f"• **Order:** `{order.order_number}`\n"
            f"• **Buyer:** {order.full_name} ({buyer_handle})\n"
            f"• **Buyer ID:** `{order.user_id}`\n"
            f"• **Reason:** {reason}\n"
            f"• **Status:** REJECTED\n"
            f"• **Timestamp:** {order.updated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}"
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
