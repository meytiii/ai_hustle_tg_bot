"""Inline keyboards for the international buyer flow (100% English)."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_start_keyboard() -> InlineKeyboardMarkup:
    """Keyboard on the welcome screen with the primary purchase action and support."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🚀 Buy Now", callback_data="buy_now"),
            ],
            [
                InlineKeyboardButton(text="💬 Contact Support", callback_data="contact_support"),
            ],
        ]
    )


def get_cancel_support_keyboard() -> InlineKeyboardMarkup:
    """Allows the user to cancel contacting support."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_support"),
            ]
        ]
    )


def get_order_payment_keyboard(order_number: str) -> InlineKeyboardMarkup:
    """Keyboard presented alongside payment instructions."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 I Have Paid — Submit Proof",
                    callback_data=f"submit_proof:{order_number}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Cancel Order",
                    callback_data=f"cancel_order:{order_number}",
                )
            ],
        ]
    )


def get_cancel_submission_keyboard(order_number: str) -> InlineKeyboardMarkup:
    """Allows the user to cancel their order during receipt submission."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Cancel Order",
                    callback_data=f"cancel_order:{order_number}",
                )
            ]
        ]
    )


def get_retry_keyboard() -> InlineKeyboardMarkup:
    """Presented when an order has been cancelled or rejected."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Start New Order",
                    callback_data="buy_now",
                )
            ]
        ]
    )
