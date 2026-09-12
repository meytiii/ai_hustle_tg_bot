"""Buyer interaction handlers (100% English interface)."""

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.bot.keyboards.buyer_keyboards import (
    get_buy_payment_keyboard,
    get_download_pdf_keyboard,
    get_more_details_keyboard,
    get_payment_help_keyboard,
    get_product_keyboard,
    get_rejection_keyboard,
    get_start_keyboard,
    get_support_keyboard,
    get_tx_hash_submission_keyboard,
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
from src.services.delivery_service import BuyerBlockedBotError, DeliveryService
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

# Text Constants Matching Exact User Specifications
START_TEXT = (
    "👋 **Welcome!**\n\n"
    "Welcome to the official store for the AI Side Hustle Launch System.\n"
    "Turn your side hustle idea into a structured plan for building, launching, selling, and growing a digital product.\n\n"
    "🚀 **Visual Pro Edition**\n"
    "24-Part Launch System\n\n"
    "Click below to learn more and get your copy.\n"
    "All purchases are delivered directly through Telegram after payment confirmation."
)

PRODUCT_TEXT = (
    "🧠 **AI Side Hustle Launch System**\n"
    "**Visual Pro Edition**\n\n"
    "A practical 24-part system designed to help you move from:\n"
    "Idea → Validation → Product → Offer → Launch → Sales → Growth\n\n"
    "Inside, you'll find:\n"
    "✓ 24 structured parts\n"
    "✓ Practical frameworks\n"
    "✓ Workbooks & templates\n"
    "✓ Real-world examples\n"
    "✓ AI-assisted workflows\n"
    "✓ Experiments designed for action\n\n"
    "Regular Price: ~~$99~~\n"
    "🔥 **Launch Price: $79**\n\n"
    "Get instant digital delivery after payment confirmation."
)

MORE_DETAILS_TEXT = (
    "📖 **What's Inside?**\n\n"
    "The AI Side Hustle Launch System is organized into 24 parts covering the complete journey "
    "from opportunity discovery to a 12-month growth plan.\n\n"
    "The system covers:\n"
    "Opportunity Engine\n"
    "Validation Engine\n"
    "Customer Intelligence\n"
    "Product Architecture\n"
    "Content & Curriculum\n"
    "Offer Design\n"
    "Pricing & Economics\n"
    "Brand & Product Experience\n"
    "Sales Asset System\n"
    "Launch System\n"
    "Organic Distribution\n"
    "Community & Conversation\n"
    "Email & Retention\n"
    "Revenue Engine\n"
    "Launch & Campaign Machine\n"
    "Customer Acquisition Lab\n"
    "Conversion Optimization\n"
    "Product Expansion & Ladder\n"
    "Customer Success & Proof\n"
    "Operations & Automation\n"
    "Analytics & Decision System\n"
    "Risk & Failure-Proofing\n"
    "Product Ecosystem\n"
    "12-Month Master Plan\n\n"
    "Price: **$79 launch price**\n\n"
    "Ready to get started?"
)

PAYMENT_HELP_TEXT = (
    "❓ **Payment Help**\n\n"
    "To purchase the product:\n"
    "1. Open your TON-compatible wallet, such as Tonkeeper.\n"
    "2. Choose USDT.\n"
    "3. Make sure the network is TON.\n"
    "4. Send exactly 79 USDT to the wallet address provided above.\n"
    "5. After sending the payment, return here and click I HAVE PAID.\n"
    "6. You will be asked to provide your transaction hash.\n\n"
    "Your payment will be manually verified before your product is delivered.\n"
    "⚠️ Please double-check the network and wallet address before sending."
)

PAYMENT_SUBMITTED_TEXT = (
    "✅ **Payment Submitted**\n\n"
    "Thank you!\n"
    "Please send your transaction hash (TX Hash) below.\n"
    "We will manually verify your payment.\n\n"
    "Once your payment is confirmed, your digital product will be delivered automatically here in this Telegram chat.\n\n"
    "Please do not send your wallet recovery phrase or private key.\n"
    "Only send the transaction hash."
)

PAYMENT_UNDER_REVIEW_TEXT = (
    "🔎 **Payment Under Review**\n\n"
    "Thank you. We have received your transaction hash.\n"
    "Your payment is now being verified.\n"
    "⏳ Please wait for confirmation.\n\n"
    "You will receive your product here once the payment has been approved."
)

SUPPORT_TEXT = (
    "💬 **Support**\n\n"
    "Need help with your purchase or payment?\n"
    "Send us your question and we'll help you as soon as possible.\n\n"
    "For payment issues, please include your transaction hash.\n"
    "⚠️ Never send your wallet recovery phrase or private key."
)


async def safe_edit_or_answer(
    event: Message | CallbackQuery,
    text: str,
    reply_markup=None,
    parse_mode: str = "Markdown",
) -> None:
    """Edits current message if event is a CallbackQuery, otherwise sends a new message."""
    if isinstance(event, CallbackQuery):
        try:
            await event.message.edit_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode)
        except TelegramBadRequest:
            await event.message.answer(text=text, reply_markup=reply_markup, parse_mode=parse_mode)
    else:
        await event.answer(text=text, reply_markup=reply_markup, parse_mode=parse_mode)


@router.message(
    StateFilter(BuyerOrderStates.waiting_for_tx_hash),
    F.text.startswith("/") | (F.text.casefold() == "help"),
)
async def intercept_locked_commands(message: Message, state: FSMContext):
    """Intercepts commands during TX hash submission, reacts with ✋, and offers back navigation."""
    data = await state.get_data()
    order_number = data.get("order_number", "")
    await react_to_message(message, STOP_EMOJI)
    await message.answer(
        "✋ **Payment Submission in Progress**\n\n"
        "Commands are locked until your Transaction Hash is received.\n"
        "Please provide your transaction hash below to complete your order, or click Back:",
        parse_mode="Markdown",
        reply_markup=get_tx_hash_submission_keyboard(order_number),
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Welcomes the user with Step 1 message and options."""
    await state.clear()
    await message.answer(
        text=START_TEXT,
        parse_mode="Markdown",
        reply_markup=get_start_keyboard(),
    )


@router.callback_query(F.data == "back_to_start")
async def cb_back_to_start(callback: CallbackQuery, state: FSMContext):
    """Navigates back to the main welcome screen."""
    await state.clear()
    await callback.answer()
    await safe_edit_or_answer(callback, START_TEXT, reply_markup=get_start_keyboard())


@router.callback_query(F.data == "view_product")
@router.message(Command("info"))
async def cb_view_product(event: Message | CallbackQuery, state: FSMContext):
    """Displays Step 2 product details and actions."""
    await state.clear()
    if isinstance(event, CallbackQuery):
        await event.answer()
    await safe_edit_or_answer(event, PRODUCT_TEXT, reply_markup=get_product_keyboard())


@router.callback_query(F.data == "more_details")
async def cb_more_details(callback: CallbackQuery, state: FSMContext):
    """Displays Step 3 system breakdown with 24 parts."""
    await state.clear()
    await callback.answer()
    await safe_edit_or_answer(callback, MORE_DETAILS_TEXT, reply_markup=get_more_details_keyboard())


async def execute_buy_flow(
    event: Message | CallbackQuery,
    state: FSMContext,
    order_service: OrderService,
    settings: Settings,
):
    """Creates or retrieves the customer's pending order and renders Step 4 payment screen."""
    await state.clear()
    user = event.from_user

    # Check if user already has an order under review
    active_order = await order_service.get_active_order_by_user(user.id)
    if active_order:
        if active_order.status == OrderStatus.UNDER_REVIEW.value:
            if isinstance(event, CallbackQuery):
                await event.answer()
            await safe_edit_or_answer(
                event,
                PAYMENT_UNDER_REVIEW_TEXT,
                reply_markup=get_start_keyboard(),
            )
            return
        elif active_order.status == OrderStatus.AWAITING_PAYMENT.value:
            order = active_order
            if order.wallet_address != settings.ton_wallet_address:
                order.wallet_address = settings.ton_wallet_address
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

    buy_text = (
        "💳 **Secure Your Copy**\n\n"
        "AI Side Hustle Launch System — Visual Pro Edition\n"
        "🔥 **Launch Price: $79**\n\n"
        "Payment method: USDT on the TON Network\n\n"
        "Please send exactly:\n"
        "**79 USDT**\n"
        "to the wallet address shown below.\n\n"
        "⚠️ **Important: Make sure you are sending USDT on the TON Network.**\n\n"
        "Wallet Address:\n\n"
        f"`{settings.ton_wallet_address}`\n\n"
        "After completing the payment, click I HAVE PAID below."
    )

    markup = get_buy_payment_keyboard(order.order_number)
    if isinstance(event, CallbackQuery):
        await event.answer()
    await safe_edit_or_answer(event, buy_text, reply_markup=markup)


@router.message(Command("buy"))
@router.callback_query(F.data == "buy_now")
async def cb_buy_now(
    event: Message | CallbackQuery,
    state: FSMContext,
    order_service: OrderService,
    settings: Settings,
):
    """Initiates checkout and renders payment instructions."""
    await execute_buy_flow(event, state, order_service, settings)


cmd_buy = cb_buy_now
cmd_info = cb_view_product


@router.callback_query(F.data.startswith("payment_help:"))
async def cb_payment_help(callback: CallbackQuery):
    """Displays Step 5 payment guide."""
    order_number = callback.data.split(":")[1]
    await callback.answer()
    await safe_edit_or_answer(
        callback,
        PAYMENT_HELP_TEXT,
        reply_markup=get_payment_help_keyboard(order_number),
    )


@router.callback_query(F.data.startswith("back_to_payment:"))
async def cb_back_to_payment(
    callback: CallbackQuery,
    state: FSMContext,
    order_service: OrderService,
    settings: Settings,
):
    """Returns back to the payment instructions screen."""
    await state.clear()
    order_number = callback.data.split(":")[1]
    order = await order_service.get_order_by_number(order_number)
    if order and order.wallet_address != settings.ton_wallet_address:
        order.wallet_address = settings.ton_wallet_address

    buy_text = (
        "💳 **Secure Your Copy**\n\n"
        "AI Side Hustle Launch System — Visual Pro Edition\n"
        "🔥 **Launch Price: $79**\n\n"
        "Payment method: USDT on the TON Network\n\n"
        "Please send exactly:\n"
        "**79 USDT**\n"
        "to the wallet address shown below.\n\n"
        "⚠️ **Important: Make sure you are sending USDT on the TON Network.**\n\n"
        "Wallet Address:\n\n"
        f"`{settings.ton_wallet_address}`\n\n"
        "After completing the payment, click I HAVE PAID below."
    )
    await callback.answer()
    await safe_edit_or_answer(
        callback,
        buy_text,
        reply_markup=get_buy_payment_keyboard(order_number),
    )


@router.callback_query(F.data.startswith("i_have_paid:"))
async def cb_i_have_paid(callback: CallbackQuery, state: FSMContext, order_service: OrderService):
    """Transitions user into waiting_for_tx_hash and prompts for transaction hash (Step 6)."""
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
            reply_markup=get_product_keyboard(),
        )
        return

    await state.set_state(BuyerOrderStates.waiting_for_tx_hash)
    await state.update_data(order_number=order_number)

    await callback.answer()
    await safe_edit_or_answer(
        callback,
        PAYMENT_SUBMITTED_TEXT,
        reply_markup=get_tx_hash_submission_keyboard(order_number),
    )


# Backward compatibility alias for submit_proof callback
@router.callback_query(F.data.startswith("submit_proof:"))
async def cb_submit_proof_alias(callback: CallbackQuery, state: FSMContext, order_service: OrderService):
    await cb_i_have_paid(callback, state, order_service)


cb_submit_proof = cb_i_have_paid


@router.message(BuyerOrderStates.waiting_for_tx_hash)
async def process_tx_hash(
    message: Message,
    state: FSMContext,
    order_service: OrderService,
    notification_service: NotificationService,
    bot: Bot,
):
    """Receives and validates transaction hash, updates state to UNDER_REVIEW, and alerts Owner."""
    tx_hash = message.text.strip() if message.text else ""
    data = await state.get_data()
    order_number = data.get("order_number")

    if not tx_hash or len(tx_hash) < 10:
        await react_to_message(message, SOB_EMOJI)
        await message.answer(
            "⚠️ Please provide a valid transaction hash (text).",
            reply_markup=get_tx_hash_submission_keyboard(order_number) if order_number else get_product_keyboard(),
        )
        return

    if not order_number:
        await state.clear()
        await message.answer("Session expired. Please restart your order.", reply_markup=get_product_keyboard())
        return

    try:
        order = await order_service.submit_tx_hash(order_number, tx_hash)
    except OrderExpiredError:
        await state.clear()
        await message.answer(
            f"⚠️ Order `#{order_number}` has expired. Please start a new order.",
            parse_mode="Markdown",
            reply_markup=get_product_keyboard(),
        )
        return
    except OrderStateError as e:
        await state.clear()
        await message.answer(f"⚠️ Error: {e}", reply_markup=get_product_keyboard())
        return

    # Valid transaction hash accepted!
    await react_to_message(message, THUMBS_UP_EMOJI)
    await state.clear()

    # Step 7: Inform Buyer
    await message.answer(
        text=PAYMENT_UNDER_REVIEW_TEXT,
        parse_mode="Markdown",
    )

    # Step 8: Notify Owner in Persian
    owner_markup = get_owner_review_keyboard(order.order_number)
    await notification_service.notify_owner_new_order(bot, order, owner_markup)


@router.callback_query(F.data.startswith("download_pdf:"))
async def cb_download_pdf(
    callback: CallbackQuery,
    order_service: OrderService,
    delivery_service: DeliveryService,
    bot: Bot,
):
    """Delivers the actual PDF digital guide on demand when buyer clicks the download button (Step 10)."""
    order_number = callback.data.split(":")[1]
    order = await order_service.get_order_by_number(order_number)

    if not order:
        await callback.answer("Order not found.", show_alert=True)
        return

    if order.user_id != callback.from_user.id:
        await callback.answer("Unauthorized.", show_alert=True)
        return

    if order.status not in (OrderStatus.APPROVED.value, OrderStatus.DELIVERED.value):
        await callback.answer("Payment is not approved yet.", show_alert=True)
        return

    await callback.answer("Sending your PDF file...")

    try:
        await delivery_service.deliver_pdf(bot, order.user_id, order.order_number)
        await order_service.mark_delivered(order_number)
    except BuyerBlockedBotError:
        await order_service.mark_delivery_failed(order_number)
        await callback.message.answer(
            "⚠️ It appears you have blocked messages from this bot. Please unblock the bot to receive your file."
        )
    except Exception as e:
        logger.error(f"Failed to deliver PDF on click for order {order_number}: {e}")
        await callback.message.answer("⚠️ An error occurred while sending your file. Please try again.")


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
            reply_markup=get_product_keyboard(),
        )
    except Exception as e:
        logger.warning(f"Could not cancel order {order_number}: {e}")
        await callback.answer("Order was already cancelled or expired.", show_alert=True)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, order_service: OrderService):
    """Cancels the current order via command."""
    data = await state.get_data()
    order_number = data.get("order_number")
    await state.clear()

    if order_number:
        try:
            await order_service.cancel_order(order_number)
            await message.answer(
                f"❌ Your order `#{order_number}` has been cancelled.",
                parse_mode="Markdown",
                reply_markup=get_product_keyboard(),
            )
            return
        except Exception as e:
            logger.warning(f"Failed to cancel order {order_number} via /cancel: {e}")

    await message.answer(
        "Current action cancelled.",
        reply_markup=get_start_keyboard(),
    )


@router.message(Command("support"))
@router.message(Command("contact"))
@router.callback_query(F.data == "contact_support")
async def start_contact_support(event: Message | CallbackQuery, state: FSMContext):
    """Displays Support instructions and sets waiting_for_message state."""
    await state.set_state(BuyerSupportStates.waiting_for_message)
    if isinstance(event, CallbackQuery):
        await event.answer()
    await safe_edit_or_answer(
        event,
        SUPPORT_TEXT,
        reply_markup=get_support_keyboard(),
    )


@router.message(BuyerSupportStates.waiting_for_message)
async def process_support_message(
    message: Message,
    state: FSMContext,
    notification_service: NotificationService,
    bot: Bot,
):
    """Processes buyer support inquiry and forwards to Owner."""
    text = message.text or message.caption or ""
    if not text.strip():
        await message.answer("⚠️ Please provide a text message for support.")
        return

    await react_to_message(message, THUMBS_UP_EMOJI)
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
    await safe_edit_or_answer(
        callback,
        START_TEXT,
        reply_markup=get_start_keyboard(),
    )
