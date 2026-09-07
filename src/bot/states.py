"""Finite State Machine (FSM) states for Buyer and Owner interaction flows."""

from aiogram.fsm.state import State, StatesGroup


class BuyerOrderStates(StatesGroup):
    """States traversed by a buyer during order checkout."""
    waiting_for_tx_hash = State()
    waiting_for_receipt = State()


class OwnerReviewStates(StatesGroup):
    """States traversed by the owner when entering custom rejection feedback."""
    waiting_for_custom_reason = State()


class BuyerSupportStates(StatesGroup):
    """States traversed by a buyer contacting support."""
    waiting_for_message = State()


class OwnerSupportStates(StatesGroup):
    """States traversed by the owner replying to a user's support message."""
    waiting_for_reply = State()
