"""Inline keyboards for the Owner review interface (100% Persian / Farsi)."""

from typing import Dict, List
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from src.database.models import BlockedUser

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


def get_owner_support_reply_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Action buttons on user support messages allowing the owner to reply or block."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✍️ پاسخ به این پیام",
                    callback_data=f"support_reply:{user_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚫 مسدود کردن این کاربر",
                    callback_data=f"block_user:{user_id}",
                )
            ],
        ]
    )


def get_owner_cancel_reply_keyboard() -> InlineKeyboardMarkup:
    """Button allowing the owner to cancel typing a reply."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔙 انصراف از پاسخ",
                    callback_data="cancel_support_reply",
                )
            ]
        ]
    )


def get_blocklist_keyboard(
    blocked_users: List[BlockedUser],
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    """Renders the inline buttons for blocked users and page controls."""
    inline_keyboard: List[List[InlineKeyboardButton]] = []

    # Individual button for each user to unblock
    for user in blocked_users:
        if user.username:
            label = f"🔓 @{user.username} ({user.user_id})"
        else:
            label = f"🔓 کاربر {user.user_id}"
        inline_keyboard.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"unblock_user:{user.user_id}:{page}",
                )
            ]
        )

    # Navigation row if more than 1 page
    if total_pages > 1:
        nav_row: List[InlineKeyboardButton] = []
        if page > 1:
            nav_row.append(
                InlineKeyboardButton(
                    text="⬅️ قبلی",
                    callback_data=f"blocklist_page:{page - 1}",
                )
            )
        nav_row.append(
            InlineKeyboardButton(
                text=f"📄 {page} / {total_pages}",
                callback_data="noop",
            )
        )
        if page < total_pages:
            nav_row.append(
                InlineKeyboardButton(
                    text="بعدی ➡️",
                    callback_data=f"blocklist_page:{page + 1}",
                )
            )
        inline_keyboard.append(nav_row)

    # Close button
    inline_keyboard.append(
        [
            InlineKeyboardButton(
                text="🔙 بستن لیست",
                callback_data="close_admin_panel",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def get_history_pagination_keyboard(
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    """Pagination navigation buttons for order history."""
    inline_keyboard: List[List[InlineKeyboardButton]] = []

    if total_pages > 1:
        nav_row: List[InlineKeyboardButton] = []
        if page > 1:
            nav_row.append(
                InlineKeyboardButton(
                    text="⬅️ قبلی",
                    callback_data=f"history_page:{page - 1}",
                )
            )
        nav_row.append(
            InlineKeyboardButton(
                text=f"📄 {page} / {total_pages}",
                callback_data="noop",
            )
        )
        if page < total_pages:
            nav_row.append(
                InlineKeyboardButton(
                    text="بعدی ➡️",
                    callback_data=f"history_page:{page + 1}",
                )
            )
        inline_keyboard.append(nav_row)

    inline_keyboard.append(
        [
            InlineKeyboardButton(
                text="🔙 بستن تاریخچه",
                callback_data="close_admin_panel",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

