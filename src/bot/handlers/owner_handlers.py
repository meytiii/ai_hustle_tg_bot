"""Owner administrative handlers (100% Persian / Farsi interface)."""

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards.buyer_keyboards import get_retry_keyboard
from src.bot.keyboards.owner_keyboards import (
    REJECTION_PRESET_EXPLANATIONS_EN,
    get_owner_cancel_reply_keyboard,
    get_owner_reject_presets_keyboard,
    get_owner_review_keyboard,
)
from src.bot.states import OwnerReviewStates, OwnerSupportStates
from src.database.models import OrderStatus
from src.services.delivery_service import BuyerBlockedBotError, DeliveryError, DeliveryService
from src.services.notification_service import NotificationService
from src.services.order_service import OrderService, OrderStateError
from src.utils.logger import logger

router = Router(name="owner_router")


@router.callback_query(F.data.startswith("owner_approve:"))
async def cb_owner_approve(
    callback: CallbackQuery,
    order_service: OrderService,
    delivery_service: DeliveryService,
    notification_service: NotificationService,
    bot: Bot,
):
    """Handles order approval, immediate idempotent file delivery, and bilingual notifications."""
    order_number = callback.data.split(":")[1]
    order = await order_service.get_order_by_number(order_number)

    if not order:
        await callback.answer("سفارش یافت نشد.", show_alert=True)
        return

    # Idempotency check: if already approved/delivered, avoid duplicate file dispatch
    if order.status in [OrderStatus.APPROVED.value, OrderStatus.DELIVERED.value]:
        await callback.answer("این سفارش قبلاً تایید شده است.", show_alert=True)
        return

    if order.status != OrderStatus.UNDER_REVIEW.value:
        await callback.answer(f"وضعیت سفارش نامعتبر است: {order.status}", show_alert=True)
        return

    await callback.answer("در حال ثبت تایید و ارسال فایل...")

    # 1. Transition state to APPROVED
    try:
        order = await order_service.approve_order(order_number)
    except OrderStateError as e:
        await callback.message.answer(f"خطا در تغییر وضعیت سفارش: {e}")
        return

    # 2. Deliver PDF to Buyer
    try:
        await delivery_service.deliver_pdf(bot, order.user_id, order.order_number)
        await order_service.mark_delivered(order_number)

        # Update Owner UI
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            f"✅ **سفارش `#{order.order_number}` تایید شد.**\n\n"
            f"فایل کتاب با موفقیت به تلگرام خریدار ارسال گردید.",
            parse_mode="Markdown",
        )

        # Notify Developer (English)
        await notification_service.notify_developer_completed(bot, order)

    except BuyerBlockedBotError:
        await order_service.mark_delivery_failed(order_number)
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            f"⚠️ **سفارش `#{order.order_number}` تایید شد، اما ارسال فایل ناموفق بود!**\n\n"
            f"علت: خریدار ربات را مسدود (بلاک) کرده است.",
            parse_mode="Markdown",
        )
        await notification_service.notify_developer_error(
            bot,
            context=f"Delivery failed for order {order_number}",
            error_details="Buyer has blocked the bot.",
        )
    except DeliveryError as e:
        await order_service.mark_delivery_failed(order_number)
        await callback.message.answer(f"❌ خطا در ارسال فایل: {e}")
        await notification_service.notify_developer_error(
            bot,
            context=f"Delivery failed for order {order_number}",
            error_details=str(e),
        )


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


@router.callback_query(F.data.startswith("block_user:"))
async def cb_block_user(callback: CallbackQuery, order_service: OrderService):
    """Blocks a user and confirms to the owner."""
    user_id = int(callback.data.split(":")[1])
    await order_service.block_user(user_id)

    await callback.answer("کاربر با موفقیت مسدود شد.", show_alert=True)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"🚫 **کاربر با شناسه `{user_id}` مسدود شد.**\n\n"
        f"این کاربر دیگر قادر به ارسال پیام به پشتیبانی یا خرید از ربات نخواهد بود.",
        parse_mode="Markdown",
    )
