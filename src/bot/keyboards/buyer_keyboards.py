"""Inline keyboards for the customer buyer flow (100% English)."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_start_keyboard() -> InlineKeyboardMarkup:
    """Start menu keyboard with product details and support."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🧠 AI Side Hustle Launch System",
                    callback_data="view_product",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="💬 Support",
                    callback_data="contact_support",
                ),
            ],
        ]
    )


def get_product_keyboard() -> InlineKeyboardMarkup:
    """Product presentation screen with Buy, More Details, and Back buttons."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 BUY FOR $79",
                    callback_data="buy_now",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📖 MORE DETAILS",
                    callback_data="more_details",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ BACK",
                    callback_data="back_to_start",
                ),
            ],
        ]
    )


def get_more_details_keyboard() -> InlineKeyboardMarkup:
    """Extended system curriculum view with Buy and Back buttons."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔥 GET IT FOR $79",
                    callback_data="buy_now",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ BACK",
                    callback_data="view_product",
                ),
            ],
        ]
    )


def get_buy_payment_keyboard(order_number: str) -> InlineKeyboardMarkup:
    """Payment instructions screen with I Have Paid, Payment Help, and Back."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 I HAVE PAID",
                    callback_data=f"i_have_paid:{order_number}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❓ PAYMENT HELP",
                    callback_data=f"payment_help:{order_number}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ BACK",
                    callback_data="view_product",
                ),
            ],
        ]
    )


def get_payment_help_keyboard(order_number: str) -> InlineKeyboardMarkup:
    """Payment guide screen with I Have Paid and Back to payment screen."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 I HAVE PAID",
                    callback_data=f"i_have_paid:{order_number}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ BACK",
                    callback_data=f"back_to_payment:{order_number}",
                ),
            ],
        ]
    )


def get_tx_hash_submission_keyboard(order_number: str) -> InlineKeyboardMarkup:
    """Back button displayed when prompting for TX Hash."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ BACK",
                    callback_data=f"back_to_payment:{order_number}",
                ),
            ],
        ]
    )


def get_download_pdf_keyboard(order_number: str) -> InlineKeyboardMarkup:
    """Inline download button sent upon payment approval."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📘 DOWNLOAD YOUR PDF",
                    callback_data=f"download_pdf:{order_number}",
                ),
            ],
        ]
    )


def get_rejection_keyboard() -> InlineKeyboardMarkup:
    """Presented to the buyer when payment could not be confirmed."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💬 CONTACT SUPPORT",
                    callback_data="contact_support",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔄 TRY AGAIN",
                    callback_data="view_product",
                ),
            ],
        ]
    )


def get_support_keyboard() -> InlineKeyboardMarkup:
    """Allows cancelling or returning from the support inquiry state."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ BACK",
                    callback_data="back_to_start",
                ),
            ],
        ]
    )


# Backward compatibility aliases
def get_order_payment_keyboard(order_number: str) -> InlineKeyboardMarkup:
    return get_buy_payment_keyboard(order_number)


def get_cancel_support_keyboard() -> InlineKeyboardMarkup:
    return get_support_keyboard()


def get_cancel_submission_keyboard(order_number: str) -> InlineKeyboardMarkup:
    return get_tx_hash_submission_keyboard(order_number)


def get_retry_keyboard() -> InlineKeyboardMarkup:
    return get_rejection_keyboard()
