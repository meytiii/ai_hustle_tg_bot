"""Inline keyboards for the Owner review interface (100% Persian / Farsi)."""

from typing import Dict
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# English explanations delivered to the buyer when a preset rejection reason is chosen by the owner
REJECTION_PRESET_EXPLANATIONS_EN: Dict[str, str] = {
    "not_found": "Your payment transaction hash could not be located on the TON blockchain. Please verify your transaction and try again.",
    "bad_amount": "The transferred TON amount does not match the product launch discount price ($79).",
    "bad_receipt": "The payment screenshot receipt provided was unreadable, invalid, or corrupted.",
}


def get_owner_review_keyboard(order_number: str) -> InlineKeyboardMarkup:
    """Action buttons attached to incoming order review notifications."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ تایید و ارسال فایل به خریدار",
                    callback_data=f"owner_approve:{order_number}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ رد سفارش",
                    callback_data=f"owner_reject_menu:{order_number}",
                )
            ],
        ]
    )


def get_owner_reject_presets_keyboard(order_number: str) -> InlineKeyboardMarkup:
    """Preset rejection reasons and custom note option displayed to the Owner."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔍 تراکنش در بلاکچین یافت نشد",
                    callback_data=f"reject_preset:{order_number}:not_found",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📉 مبلغ واریزی اشتباه است",
                    callback_data=f"reject_preset:{order_number}:bad_amount",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🖼️ اسکرین‌شات نامعتبر یا ناخوانا است",
                    callback_data=f"reject_preset:{order_number}:bad_receipt",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✍️ تایپ دلیل سفارشی...",
                    callback_data=f"reject_custom:{order_number}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 انصراف / بازگشت به بررسی",
                    callback_data=f"reject_back:{order_number}",
                )
            ],
        ]
    )
