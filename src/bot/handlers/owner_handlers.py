"""Owner administrative handlers (100% Persian / Farsi interface)."""

import math
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards.buyer_keyboards import (
    get_download_pdf_keyboard,
    get_rejection_keyboard,
    get_retry_keyboard,
)
from src.bot.keyboards.owner_keyboards import (
    REJECTION_PRESET_EXPLANATIONS_EN,
    get_blocklist_keyboard,
    get_history_pagination_keyboard,
    get_owner_cancel_reply_keyboard,
    get_owner_reject_presets_keyboard,
    get_owner_review_keyboard,
)
from src.bot.states import OwnerReviewStates, OwnerSupportStates
from src.database.models import Order, OrderStatus
from src.services.delivery_service import BuyerBlockedBotError, DeliveryError, DeliveryService
from src.services.notification_service import NotificationService, escape_md, format_shamsi_datetime
from src.services.order_service import OrderService, OrderStateError
from src.utils.logger import logger

router = Router(name="owner_router")


@router.callback_query(F.data.startswith("owner_approve:"))
async def cb_owner_approve(
    callback: CallbackQuery,
    order_service: OrderService,
    notification_service: NotificationService,
    bot: Bot,
):
    """Handles order approval, sends Step 9 confirmation with download button to Buyer, updates Owner."""
    order_number = callback.data.split(":")[1]
    order = await order_service.get_order_by_number(order_number)

    if not order:
        await callback.answer("سفارش یافت نشد.", show_alert=True)
        return

    # Idempotency check: if already approved/delivered, avoid duplicate processing
    if order.status in [OrderStatus.APPROVED.value, OrderStatus.DELIVERED.value]:
        await callback.answer("این سفارش قبلاً تایید شده است.", show_alert=True)
        return

    if order.status != OrderStatus.UNDER_REVIEW.value:
        await callback.answer(f"وضعیت سفارش نامعتبر است: {order.status}", show_alert=True)
        return

    await callback.answer("در حال ثبت تایید پرداخت...")

    # 1. Transition state to APPROVED
    try:
        order = await order_service.approve_order(order_number)
    except OrderStateError as e:
        await callback.message.answer(f"خطا در تغییر وضعیت سفارش: {e}")
        return

    # 2. Update Owner UI (Persian)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"✅ **پرداخت برای سفارش `#{order.order_number}` تایید شد.**\n\n"
        f"پیام حاوی دکمه دریافت فایل کتاب به تلگرام خریدار ارسال گردید.",
        parse_mode="Markdown",
    )

    # 3. Deliver Step 9 confirmation message with download button to Buyer in English
    download_markup = get_download_pdf_keyboard(order.order_number)
    await notification_service.notify_buyer_approved(
        bot=bot,
        user_id=order.user_id,
        order_number=order.order_number,
        reply_markup=download_markup,
    )

    # 4. Notify Developer (English)
    await notification_service.notify_developer_completed(bot, order)


@router.callback_query(F.data.startswith("owner_reject:"))
async def cb_owner_reject(
    callback: CallbackQuery,
    order_service: OrderService,
    notification_service: NotificationService,
    bot: Bot,
):
    """Handles direct one-click rejection in Persian interface, notifies buyer with Step 11 in English."""
    order_number = callback.data.split(":")[1]
    order = await order_service.get_order_by_number(order_number)

    if not order:
        await callback.answer("سفارش یافت نشد.", show_alert=True)
        return

    if order.status != OrderStatus.UNDER_REVIEW.value:
        await callback.answer("این سفارش در وضعیت بررسی قرار ندارد.", show_alert=True)
        return

    reason = "Payment could not be confirmed on TON network."
    order = await order_service.reject_order(order_number, reason)

    # Remove buttons from original card
    await callback.message.edit_reply_markup(reply_markup=None)

    # Confirm to Owner in Persian
    await callback.message.answer(
        f"❌ **پرداخت برای سفارش `#{order.order_number}` رد شد.**\n\n"
        f"اطلاعیه عدم تایید همراه با دکمه‌های پشتیبانی و تلاش مجدد برای خریدار ارسال گردید.",
        parse_mode="Markdown",
    )

    # Notify Buyer in English (Step 11 with Contact Support & Try Again)
    rejection_markup = get_rejection_keyboard()
    await notification_service.notify_buyer_rejected(
        bot=bot,
        user_id=order.user_id,
        order_number=order.order_number,
        reason=reason,
        reply_markup=rejection_markup,
    )

    # Notify Developer in English
    await notification_service.notify_developer_rejected(bot, order, reason)


@router.callback_query(F.data.startswith("owner_reject_menu:"))
async def cb_owner_reject_menu(callback: CallbackQuery):
    """Displays preset rejection reasons to the Owner."""
    order_number = callback.data.split(":")[1]
    await callback.answer()
    await callback.message.edit_reply_markup(
        reply_markup=get_owner_reject_presets_keyboard(order_number)
    )


@router.callback_query(F.data.startswith("reject_back:"))
async def cb_reject_back(callback: CallbackQuery):
    """Returns to the primary approve/reject review buttons."""
    order_number = callback.data.split(":")[1]
    await callback.answer()
    await callback.message.edit_reply_markup(
        reply_markup=get_owner_review_keyboard(order_number)
    )


@router.callback_query(F.data.startswith("reject_preset:"))
async def cb_reject_preset(
    callback: CallbackQuery,
    order_service: OrderService,
    notification_service: NotificationService,
    bot: Bot,
):
    """Applies a preset rejection reason, notifies the buyer in English and developer."""
    parts = callback.data.split(":")
    order_number = parts[1]
    preset_key = parts[2]

    reason_en = REJECTION_PRESET_EXPLANATIONS_EN.get(
        preset_key, "Payment verification could not be completed."
    )

    order = await order_service.get_order_by_number(order_number)
    if not order:
        await callback.answer("سفارش یافت نشد.", show_alert=True)
        return

    if order.status != OrderStatus.UNDER_REVIEW.value:
        await callback.answer("این سفارش در وضعیت بررسی قرار ندارد.", show_alert=True)
        return

    await callback.answer("سفارش رد شد.")
    order = await order_service.reject_order(order_number, reason_en)

    # Remove buttons from original card
    await callback.message.edit_reply_markup(reply_markup=None)

    # Notify Owner in Persian
    await callback.message.answer(
        f"❌ **سفارش `#{order.order_number}` رد شد.**\n\n"
        f"علت ارسال‌شده به خریدار:\n_{reason_en}_",
        parse_mode="Markdown",
    )

    # Notify Buyer in English
    await notification_service.notify_buyer_rejected(
        bot,
        user_id=order.user_id,
        order_number=order.order_number,
        reason=reason_en,
        reply_markup=get_retry_keyboard(),
    )

    # Notify Developer in English
    await notification_service.notify_developer_rejected(bot, order, reason_en)


@router.callback_query(F.data.startswith("reject_custom:"))
async def cb_reject_custom(callback: CallbackQuery, state: FSMContext):
    """Prompts the Owner to enter a custom rejection explanation."""
    order_number = callback.data.split(":")[1]
    await state.set_state(OwnerReviewStates.waiting_for_custom_reason)
    await state.update_data(order_number=order_number)

    await callback.answer()
    await callback.message.answer(
        f"✍️ **لطفاً متن دلیل رد سفارش `#{order_number}` را بنویسید:**\n\n"
        f"این متن مستقیماً برای خریدار ارسال خواهد شد.",
        parse_mode="Markdown",
    )


@router.message(OwnerReviewStates.waiting_for_custom_reason)
async def process_custom_rejection_reason(
    message: Message,
    state: FSMContext,
    order_service: OrderService,
    notification_service: NotificationService,
    bot: Bot,
):
    """Records the custom rejection note and dispatches notifications."""
    data = await state.get_data()
    order_number = data.get("order_number")
    await state.clear()

    custom_reason = message.text.strip() if message.text else "Payment verification was unsuccessful."

    order = await order_service.get_order_by_number(order_number)
    if not order:
        await message.answer("سفارش یافت نشد.")
        return

    if order.status != OrderStatus.UNDER_REVIEW.value:
        await message.answer(f"وضعیت سفارش دیگر قابل رد شدن نیست: {order.status}")
        return

    order = await order_service.reject_order(order_number, custom_reason)

    # Confirm to Owner in Persian
    await message.answer(
        f"❌ **سفارش `#{order.order_number}` با دلیل سفارشی رد شد.**\n\n"
        f"متن ارسال‌شده به خریدار:\n_{custom_reason}_",
        parse_mode="Markdown",
    )

    # Notify Buyer in English
    await notification_service.notify_buyer_rejected(
        bot,
        user_id=order.user_id,
        order_number=order.order_number,
        reason=custom_reason,
        reply_markup=get_retry_keyboard(),
    )

    # Notify Developer in English
    await notification_service.notify_developer_rejected(bot, order, custom_reason)


@router.callback_query(F.data.startswith("support_reply:"))
async def cb_support_reply(callback: CallbackQuery, state: FSMContext):
    """Prompts the owner to type a reply to the customer's support inquiry."""
    user_id = int(callback.data.split(":")[1])
    await state.set_state(OwnerSupportStates.waiting_for_reply)
    await state.update_data(target_user_id=user_id)

    await callback.answer()
    await callback.message.answer(
        f"✍️ **لطفاً متن پاسخ خود به کاربر `{user_id}` را ارسال فرمایید:**\n\n"
        f"این پیام مستقیماً به چت خریدار ارسال خواهد شد.",
        parse_mode="Markdown",
        reply_markup=get_owner_cancel_reply_keyboard(),
    )


@router.callback_query(F.data == "cancel_support_reply")
async def cb_cancel_support_reply(callback: CallbackQuery, state: FSMContext):
    """Cancels typing a support reply."""
    await state.clear()
    await callback.answer("ارسال پاسخ لغو شد.")
    await callback.message.answer("ارسال پاسخ لغو شد.")


@router.message(OwnerSupportStates.waiting_for_reply)
async def process_owner_support_reply(
    message: Message,
    state: FSMContext,
    notification_service: NotificationService,
    bot: Bot,
):
    """Sends the owner's response to the customer."""
    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    await state.clear()

    reply_text = message.text or message.caption or ""
    if not reply_text.strip():
        await message.answer("⚠️ متن پاسخ نمی‌تواند خالی باشد.")
        return

    if not target_user_id:
        await message.answer("⚠️ شناسه کاربر یافت نشد.")
        return

    delivered = await notification_service.notify_user_support_reply(
        bot=bot,
        user_id=target_user_id,
        reply_text=reply_text.strip(),
    )

    if delivered:
        await message.answer(
            f"✅ **پاسخ شما با موفقیت برای کاربر `{target_user_id}` ارسال گردید.**",
            parse_mode="Markdown",
        )
    else:
        await message.answer(
            f"⚠️ **ارسال پاسخ ناموفق بود!** ممکن است کاربر ربات را مسدود (بلاک) کرده باشد.",
            parse_mode="Markdown",
        )


STATUS_MAP_FA = {
    "AWAITING_PAYMENT": "⏳ در انتظار پرداخت",
    "AWAITING_RECEIPT": "🧾 در انتظار ارسال رسید",
    "UNDER_REVIEW": "🔍 در انتظار تایید",
    "APPROVED": "✅ تایید شده",
    "DELIVERED": "📦 تحویل داده شده",
    "DELIVERY_FAILED": "⚠️ خطا در ارسال فایل",
    "REJECTED": "❌ رد شده",
    "CANCELLED": "🚫 لغو شده توسط خریدار",
    "EXPIRED": "⏱️ منقضی شده",
}


def format_orders_history_message(orders: list[Order], page: int, total_pages: int, total_count: int) -> str:
    """Formats a page of orders into a detailed Persian report."""
    lines = [
        f"📋 **تاریخچه سفارشات (صفحه {page} از {total_pages} | مجموع: {total_count} سفارش):**\n"
    ]
    for idx, order in enumerate(orders, start=(page - 1) * 10 + 1):
        status_text = STATUS_MAP_FA.get(order.status, order.status)
        date_str = format_shamsi_datetime(order.created_at)
        buyer_handle = f"@{escape_md(order.username)}" if order.username else "ندارد"
        buyer_name = escape_md(order.full_name)
        tx_display = f"`{order.tx_hash}`" if order.tx_hash else "ثبت نشده"

        entry = (
            f"🔹 **سفارش #{order.order_number}** (ردیف {idx})\n"
            f"• 👤 خریدار: {buyer_name} ({buyer_handle})\n"
            f"• 🆔 شناسه: `{order.user_id}`\n"
            f"• 💰 مبلغ: ${order.amount_usd:g}\n"
            f"• 📌 وضعیت: {status_text}\n"
            f"• 📅 تاریخ: {date_str}\n"
            f"• 🔗 هش تراکنش: {tx_display}"
        )
        if order.rejection_reason:
            entry += f"\n• ⚠️ دلیل رد: _{escape_md(order.rejection_reason)}_"
        lines.append(entry)

    return "\n\n".join(lines)


@router.callback_query(F.data.startswith("block_user:"))
async def cb_block_user(
    callback: CallbackQuery,
    order_service: OrderService,
    bot: Bot | None = None,
):
    """Blocks a user, captures their username if available, and confirms to the owner."""
    user_id = int(callback.data.split(":")[1])
    active_bot = bot or getattr(callback, "bot", None)
    username = None
    if active_bot:
        try:
            chat = await active_bot.get_chat(user_id)
            username = chat.username
        except Exception:
            pass

    await order_service.block_user(user_id=user_id, username=username)

    await callback.answer("کاربر با موفقیت مسدود شد.", show_alert=True)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"🚫 **کاربر با شناسه `{user_id}` مسدود شد.**\n\n"
        f"این کاربر دیگر قادر به ارسال پیام به پشتیبانی یا خرید از ربات نخواهد بود.\n"
        f"جهت مدیریت یا رفع مسدودیت کاربران، از دستور /blocklist استفاده فرمایید.",
        parse_mode="Markdown",
    )


@router.message(Command("blocklist"))
async def cmd_blocklist(message: Message, order_service: OrderService):
    """Displays a paginated list of blocked users with inline unblock buttons."""
    total_count = await order_service.count_blocked_users()
    if total_count == 0:
        await message.answer(
            "✅ **لیست کاربران مسدود شده خالی است.**\n\nدر حال حاضر هیچ کاربری در لیست مسدودشده‌ها قرار ندارد.",
            parse_mode="Markdown",
        )
        return

    page = 1
    total_pages = max(1, math.ceil(total_count / 10))
    users = await order_service.get_blocked_users(offset=0, limit=10)
    markup = get_blocklist_keyboard(users, page=page, total_pages=total_pages)
    await message.answer(
        f"🚫 **لیست کاربران مسدود شده** (صفحه {page} از {total_pages} | مجموع: {total_count} کاربر):\n\n"
        f"جهت **رفع مسدودیت (Unlock)** هر کاربر، روی دکمه مربوط به آن کلیک نمایید:",
        reply_markup=markup,
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("blocklist_page:"))
async def cb_blocklist_page(callback: CallbackQuery, order_service: OrderService):
    """Handles pagination navigation for the blocklist."""
    page = int(callback.data.split(":")[1])
    total_count = await order_service.count_blocked_users()
    if total_count == 0:
        await callback.message.edit_text(
            "✅ **لیست کاربران مسدود شده خالی است.**",
            parse_mode="Markdown",
        )
        await callback.answer()
        return

    total_pages = max(1, math.ceil(total_count / 10))
    if page < 1:
        page = 1
    elif page > total_pages:
        page = total_pages

    users = await order_service.get_blocked_users(offset=(page - 1) * 10, limit=10)
    markup = get_blocklist_keyboard(users, page=page, total_pages=total_pages)
    await callback.message.edit_text(
        f"🚫 **لیست کاربران مسدود شده** (صفحه {page} از {total_pages} | مجموع: {total_count} کاربر):\n\n"
        f"جهت **رفع مسدودیت (Unlock)** هر کاربر، روی دکمه مربوط به آن کلیک نمایید:",
        reply_markup=markup,
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("unblock_user:"))
async def cb_unblock_user(
    callback: CallbackQuery,
    order_service: OrderService,
    notification_service: NotificationService,
    bot: Bot,
):
    """Unblocks a user, notifies them in English, and updates the blocklist message."""
    parts = callback.data.split(":")
    user_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 1

    unblocked = await order_service.unblock_user(user_id)
    if unblocked:
        await notification_service.notify_user_unblocked(bot=bot, user_id=user_id)
        await callback.answer("کاربر با موفقیت رفع مسدودیت شد و پیام به او ارسال گردید.", show_alert=True)
    else:
        await callback.answer("این کاربر در حال حاضر مسدود نیست.", show_alert=True)

    # Refresh blocklist view
    total_count = await order_service.count_blocked_users()
    if total_count == 0:
        await callback.message.edit_text(
            "✅ **لیست کاربران مسدود شده خالی است.**\n\nتمام کاربران با موفقیت رفع مسدودیت شدند.",
            parse_mode="Markdown",
        )
        return

    total_pages = max(1, math.ceil(total_count / 10))
    if page > total_pages:
        page = total_pages

    users = await order_service.get_blocked_users(offset=(page - 1) * 10, limit=10)
    markup = get_blocklist_keyboard(users, page=page, total_pages=total_pages)
    await callback.message.edit_text(
        f"🚫 **لیست کاربران مسدود شده** (صفحه {page} از {total_pages} | مجموع: {total_count} کاربر):\n\n"
        f"جهت **رفع مسدودیت (Unlock)** هر کاربر، روی دکمه مربوط به آن کلیک نمایید:",
        reply_markup=markup,
        parse_mode="Markdown",
    )


@router.message(Command("history"))
async def cmd_history(message: Message, order_service: OrderService):
    """Displays paginated order history from newest to oldest with full information."""
    total_count = await order_service.count_orders()
    if total_count == 0:
        await message.answer(
            "ℹ️ تاکنون هیچ سفارشی در سیستم ثبت نشده است.",
            parse_mode="Markdown",
        )
        return

    page = 1
    total_pages = max(1, math.ceil(total_count / 10))
    orders = await order_service.get_orders_paginated(offset=0, limit=10)
    text = format_orders_history_message(orders, page=page, total_pages=total_pages, total_count=total_count)
    markup = get_history_pagination_keyboard(page=page, total_pages=total_pages)
    await message.answer(text, reply_markup=markup, parse_mode="Markdown")


@router.callback_query(F.data.startswith("history_page:"))
async def cb_history_page(callback: CallbackQuery, order_service: OrderService):
    """Handles pagination for order history."""
    page = int(callback.data.split(":")[1])
    total_count = await order_service.count_orders()
    if total_count == 0:
        await callback.message.edit_text("ℹ️ تاکنون هیچ سفارشی در سیستم ثبت نشده است.", parse_mode="Markdown")
        await callback.answer()
        return

    total_pages = max(1, math.ceil(total_count / 10))
    if page < 1:
        page = 1
    elif page > total_pages:
        page = total_pages

    orders = await order_service.get_orders_paginated(offset=(page - 1) * 10, limit=10)
    text = format_orders_history_message(orders, page=page, total_pages=total_pages, total_count=total_count)
    markup = get_history_pagination_keyboard(page=page, total_pages=total_pages)
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "close_admin_panel")
async def cb_close_admin_panel(callback: CallbackQuery):
    """Closes and removes the current admin panel message."""
    try:
        await callback.message.delete()
    except Exception:
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("بسته شد.")


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    """No-op callback for page indicator button."""
    await callback.answer()

