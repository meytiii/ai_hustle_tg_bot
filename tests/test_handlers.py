"""Integration and event simulation tests for buyer and owner handlers."""

from unittest.mock import AsyncMock, MagicMock
import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage, StorageKey
from aiogram.types import CallbackQuery, Message, PhotoSize, User

from src.bot.handlers.buyer_handlers import (
    cb_buy_now,
    cb_cancel_order,
    cb_submit_proof,
    cmd_start,
    process_receipt,
    process_tx_hash,
)
from src.bot.handlers.owner_handlers import cb_owner_approve, cb_reject_preset, process_custom_rejection_reason
from src.bot.states import BuyerOrderStates, OwnerReviewStates
from src.config import Settings
from src.database.models import OrderStatus
from src.services.delivery_service import DeliveryService
from src.services.notification_service import NotificationService
from src.services.order_service import OrderService


@pytest.fixture
def test_settings():
    return Settings(
        bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        ton_wallet_address="EQDtest_wallet_address_12345",
        price_usd=79.0,
        original_price_usd=100.0,
        price_ton=12.5,
        owner_id=72101760,
        developer_id=347382968,
        order_timeout_minutes=120,
    )


@pytest.fixture
def fsm_storage():
    return MemoryStorage()


def create_fsm_context(storage: MemoryStorage, user_id: int = 12345, chat_id: int = 12345) -> FSMContext:
    key = StorageKey(bot_id=123456, chat_id=chat_id, user_id=user_id)
    return FSMContext(storage=storage, key=key)


@pytest.mark.asyncio
async def test_cmd_start_displays_promotion(test_settings, fsm_storage):
    """Verifies that /start presents the AI Side Hustle guide with promotional price."""
    message = MagicMock(spec=Message)
    message.answer = AsyncMock()
    state = create_fsm_context(fsm_storage)

    await cmd_start(message, state, test_settings)

    assert message.answer.called
    call_args = message.answer.call_args
    text = call_args.kwargs.get("text", "")
    assert "Welcome" in text


@pytest.mark.asyncio
async def test_full_buyer_to_owner_flow(order_service: OrderService, test_settings, fsm_storage):
    """Tests the complete lifecycle:
    1. Buyer clicks Buy Now
    2. Buyer initiates proof submission
    3. Buyer submits TX hash
    4. Buyer submits receipt photo
    5. Owner approves order
    6. Delivery is completed
    """
    buyer_user = User(id=88888, is_bot=False, first_name="Buyer", username="test_buyer")
    buyer_state = create_fsm_context(fsm_storage, user_id=buyer_user.id)

    # Mock Bot
    bot = AsyncMock()
    mock_doc_msg = MagicMock()
    mock_doc_msg.document.file_id = "cached_telegram_file_id_999"
    bot.send_document.return_value = mock_doc_msg

    # Step 1: Buy Now
    callback = MagicMock(spec=CallbackQuery)
    callback.from_user = buyer_user
    callback.message = MagicMock()
    callback.message.answer = AsyncMock()
    callback.answer = AsyncMock()

    await cb_buy_now(callback, buyer_state, order_service, test_settings)

    call_args = callback.message.answer.call_args
    prompt_text = call_args.kwargs.get("text", "")
    assert "Send TON to the following wallet address" in prompt_text
    assert "IMPORTANT — BEFORE YOU PAY" in prompt_text
    assert test_settings.ton_wallet_address in prompt_text

    # Retrieve generated order
    active_order = await order_service.get_active_order_by_user(buyer_user.id)
    assert active_order is not None
    order_num = active_order.order_number

    # Step 2: Submit Proof button
    cb_proof = MagicMock(spec=CallbackQuery)
    cb_proof.data = f"submit_proof:{order_num}"
    cb_proof.message = MagicMock()
    cb_proof.message.answer = AsyncMock()
    cb_proof.answer = AsyncMock()

    await cb_submit_proof(cb_proof, buyer_state, order_service)
    curr_state = await buyer_state.get_state()
    assert curr_state == BuyerOrderStates.waiting_for_tx_hash.state

    # Step 3: Send TX hash
    msg_hash = MagicMock(spec=Message)
    msg_hash.text = "ton_hash_sample_abcdef123456789"
    msg_hash.answer = AsyncMock()

    await process_tx_hash(msg_hash, buyer_state, order_service)
    curr_state = await buyer_state.get_state()
    assert curr_state == BuyerOrderStates.waiting_for_receipt.state

    # Step 4: Send Receipt screenshot
    msg_receipt = MagicMock(spec=Message)
    msg_receipt.photo = [PhotoSize(file_id="receipt_photo_id_123", file_unique_id="u123", width=800, height=600)]
    msg_receipt.document = None
    msg_receipt.answer = AsyncMock()

    notifier = NotificationService(owner_id=test_settings.owner_id, developer_id=test_settings.developer_id)
    await process_receipt(msg_receipt, buyer_state, order_service, notifier, bot)

    # Order should now be UNDER_REVIEW
    order_under_review = await order_service.get_order_by_number(order_num)
    assert order_under_review.status == OrderStatus.UNDER_REVIEW.value
    assert order_under_review.tx_hash == "ton_hash_sample_abcdef123456789"
    assert order_under_review.receipt_file_id == "receipt_photo_id_123"

    # Step 5: Owner Approves
    cb_approve = MagicMock(spec=CallbackQuery)
    cb_approve.data = f"owner_approve:{order_num}"
    cb_approve.message = MagicMock()
    cb_approve.message.answer = AsyncMock()
    cb_approve.message.edit_reply_markup = AsyncMock()
    cb_approve.answer = AsyncMock()

    delivery = DeliveryService(session=order_service.session, pdf_path=test_settings.pdf_file_path)

    await cb_owner_approve(cb_approve, order_service, delivery, notifier, bot)

    # Order should now be DELIVERED
    order_delivered = await order_service.get_order_by_number(order_num)
    assert order_delivered.status == OrderStatus.DELIVERED.value

    # Verifying file delivery was called
    assert bot.send_document.called
    doc_call = bot.send_document.call_args
    assert doc_call.kwargs.get("chat_id") == buyer_user.id
    assert "AI Side Hustle" in doc_call.kwargs.get("caption", "")


@pytest.mark.asyncio
async def test_owner_rejection_preset_flow(order_service: OrderService, test_settings):
    """Tests the rejection flow with preset reasons."""
    order = await order_service.create_order(
        user_id=777,
        username="buyer_reject",
        full_name="Buyer Reject",
        amount_usd=79.0,
        amount_ton=12.5,
        wallet_address=test_settings.ton_wallet_address,
    )
    await order_service.submit_tx_hash(order.order_number, "hash_to_reject")
    await order_service.submit_receipt(order.order_number, "photo_to_reject")

    bot = AsyncMock()
    notifier = NotificationService(owner_id=test_settings.owner_id, developer_id=test_settings.developer_id)

    cb_reject = MagicMock(spec=CallbackQuery)
    cb_reject.data = f"reject_preset:{order.order_number}:not_found"
    cb_reject.message = MagicMock()
    cb_reject.message.answer = AsyncMock()
    cb_reject.message.edit_reply_markup = AsyncMock()
    cb_reject.answer = AsyncMock()

    await cb_reject_preset(cb_reject, order_service, notifier, bot)

    rejected_order = await order_service.get_order_by_number(order.order_number)
    assert rejected_order.status == OrderStatus.REJECTED.value
    assert "could not be located on the TON blockchain" in rejected_order.rejection_reason

    # Verify Buyer received the English notification
    assert bot.send_message.called
    call_matches = [
        c for c in bot.send_message.call_args_list if c.kwargs.get("chat_id") == 777
    ]
    assert len(call_matches) > 0
    buyer_text = call_matches[0].kwargs.get("text", "")
    assert "could not be located on the TON blockchain" in buyer_text
    assert f"#{order.order_number}" in buyer_text
