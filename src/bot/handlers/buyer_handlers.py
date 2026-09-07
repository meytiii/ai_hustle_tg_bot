"""Buyer interaction handlers (100% English interface)."""

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards.buyer_keyboards import (
    get_cancel_submission_keyboard,
    get_cancel_support_keyboard,
    get_order_payment_keyboard,
    get_retry_keyboard,
    get_start_keyboard,
)
from src.bot.keyboards.owner_keyboards import (
    get_owner_review_keyboard,
    get_owner_support_reply_keyboard,
)
from src.bot.middlewares.reaction_middleware import (
    SOB_EMOJI,
    STOP_EMOJI,
    THUMBS_UP_EMOJI,
    react_to_message,
)
from src.bot.states import BuyerOrderStates, BuyerSupportStates
from src.config import Settings
from src.database.models import OrderStatus
from src.services.notification_service import NotificationService
from src.services.order_service import (
    DuplicateTxHashError,
    OrderExpiredError,
    OrderNotFoundError,
    OrderService,
    OrderStateError,
)
from src.utils.logger import logger

router = Router(name="buyer_router")


@router.message(
    StateFilter(BuyerOrderStates.waiting_for_tx_hash, BuyerOrderStates.waiting_for_receipt),
    F.text.startswith("/") | (F.text.casefold() == "help"),
)
async def intercept_locked_commands(message: Message, state: FSMContext):
    """Intercepts commands during payment proof submission, locks them, reacts with ✋, and offers cancellation."""
    data = await state.get_data()
    order_number = data.get("order_number", "")
    await react_to_message(message, STOP_EMOJI)
    await message.answer(
        "✋ **Proof Submission in Progress**\n\n"
        "Commands are locked until your Transaction Hash and payment screenshot are received.\n"
        "Please provide your payment proof to complete your order, or cancel your submission below:",
        parse_mode="Markdown",
        reply_markup=get_cancel_submission_keyboard(order_number),
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, settings: Settings):
    """Welcomes the user and presents the AI Side Hustle product with launch promotion."""
    await state.clear()
    welcome_text = (
        f"👋 **Welcome!**\n\n"
    )
    await message.answer(
        text=welcome_text,
        parse_mode="Markdown",
        reply_markup=get_start_keyboard(),
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, order_service: OrderService):
    """Allows the user to cancel an ongoing order or submission."""
    data = await state.get_data()
    order_number = data.get("order_number")
    await state.clear()

    if order_number:
        try:
            await order_service.cancel_order(order_number)
            await message.answer(
                f"❌ Your order `#{order_number}` has been cancelled.",
                parse_mode="Markdown",
                reply_markup=get_retry_keyboard(),
            )
            return
        except Exception as e:
            logger.warning(f"Failed to cancel order {order_number} via /cancel: {e}")

    await message.answer(
        "Current action cancelled. You can start a new order at any time.",
        reply_markup=get_retry_keyboard(),
    )


async def execute_buy_flow(
    event: Message | CallbackQuery,
    state: FSMContext,
    order_service: OrderService,
    settings: Settings,
):
    """Core logic to create or resume an order and display payment instructions."""
    await state.clear()
    user = event.from_user

    # Check if user already has an active order under review
    active_order = await order_service.get_active_order_by_user(user.id)
    if active_order:
        if active_order.status == OrderStatus.UNDER_REVIEW.value:
            if isinstance(event, CallbackQuery):
                await event.answer()
                await event.message.answer(
                    f"ℹ️ Your order `#{active_order.order_number}` is currently under review by our administrator.\n\n"
                    f"You will receive your PDF guide as soon as verification is complete.",
                    parse_mode="Markdown",
                )
            else:
                await event.answer(
                    f"ℹ️ Your order `#{active_order.order_number}` is currently under review by our administrator.\n\n"
                    f"You will receive your PDF guide as soon as verification is complete.",
                    parse_mode="Markdown",
                )
            return
        elif active_order.status in [OrderStatus.AWAITING_PAYMENT.value, OrderStatus.AWAITING_RECEIPT.value]:
            # Reuse existing active pending order
            order = active_order
        else:
            order = await order_service.create_order(
                user_id=user.id,
                username=user.username,
                full_name=user.full_name or "Valued Customer",
                amount_usd=settings.price_usd,
                amount_ton=settings.price_ton,
                wallet_address=settings.ton_wallet_address,
                timeout_minutes=settings.order_timeout_minutes,
            )
    else:
        order = await order_service.create_order(
            user_id=user.id,
            username=user.username,
            full_name=user.full_name or "Valued Customer",
            amount_usd=settings.price_usd,
            amount_ton=settings.price_ton,
            wallet_address=settings.ton_wallet_address,
            timeout_minutes=settings.order_timeout_minutes,
        )

    payment_instructions = (
        f"🧾 **Order Summary: `#{order.order_number}`**\n\n"
        f"• **Product:** AI Side Hustle (PDF Guide)\n"
        f"• **Amount Due:** **${order.amount_usd:g}**\n\n"
        f"📥 **Send TON to the following wallet address:**\n"
        f"`{order.wallet_address}`\n\n"
        f"_(Tap the address above to copy it to your clipboard)_\n\n"
        f"⚠️ **IMPORTANT — BEFORE YOU PAY:**\n"
        f"Please ensure you **copy your Transaction Hash / ID** and **take a screenshot of your payment confirmation**.\n"
        f"You will need to submit both in the next step to verify your purchase.\n\n"
        f"⏱️ _This order remains valid for {settings.order_timeout_minutes} minutes._"
    )

    markup = get_order_payment_keyboard(order.order_number)
    if isinstance(event, CallbackQuery):
        await event.answer()
        await event.message.answer(
            text=payment_instructions,
            parse_mode="Markdown",
            reply_markup=markup,
        )
    else:
        await event.answer(
            text=payment_instructions,
            parse_mode="Markdown",
            reply_markup=markup,
        )


@router.message(Command("buy"))
async def cmd_buy(
    message: Message,
    state: FSMContext,
    order_service: OrderService,
    settings: Settings,
):
    """Executes the buying procedure via /buy."""
    await execute_buy_flow(message, state, order_service, settings)


@router.callback_query(F.data == "buy_now")
async def cb_buy_now(
    callback: CallbackQuery,
    state: FSMContext,
    order_service: OrderService,
    settings: Settings,
):
    """Creates a new order and presents payment instructions via the inline button."""
    await execute_buy_flow(callback, state, order_service, settings)


@router.message(Command("info"))
async def cmd_info(message: Message, settings: Settings):
    """Provides product information and current launch pricing."""
    info_text = (
        f"📖 **About 'AI Side Hustle' (PDF Guide)**\n\n"
        f"A comprehensive, actionable blueprint designed to help you build sustainable online income "
        f"streams leveraging modern artificial intelligence tools.\n\n"
        f"• **Format:** Digital PDF eBook\n"
        f"• **Price:** **${settings.price_usd:g}** ~~(Regular: ${settings.original_price_usd:g})~~\n"
        f"• **Delivery:** Instant automated file delivery directly in Telegram once your payment is verified.\n\n"
        f"Ready to unlock your copy? Use **/buy** or tap below:"
    )
    await message.answer(
        text=info_text,
        parse_mode="Markdown",
        reply_markup=get_start_keyboard(),
    )



@router.callback_query(F.data.startswith("submit_proof:"))
async def cb_submit_proof(callback: CallbackQuery, state: FSMContext, order_service: OrderService):
    """Initiates the 2-step proof submission flow starting with TX hash."""
    order_number = callback.data.split(":")[1]
    order = await order_service.get_order_by_number(order_number)

    if not order:
        await callback.answer("Order not found.", show_alert=True)
        return

    if order.is_expired():
        await callback.answer("This order has expired.", show_alert=True)
        await callback.message.answer(
            f"⚠️ Order `#{order_number}` has expired. Please initiate a new order.",
            parse_mode="Markdown",
            reply_markup=get_retry_keyboard(),
        )
        return

    await state.set_state(BuyerOrderStates.waiting_for_tx_hash)
    await state.update_data(order_number=order_number)

    await callback.answer()
    await callback.message.answer(
        f"📝 **Step 1 of 2: Submit Transaction Hash**\n\n"
        f"Order: `#{order_number}`\n\n"
        f"Please paste and send your **TON Transaction Hash / ID** below:",
        parse_mode="Markdown",
        reply_markup=get_cancel_submission_keyboard(order_number),
    )


@router.message(BuyerOrderStates.waiting_for_tx_hash)
async def process_tx_hash(message: Message, state: FSMContext, order_service: OrderService):
    """Receives and validates the buyer's TON transaction hash."""
    tx_hash = message.text.strip() if message.text else ""
    data = await state.get_data()
    order_number = data.get("order_number")

    if not tx_hash or len(tx_hash) < 10:
        await react_to_message(message, SOB_EMOJI)
        await message.answer(
            "⚠️ Please provide a valid transaction hash (text).",
            reply_markup=get_cancel_submission_keyboard(order_number) if order_number else get_retry_keyboard(),
        )
        return

    if not order_number:
        await state.clear()
        await message.answer("Session expired. Please restart your order.", reply_markup=get_retry_keyboard())
        return

    try:
        await order_service.submit_tx_hash(order_number, tx_hash)
    except DuplicateTxHashError:
        await react_to_message(message, SOB_EMOJI)
        await message.answer(
            "⚠️ **Duplicate Transaction Detected:**\n\n"
            "This transaction hash has already been submitted for another order. "
            "Please verify your wallet details and send a valid, unsubmitted transaction hash.",
            parse_mode="Markdown",
            reply_markup=get_cancel_submission_keyboard(order_number),
        )
        return
    except OrderExpiredError:
        await state.clear()
        await message.answer(
            f"⚠️ Order `#{order_number}` has expired. Please start a new order.",
            parse_mode="Markdown",
            reply_markup=get_retry_keyboard(),
        )
        return
    except OrderStateError as e:
        await state.clear()
        await message.answer(f"⚠️ Error: {e}", reply_markup=get_retry_keyboard())
        return

    # Valid transaction hash accepted!
    await react_to_message(message, THUMBS_UP_EMOJI)
    await state.set_state(BuyerOrderStates.waiting_for_receipt)
    await message.answer(
        f"✅ Transaction hash recorded!\n\n"
        f"📸 **Step 2 of 2: Upload Payment Receipt**\n\n"
        f"Please send a clear **screenshot or photo** of your payment receipt below:",
        parse_mode="Markdown",
        reply_markup=get_cancel_submission_keyboard(order_number),
    )


@router.message(BuyerOrderStates.waiting_for_receipt)
async def process_receipt(
    message: Message,
    state: FSMContext,
    order_service: OrderService,
    notification_service: NotificationService,
    bot: Bot,
):
    """Receives the screenshot receipt, finalizes submission, and alerts the Owner."""
    data = await state.get_data()
    order_number = data.get("order_number")

    file_id = None
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
        file_id = message.document.file_id

    if not file_id:
        await message.answer(
            "⚠️ Please upload your receipt as a photo or image document.",
            reply_markup=get_cancel_submission_keyboard(order_number),
        )
        return

    try:
        order = await order_service.submit_receipt(order_number, file_id)
    except OrderExpiredError:
        await state.clear()
        await message.answer(
            f"⚠️ Order `#{order_number}` has expired. Please initiate a new order.",
            parse_mode="Markdown",
            reply_markup=get_retry_keyboard(),
        )
        return
    except Exception as e:
        logger.error(f"Error saving receipt for order {order_number}: {e}")
        await message.answer("⚠️ An error occurred processing your receipt. Please try again.")
        return

    # Valid receipt screenshot accepted!
    await react_to_message(message, THUMBS_UP_EMOJI)
    await state.clear()

    # Inform buyer
    await message.answer(
        f"✅ **Payment Proof Received!**\n\n"
        f"Your order `#{order_number}` has been submitted and is now under review by our administrator.\n\n"
        f"Once your payment is verified, your **AI Side Hustle** PDF guide will be delivered directly in this chat. Thank you!",
        parse_mode="Markdown",
    )

    # Notify Owner in Persian
    owner_markup = get_owner_review_keyboard(order.order_number)
    await notification_service.notify_owner_new_order(bot, order, owner_markup)


@router.callback_query(F.data.startswith("cancel_order:"))
async def cb_cancel_order(callback: CallbackQuery, state: FSMContext, order_service: OrderService):
    """Cancels the current order."""
    order_number = callback.data.split(":")[1]
    await state.clear()

    try:
        await order_service.cancel_order(order_number)
        await callback.answer("Order cancelled.")
        await callback.message.answer(
            f"❌ Order `#{order_number}` has been cancelled.",
            parse_mode="Markdown",
            reply_markup=get_retry_keyboard(),
        )
    except Exception as e:
        logger.warning(f"Could not cancel order {order_number}: {e}")
        await callback.answer("Order was already cancelled or expired.", show_alert=True)


@router.message(Command("support"))
@router.message(Command("contact"))
@router.callback_query(F.data == "contact_support")
async def start_contact_support(event: Message | CallbackQuery, state: FSMContext):
    """Prompts the user to type and send their message for support."""
    await state.set_state(BuyerSupportStates.waiting_for_message)
    prompt_text = (
        "💬 **Contact Support**\n\n"
        "Please type and send your question or message below.\n"
        "Our team will receive your message and reply directly in this chat:"
    )
    if isinstance(event, CallbackQuery):
        await event.answer()
        await event.message.answer(
            text=prompt_text,
            parse_mode="Markdown",
            reply_markup=get_cancel_support_keyboard(),
        )
    else:
        await event.answer(
            text=prompt_text,
            parse_mode="Markdown",
            reply_markup=get_cancel_support_keyboard(),
        )


@router.message(BuyerSupportStates.waiting_for_message)
async def process_support_message(
    message: Message,
    state: FSMContext,
    notification_service: NotificationService,
    bot: Bot,
):
    """Processes the user's message and delivers it to the Owner."""
    text = message.text or message.caption or ""
    if not text.strip():
        await message.answer("⚠️ Please provide a text message for support.")
        return

    await state.clear()
    user = message.from_user
    owner_markup = get_owner_support_reply_keyboard(user.id)

    delivered = await notification_service.notify_owner_support_message(
        bot=bot,
        user_id=user.id,
        username=user.username,
        full_name=user.full_name or "Customer",
        message_text=text.strip(),
        reply_markup=owner_markup,
    )

    if delivered:
        await message.answer(
            "✅ **Message Sent!**\n\n"
            "Your message has been delivered to our team. We will review it and reply directly to you right here in this chat.",
            reply_markup=get_start_keyboard(),
        )
    else:
        await message.answer(
            "⚠️ An error occurred while sending your message. Please try again later.",
            reply_markup=get_start_keyboard(),
        )


@router.callback_query(F.data == "cancel_support")
async def cb_cancel_support(callback: CallbackQuery, state: FSMContext):
    """Cancels support contact and returns to main menu."""
    await state.clear()
    await callback.answer("Support request cancelled.")
    await callback.message.answer(
        "Support request cancelled.",
        reply_markup=get_start_keyboard(),
    )
