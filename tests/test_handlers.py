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


@pytest.mark.asyncio
async def test_support_message_and_reply_flow(test_settings, fsm_storage):
    """Tests buyer contacting support and owner replying back."""
    from src.bot.handlers.buyer_handlers import process_support_message, start_contact_support
    from src.bot.handlers.owner_handlers import cb_support_reply, process_owner_support_reply
    from src.bot.states import BuyerSupportStates, OwnerSupportStates

    bot = AsyncMock()
    notifier = NotificationService(owner_id=test_settings.owner_id, developer_id=test_settings.developer_id)

    buyer_user = User(id=55555, is_bot=False, first_name="Mehdi_Test", username="test_buyer_handle")
    buyer_state = create_fsm_context(fsm_storage, user_id=buyer_user.id)

    # 1. Buyer triggers Contact Support
    cb_support = MagicMock(spec=CallbackQuery)
    cb_support.from_user = buyer_user
    cb_support.message = MagicMock()
    cb_support.message.answer = AsyncMock()
    cb_support.answer = AsyncMock()

    await start_contact_support(cb_support, buyer_state)
    assert await buyer_state.get_state() == BuyerSupportStates.waiting_for_message.state

    # 2. Buyer sends support message
    msg_support = MagicMock(spec=Message)
    msg_support.from_user = buyer_user
    msg_support.text = "Hello, how long does manual verification take?"
    msg_support.caption = None
    msg_support.answer = AsyncMock()

    await process_support_message(msg_support, buyer_state, notifier, bot)
    assert await buyer_state.get_state() is None

    # Verify Owner received notification in Persian
    assert bot.send_message.called
    owner_call = [c for c in bot.send_message.call_args_list if c.kwargs.get("chat_id") == test_settings.owner_id]
    assert len(owner_call) > 0
    owner_text = owner_call[-1].kwargs.get("text", "")
    assert "پیام جدید از بخش پشتیبانی" in owner_text
    assert "Hello, how long does manual verification take?" in owner_text

    # 3. Owner clicks Reply button
    owner_state = create_fsm_context(fsm_storage, user_id=test_settings.owner_id)
    cb_reply = MagicMock(spec=CallbackQuery)
    cb_reply.data = f"support_reply:{buyer_user.id}"
    cb_reply.message = MagicMock()
    cb_reply.message.answer = AsyncMock()
    cb_reply.answer = AsyncMock()

    await cb_support_reply(cb_reply, owner_state)
    assert await owner_state.get_state() == OwnerSupportStates.waiting_for_reply.state

    # 4. Owner types reply
    msg_owner_reply = MagicMock(spec=Message)
    msg_owner_reply.text = "Verification usually takes between 5 to 15 minutes."
    msg_owner_reply.caption = None
    msg_owner_reply.answer = AsyncMock()

    await process_owner_support_reply(msg_owner_reply, owner_state, notifier, bot)
    assert await owner_state.get_state() is None

    # Verify Buyer received the reply in English
    buyer_delivery = [c for c in bot.send_message.call_args_list if c.kwargs.get("chat_id") == buyer_user.id]
    assert len(buyer_delivery) > 0
    buyer_msg_text = buyer_delivery[-1].kwargs.get("text", "")
    assert "Support Team Response" in buyer_msg_text
    assert "Verification usually takes between 5 to 15 minutes." in buyer_msg_text


@pytest.mark.asyncio
async def test_owner_block_user_callback(order_service: OrderService):
    """Tests the owner blocking a user directly via the inline button on a support message."""
    from src.bot.handlers.owner_handlers import cb_block_user

    target_user_id = 88888
    assert await order_service.is_user_blocked(target_user_id) is False

    cb = MagicMock(spec=CallbackQuery)
    cb.data = f"block_user:{target_user_id}"
    cb.message = MagicMock()
    cb.message.answer = AsyncMock()
    cb.message.edit_reply_markup = AsyncMock()
    cb.answer = AsyncMock()

    await cb_block_user(cb, order_service)

    # User must now be blocked in DB
    assert await order_service.is_user_blocked(target_user_id) is True

    # Alert shown to admin
    cb.answer.assert_called_once_with("کاربر با موفقیت مسدود شد.", show_alert=True)
    cb.message.edit_reply_markup.assert_called_once_with(reply_markup=None)

    # Confirmation sent to admin chat
    assert cb.message.answer.called
    admin_msg = cb.message.answer.call_args[0][0]
    assert str(target_user_id) in admin_msg
    assert "مسدود شد" in admin_msg


@pytest.mark.asyncio
async def test_owner_blocklist_and_unblock_flow(order_service: OrderService, test_settings):
    """Tests the /blocklist pagination and unblocking with user notification dispatch."""
    from src.bot.handlers.owner_handlers import cb_blocklist_page, cb_unblock_user, cmd_blocklist

    bot = AsyncMock()
    notifier = NotificationService(owner_id=test_settings.owner_id, developer_id=test_settings.developer_id)

    # 1. When no blocked users exist
    empty_msg = MagicMock(spec=Message)
    empty_msg.answer = AsyncMock()
    await cmd_blocklist(empty_msg, order_service)
    assert "خالی است" in empty_msg.answer.call_args[0][0]

    # 2. Block 12 users to trigger pagination (> 10 items)
    for i in range(1, 13):
        await order_service.block_user(user_id=1000 + i, username=f"spammer_{i}", reason="Spam")

    assert await order_service.count_blocked_users() == 12

    # 3. Call /blocklist on page 1
    page1_msg = MagicMock(spec=Message)
    page1_msg.answer = AsyncMock()
    await cmd_blocklist(page1_msg, order_service)

    assert page1_msg.answer.called
    markup1 = page1_msg.answer.call_args.kwargs["reply_markup"]
    # 10 user buttons + 1 nav row + 1 close row = 12 rows
    assert len(markup1.inline_keyboard) == 12
    # Verify button labels format: @spammer_X (ID)
    first_btn_text = markup1.inline_keyboard[0][0].text
    assert "@spammer_" in first_btn_text
    assert "(" in first_btn_text

    # 4. Navigate to page 2
    cb_page2 = MagicMock(spec=CallbackQuery)
    cb_page2.data = "blocklist_page:2"
    cb_page2.message = MagicMock()
    cb_page2.message.edit_text = AsyncMock()
    cb_page2.answer = AsyncMock()

    await cb_blocklist_page(cb_page2, order_service)
    markup2 = cb_page2.message.edit_text.call_args.kwargs["reply_markup"]
    # 2 user buttons + 1 nav row + 1 close row = 4 rows
    assert len(markup2.inline_keyboard) == 4

    # 5. Unblock user 1001
    cb_unblock = MagicMock(spec=CallbackQuery)
    cb_unblock.data = "unblock_user:1001:1"
    cb_unblock.message = MagicMock()
    cb_unblock.message.edit_text = AsyncMock()
    cb_unblock.answer = AsyncMock()

    await cb_unblock_user(cb_unblock, order_service, notifier, bot)

    assert await order_service.is_user_blocked(1001) is False
    assert await order_service.count_blocked_users() == 11
    # Check alert shown
    cb_unblock.answer.assert_called_once_with("کاربر با موفقیت رفع مسدودیت شد و پیام به او ارسال گردید.", show_alert=True)
    # Check notification sent to user 1001
    assert bot.send_message.called
    user_notifs = [c for c in bot.send_message.call_args_list if c.kwargs.get("chat_id") == 1001]
    assert len(user_notifs) > 0
    assert "Account Reinstated" in user_notifs[0].kwargs.get("text", "")


@pytest.mark.asyncio
async def test_owner_history_flow(order_service: OrderService, test_settings):
    """Tests /history order listing with pagination (> 10 orders)."""
    from src.bot.handlers.owner_handlers import cb_history_page, cmd_history

    # 1. Empty history check
    msg_empty = MagicMock(spec=Message)
    msg_empty.answer = AsyncMock()
    await cmd_history(msg_empty, order_service)
    assert "هیچ سفارشی" in msg_empty.answer.call_args[0][0]

    # 2. Create 12 orders
    for i in range(1, 13):
        await order_service.create_order(
            user_id=2000 + i,
            username=f"buyer_hist_{i}",
            full_name=f"Buyer {i}",
            amount_usd=79.0,
            amount_ton=12.5,
            wallet_address="EQDtest_wallet",
        )

    # 3. Call /history on page 1
    msg_page1 = MagicMock(spec=Message)
    msg_page1.answer = AsyncMock()
    await cmd_history(msg_page1, order_service)

    text1 = msg_page1.answer.call_args[0][0]
    assert "تاریخچه سفارشات" in text1
    assert "صفحه 1 از 2" in text1
    assert "$79" in text1

    markup1 = msg_page1.answer.call_args.kwargs["reply_markup"]
    assert len(markup1.inline_keyboard) == 2  # Nav row + Close row

    # 4. Navigate to page 2
    cb_page2 = MagicMock(spec=CallbackQuery)
    cb_page2.data = "history_page:2"
    cb_page2.message = MagicMock()
    cb_page2.message.edit_text = AsyncMock()
    cb_page2.answer = AsyncMock()

    await cb_history_page(cb_page2, order_service)
    text2 = cb_page2.message.edit_text.call_args[0][0]
    assert "صفحه 2 از 2" in text2


@pytest.mark.asyncio
async def test_role_based_help_handler(test_settings):
    """Verifies that Owner/Dev receive admin help while buyers receive buyer help."""
    from src.bot.handlers.common_handlers import handle_help

    owner_user = User(id=test_settings.owner_id, is_bot=False, first_name="Owner")
    dev_user = User(id=test_settings.developer_id, is_bot=False, first_name="Dev")
    normal_user = User(id=999888777, is_bot=False, first_name="Customer")

    # 1. Owner requests help
    msg_owner = MagicMock(spec=Message)
    msg_owner.from_user = owner_user
    msg_owner.answer = AsyncMock()
    await handle_help(msg_owner, test_settings)
    owner_text = msg_owner.answer.call_args.kwargs.get("text", msg_owner.answer.call_args[0][0] if msg_owner.answer.call_args[0] else "")
    assert "/blocklist" in owner_text
    assert "/history" in owner_text

    # 2. Developer requests help
    msg_dev = MagicMock(spec=Message)
    msg_dev.from_user = dev_user
    msg_dev.answer = AsyncMock()
    await handle_help(msg_dev, test_settings)
    dev_text = msg_dev.answer.call_args.kwargs.get("text", msg_dev.answer.call_args[0][0] if msg_dev.answer.call_args[0] else "")
    assert "/blocklist" in dev_text
    assert "/history" in dev_text

    # 3. Normal Buyer requests help
    msg_buyer = MagicMock(spec=Message)
    msg_buyer.from_user = normal_user
    msg_buyer.answer = AsyncMock()
    await handle_help(msg_buyer, test_settings)
    buyer_text = msg_buyer.answer.call_args.kwargs.get("text", msg_buyer.answer.call_args[0][0] if msg_buyer.answer.call_args[0] else "")
    assert "/buy" in buyer_text
    assert "/info" in buyer_text
    assert "/contact" in buyer_text
    assert "/blocklist" not in buyer_text


@pytest.mark.asyncio
async def test_buyer_commands_buy_and_info(order_service: OrderService, test_settings, fsm_storage):
    """Verifies /buy creates/presents order and /info displays product overview."""
    from src.bot.handlers.buyer_handlers import cmd_buy, cmd_info

    buyer_user = User(id=333444, is_bot=False, first_name="Sam", username="sam_crypto")
    state = create_fsm_context(fsm_storage, user_id=buyer_user.id)

    # 1. /buy command
    msg_buy = MagicMock(spec=Message)
    msg_buy.from_user = buyer_user
    msg_buy.answer = AsyncMock()
    await cmd_buy(msg_buy, state, order_service, test_settings)

    assert msg_buy.answer.called
    buy_text = msg_buy.answer.call_args.kwargs.get("text", "")
    assert "Order Summary:" in buy_text
    assert "$79" in buy_text
    assert test_settings.ton_wallet_address in buy_text

    # 2. /info command
    msg_info = MagicMock(spec=Message)
    msg_info.from_user = buyer_user
    msg_info.answer = AsyncMock()
    await cmd_info(msg_info, test_settings)

    assert msg_info.answer.called
    info_text = msg_info.answer.call_args.kwargs.get("text", "")
    assert "AI Side Hustle" in info_text
    assert "$79" in info_text


@pytest.mark.asyncio
async def test_proof_submission_command_locking_and_emoji_reactions(
    order_service: OrderService,
    test_settings,
    fsm_storage,
):
    """Verifies that commands are locked during proof submission with ✋,

    invalid/duplicate hashes trigger 😭, and valid submissions trigger 👍.
    """
    from src.bot.handlers.buyer_handlers import (
        intercept_locked_commands,
        process_receipt,
        process_tx_hash,
    )
    from src.bot.middlewares.reaction_middleware import (
        SOB_EMOJI,
        STOP_EMOJI,
        THUMBS_UP_EMOJI,
    )

    buyer_user = User(id=990011, is_bot=False, first_name="ReactionTester")
    state = create_fsm_context(fsm_storage, user_id=buyer_user.id)

    order = await order_service.create_order(
        user_id=buyer_user.id,
        username="tester_rx",
        full_name="Tester",
        amount_usd=79.0,
        amount_ton=12.5,
        wallet_address="EQDtest_wallet",
    )
    await state.set_state(BuyerOrderStates.waiting_for_tx_hash)
    await state.update_data(order_number=order.order_number)

    # 1. User attempts to execute a command (/info) during proof submission
    cmd_msg = MagicMock(spec=Message)
    cmd_msg.text = "/info"
    cmd_msg.answer = AsyncMock()
    cmd_msg.react = AsyncMock()

    await intercept_locked_commands(cmd_msg, state)

    # Must react with ✋
    assert cmd_msg.react.called
    assert cmd_msg.react.call_args[0][0][0].emoji == STOP_EMOJI
    # Must warn user that commands are locked and provide cancel submission button
    assert cmd_msg.answer.called
    lock_text = cmd_msg.answer.call_args[0][0]
    assert "Commands are locked" in lock_text
    markup = cmd_msg.answer.call_args.kwargs.get("reply_markup")
    assert "Cancel Submission" in markup.inline_keyboard[0][0].text

    # 2. User enters invalid short hash -> reacts with 😭
    bad_hash_msg = MagicMock(spec=Message)
    bad_hash_msg.text = "short"
    bad_hash_msg.answer = AsyncMock()
    bad_hash_msg.react = AsyncMock()

    await process_tx_hash(bad_hash_msg, state, order_service)

    assert bad_hash_msg.react.called
    assert bad_hash_msg.react.call_args[0][0][0].emoji == SOB_EMOJI
    assert "valid transaction hash" in bad_hash_msg.answer.call_args[0][0]

    # 3. User enters a duplicate hash -> reacts with 😭
    # First, simulate another order with this hash in DB
    other_order = await order_service.create_order(
        user_id=111222,
        username="other",
        full_name="Other",
        amount_usd=79.0,
        amount_ton=12.5,
        wallet_address="EQDtest_wallet",
    )
    dup_hash = "already_used_tx_hash_1234567890"
    await order_service.submit_tx_hash(other_order.order_number, dup_hash)

    dup_hash_msg = MagicMock(spec=Message)
    dup_hash_msg.text = dup_hash
    dup_hash_msg.answer = AsyncMock()
    dup_hash_msg.react = AsyncMock()

    await process_tx_hash(dup_hash_msg, state, order_service)

    assert dup_hash_msg.react.called
    assert dup_hash_msg.react.call_args[0][0][0].emoji == SOB_EMOJI
    assert "Duplicate Transaction Detected" in dup_hash_msg.answer.call_args[0][0]

    # 4. User enters valid hash -> reacts with 👍
    valid_hash_msg = MagicMock(spec=Message)
    valid_hash_msg.text = "fresh_unique_tx_hash_abcdef9876543210"
    valid_hash_msg.answer = AsyncMock()
    valid_hash_msg.react = AsyncMock()

    await process_tx_hash(valid_hash_msg, state, order_service)

    assert valid_hash_msg.react.called
    assert valid_hash_msg.react.call_args[0][0][0].emoji == THUMBS_UP_EMOJI
    assert await state.get_state() == BuyerOrderStates.waiting_for_receipt.state

    # 5. User uploads valid receipt screenshot -> reacts with 👍
    notifier = NotificationService(owner_id=test_settings.owner_id, developer_id=test_settings.developer_id)
    bot = AsyncMock()

    photo_msg = MagicMock(spec=Message)
    photo_msg.photo = [MagicMock(file_id="photo_123")]
    photo_msg.document = None
    photo_msg.answer = AsyncMock()
    photo_msg.react = AsyncMock()

    await process_receipt(photo_msg, state, order_service, notifier, bot)

    assert photo_msg.react.called
    assert photo_msg.react.call_args[0][0][0].emoji == THUMBS_UP_EMOJI
    assert await state.get_state() is None



