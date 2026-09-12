"""Integration and event simulation tests for buyer and owner handlers."""

from unittest.mock import AsyncMock, MagicMock
import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage, StorageKey
from aiogram.types import CallbackQuery, Message, User

from src.bot.handlers.buyer_handlers import (
    cb_back_to_payment,
    cb_back_to_start,
    cb_buy_now,
    cb_cancel_order,
    cb_download_pdf,
    cb_i_have_paid,
    cb_more_details,
    cb_payment_help,
    cb_view_product,
    cmd_buy,
    cmd_info,
    cmd_start,
    intercept_locked_commands,
    process_support_message,
    process_tx_hash,
    start_contact_support,
)
from src.bot.handlers.owner_handlers import (
    cb_block_user,
    cb_blocklist_page,
    cb_history_page,
    cb_owner_approve,
    cb_owner_reject,
    cb_support_reply,
    cb_unblock_user,
    cmd_blocklist,
    cmd_history,
    process_owner_support_reply,
)
from src.bot.middlewares.reaction_middleware import (
    SOB_EMOJI,
    STOP_EMOJI,
    THUMBS_UP_EMOJI,
)
from src.bot.states import BuyerOrderStates, BuyerSupportStates, OwnerSupportStates
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
async def test_cmd_start_displays_welcome(fsm_storage):
    """Verifies that /start presents the Step 1 welcome text and keyboard."""
    message = MagicMock(spec=Message)
    message.answer = AsyncMock()
    state = create_fsm_context(fsm_storage)

    await cmd_start(message, state)

    assert message.answer.called
    call_args = message.answer.call_args
    text = call_args.kwargs.get("text", "")
    assert "Welcome!" in text
    assert "AI Side Hustle Launch System" in text
    assert "24-Part Launch System" in text


@pytest.mark.asyncio
async def test_navigation_screens(fsm_storage):
    """Tests navigation between Step 1 (Start), Step 2 (Product), and Step 3 (More Details)."""
    state = create_fsm_context(fsm_storage)

    # 1. Click '🧠 AI Side Hustle Launch System'
    cb_prod = MagicMock(spec=CallbackQuery)
    cb_prod.message = MagicMock()
    cb_prod.message.edit_text = AsyncMock()
    cb_prod.answer = AsyncMock()

    await cb_view_product(cb_prod, state)
    text_prod = cb_prod.message.edit_text.call_args.kwargs.get("text", "")
    assert "Visual Pro Edition" in text_prod
    assert "Regular Price: ~~$99~~" in text_prod
    assert "Launch Price: $79" in text_prod

    # 2. Click '📖 MORE DETAILS'
    cb_details = MagicMock(spec=CallbackQuery)
    cb_details.message = MagicMock()
    cb_details.message.edit_text = AsyncMock()
    cb_details.answer = AsyncMock()

    await cb_more_details(cb_details, state)
    text_details = cb_details.message.edit_text.call_args.kwargs.get("text", "")
    assert "What's Inside?" in text_details
    assert "Opportunity Engine" in text_details
    assert "12-Month Master Plan" in text_details

    # 3. Click '⬅️ BACK' to Start
    cb_back = MagicMock(spec=CallbackQuery)
    cb_back.message = MagicMock()
    cb_back.message.edit_text = AsyncMock()
    cb_back.answer = AsyncMock()

    await cb_back_to_start(cb_back, state)
    text_start = cb_back.message.edit_text.call_args.kwargs.get("text", "")
    assert "Welcome!" in text_start


@pytest.mark.asyncio
async def test_full_buyer_to_owner_flow(order_service: OrderService, test_settings, fsm_storage):
    """Tests the complete lifecycle:
    1. Buyer clicks Buy Now -> Step 4 payment screen (79 USDT, TON Network)
    2. Buyer clicks I Have Paid -> Step 6 asks for TX Hash
    3. Buyer sends TX Hash -> Step 7 under review, Owner receives Persian review card
    4. Owner approves payment -> Buyer receives Step 9 with download button
    5. Buyer clicks [📘 DOWNLOAD YOUR PDF] -> PDF delivered, order marked DELIVERED
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
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    await cb_buy_now(callback, buyer_state, order_service, test_settings)

    call_args = callback.message.edit_text.call_args
    prompt_text = call_args.kwargs.get("text", "")
    assert "Secure Your Copy" in prompt_text
    assert "79 USDT" in prompt_text
    assert "USDT on the TON Network" in prompt_text
    assert test_settings.ton_wallet_address in prompt_text

    # Retrieve generated order
    active_order = await order_service.get_active_order_by_user(buyer_user.id)
    assert active_order is not None
    order_num = active_order.order_number

    # Step 2: Click I HAVE PAID
    cb_paid = MagicMock(spec=CallbackQuery)
    cb_paid.data = f"i_have_paid:{order_num}"
    cb_paid.message = MagicMock()
    cb_paid.message.edit_text = AsyncMock()
    cb_paid.answer = AsyncMock()

    await cb_i_have_paid(cb_paid, buyer_state, order_service)
    curr_state = await buyer_state.get_state()
    assert curr_state == BuyerOrderStates.waiting_for_tx_hash.state
    submitted_text = cb_paid.message.edit_text.call_args.kwargs.get("text", "")
    assert "Payment Submitted" in submitted_text
    assert "Please send your transaction hash (TX Hash) below." in submitted_text

    # Step 3: Send TX hash
    msg_hash = MagicMock(spec=Message)
    msg_hash.text = "ton_hash_sample_abcdef123456789"
    msg_hash.answer = AsyncMock()
    msg_hash.react = AsyncMock()

    notifier = NotificationService(owner_id=test_settings.owner_id, developer_id=test_settings.developer_id)
    await process_tx_hash(msg_hash, buyer_state, order_service, notifier, bot)

    # State cleared and order is directly UNDER_REVIEW
    assert await buyer_state.get_state() is None
    order_under_review = await order_service.get_order_by_number(order_num)
    assert order_under_review.status == OrderStatus.UNDER_REVIEW.value
    assert order_under_review.tx_hash == "ton_hash_sample_abcdef123456789"

    # Verify Buyer received Step 7 (Payment Under Review)
    assert msg_hash.answer.called
    review_msg_text = msg_hash.answer.call_args.kwargs.get("text", "")
    assert "Payment Under Review" in review_msg_text
    assert "Your payment is now being verified." in review_msg_text

    # Verify Owner received card in Persian
    assert bot.send_message.called
    owner_call = [c for c in bot.send_message.call_args_list if c.kwargs.get("chat_id") == test_settings.owner_id]
    assert len(owner_call) > 0
    owner_card = owner_call[-1].kwargs.get("text", "")
    assert "بررسی پرداخت جدید" in owner_card
    assert "ton_hash_sample_abcdef123456789" in owner_card

    # Step 4: Owner Approves
    cb_approve = MagicMock(spec=CallbackQuery)
    cb_approve.data = f"owner_approve:{order_num}"
    cb_approve.message = MagicMock()
    cb_approve.message.answer = AsyncMock()
    cb_approve.message.edit_reply_markup = AsyncMock()
    cb_approve.answer = AsyncMock()

    await cb_owner_approve(cb_approve, order_service, notifier, bot)

    # Order should now be APPROVED (awaiting buyer download click)
    order_approved = await order_service.get_order_by_number(order_num)
    assert order_approved.status == OrderStatus.APPROVED.value

    # Verify Buyer received Step 9 with download button
    buyer_calls = [c for c in bot.send_message.call_args_list if c.kwargs.get("chat_id") == buyer_user.id]
    assert len(buyer_calls) > 0
    buyer_approval_text = buyer_calls[-1].kwargs.get("text", "")
    assert "Payment Confirmed!" in buyer_approval_text
    assert "Download your product below:" in buyer_approval_text

    # Step 5: Buyer clicks [📘 DOWNLOAD YOUR PDF]
    cb_download = MagicMock(spec=CallbackQuery)
    cb_download.data = f"download_pdf:{order_num}"
    cb_download.from_user = buyer_user
    cb_download.message = MagicMock()
    cb_download.message.answer = AsyncMock()
    cb_download.answer = AsyncMock()

    delivery = DeliveryService(session=order_service.session, pdf_path=test_settings.pdf_file_path)
    await cb_download_pdf(cb_download, order_service, delivery, bot)

    # Order should now be marked DELIVERED
    order_delivered = await order_service.get_order_by_number(order_num)
    assert order_delivered.status == OrderStatus.DELIVERED.value
    assert bot.send_document.called


@pytest.mark.asyncio
async def test_owner_rejection_flow(order_service: OrderService, test_settings):
    """Tests the direct one-click rejection flow resulting in Step 11 message with support buttons."""
    order = await order_service.create_order(
        user_id=777,
        username="buyer_reject",
        full_name="Buyer Reject",
        amount_usd=79.0,
        amount_ton=12.5,
        wallet_address=test_settings.ton_wallet_address,
    )
    await order_service.submit_tx_hash(order.order_number, "hash_to_reject_12345")

    bot = AsyncMock()
    notifier = NotificationService(owner_id=test_settings.owner_id, developer_id=test_settings.developer_id)

    cb_reject = MagicMock(spec=CallbackQuery)
    cb_reject.data = f"owner_reject:{order.order_number}"
    cb_reject.message = MagicMock()
    cb_reject.message.answer = AsyncMock()
    cb_reject.message.edit_reply_markup = AsyncMock()
    cb_reject.answer = AsyncMock()

    await cb_owner_reject(cb_reject, order_service, notifier, bot)

    rejected_order = await order_service.get_order_by_number(order.order_number)
    assert rejected_order.status == OrderStatus.REJECTED.value

    # Verify Buyer received Step 11 English notification with Support / Try Again
    assert bot.send_message.called
    call_matches = [
        c for c in bot.send_message.call_args_list if c.kwargs.get("chat_id") == 777
    ]
    assert len(call_matches) > 0
    buyer_text = call_matches[0].kwargs.get("text", "")
    assert "Payment Could Not Be Confirmed" in buyer_text
    assert "You sent the correct amount" in buyer_text
    assert "You used the TON Network" in buyer_text

    markup = call_matches[0].kwargs.get("reply_markup")
    assert markup is not None
    assert "CONTACT SUPPORT" in markup.inline_keyboard[0][0].text
    assert "TRY AGAIN" in markup.inline_keyboard[1][0].text


@pytest.mark.asyncio
async def test_payment_help_and_back_navigation(test_settings, fsm_storage, order_service: OrderService):
    """Tests viewing payment help and returning back to the payment instructions."""
    order = await order_service.create_order(
        user_id=444,
        username="help_user",
        full_name="Help User",
        amount_usd=79.0,
        amount_ton=12.5,
        wallet_address=test_settings.ton_wallet_address,
    )
    state = create_fsm_context(fsm_storage, user_id=444)

    # 1. Click PAYMENT HELP
    cb_help = MagicMock(spec=CallbackQuery)
    cb_help.data = f"payment_help:{order.order_number}"
    cb_help.message = MagicMock()
    cb_help.message.edit_text = AsyncMock()
    cb_help.answer = AsyncMock()

    await cb_payment_help(cb_help)
    help_text = cb_help.message.edit_text.call_args.kwargs.get("text", "")
    assert "Payment Help" in help_text
    assert "Tonkeeper" in help_text
    assert "Make sure the network is TON" in help_text

    # 2. Click BACK
    cb_back = MagicMock(spec=CallbackQuery)
    cb_back.data = f"back_to_payment:{order.order_number}"
    cb_back.message = MagicMock()
    cb_back.message.edit_text = AsyncMock()
    cb_back.answer = AsyncMock()

    await cb_back_to_payment(cb_back, state, order_service, test_settings)
    back_text = cb_back.message.edit_text.call_args.kwargs.get("text", "")
    assert "Secure Your Copy" in back_text
    assert "79 USDT" in back_text


@pytest.mark.asyncio
async def test_support_message_and_reply_flow(test_settings, fsm_storage):
    """Tests buyer contacting support and owner replying back."""
    bot = AsyncMock()
    notifier = NotificationService(owner_id=test_settings.owner_id, developer_id=test_settings.developer_id)

    buyer_user = User(id=55555, is_bot=False, first_name="Mehdi_Test", username="test_buyer_handle")
    buyer_state = create_fsm_context(fsm_storage, user_id=buyer_user.id)

    # 1. Buyer triggers Contact Support
    cb_support = MagicMock(spec=CallbackQuery)
    cb_support.from_user = buyer_user
    cb_support.message = MagicMock()
    cb_support.message.edit_text = AsyncMock()
    cb_support.answer = AsyncMock()

    await start_contact_support(cb_support, buyer_state)
    assert await buyer_state.get_state() == BuyerSupportStates.waiting_for_message.state
    support_text = cb_support.message.edit_text.call_args.kwargs.get("text", "")
    assert "Support" in support_text
    assert "Never send your wallet recovery phrase" in support_text

    # 2. Buyer sends support message
    msg_support = MagicMock(spec=Message)
    msg_support.from_user = buyer_user
    msg_support.text = "Hello, how long does manual verification take?"
    msg_support.caption = None
    msg_support.answer = AsyncMock()
    msg_support.react = AsyncMock()

    await process_support_message(msg_support, buyer_state, notifier, bot)
    assert await buyer_state.get_state() is None
    assert msg_support.react.called

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
    cb.answer.assert_called_once_with("کاربر با موفقیت مسدود شد.", show_alert=True)
    cb.message.edit_reply_markup.assert_called_once_with(reply_markup=None)

    assert cb.message.answer.called
    admin_msg = cb.message.answer.call_args[0][0]
    assert str(target_user_id) in admin_msg
    assert "مسدود شد" in admin_msg


@pytest.mark.asyncio
async def test_owner_blocklist_and_unblock_flow(order_service: OrderService, test_settings):
    """Tests the /blocklist pagination and unblocking with user notification dispatch."""
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
    assert len(markup1.inline_keyboard) == 12

    # 4. Navigate to page 2
    cb_page2 = MagicMock(spec=CallbackQuery)
    cb_page2.data = "blocklist_page:2"
    cb_page2.message = MagicMock()
    cb_page2.message.edit_text = AsyncMock()
    cb_page2.answer = AsyncMock()

    await cb_blocklist_page(cb_page2, order_service)
    markup2 = cb_page2.message.edit_text.call_args.kwargs["reply_markup"]
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
    cb_unblock.answer.assert_called_once_with("کاربر با موفقیت رفع مسدودیت شد و پیام به او ارسال گردید.", show_alert=True)
    assert bot.send_message.called


@pytest.mark.asyncio
async def test_owner_history_flow(order_service: OrderService):
    """Tests /history order listing with pagination (> 10 orders)."""
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
    buyer_user = User(id=333444, is_bot=False, first_name="Sam", username="sam_crypto")
    state = create_fsm_context(fsm_storage, user_id=buyer_user.id)

    # 1. /buy command
    msg_buy = MagicMock(spec=Message)
    msg_buy.from_user = buyer_user
    msg_buy.answer = AsyncMock()
    await cmd_buy(msg_buy, state, order_service, test_settings)

    assert msg_buy.answer.called
    buy_text = msg_buy.answer.call_args.kwargs.get("text", "")
    assert "Secure Your Copy" in buy_text
    assert "79 USDT" in buy_text
    assert test_settings.ton_wallet_address in buy_text

    # 2. /info command
    msg_info = MagicMock(spec=Message)
    msg_info.from_user = buyer_user
    msg_info.answer = AsyncMock()
    await cmd_info(msg_info, state)

    assert msg_info.answer.called
    info_text = msg_info.answer.call_args.kwargs.get("text", "")
    assert "AI Side Hustle" in info_text
    assert "Launch Price: $79" in info_text


@pytest.mark.asyncio
async def test_proof_submission_command_locking_and_emoji_reactions(
    order_service: OrderService,
    test_settings,
    fsm_storage,
):
    """Verifies that commands are locked during proof submission with ✋,
    invalid/duplicate hashes trigger 😭, and valid submissions trigger 👍.
    """
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
    assert cmd_msg.answer.called
    lock_text = cmd_msg.answer.call_args[0][0]
    assert "Commands are locked" in lock_text

    # 2. User enters invalid short hash -> reacts with 😭
    bad_hash_msg = MagicMock(spec=Message)
    bad_hash_msg.text = "short"
    bad_hash_msg.answer = AsyncMock()
    bad_hash_msg.react = AsyncMock()

    notifier = NotificationService(owner_id=test_settings.owner_id, developer_id=test_settings.developer_id)
    bot = AsyncMock()

    await process_tx_hash(bad_hash_msg, state, order_service, notifier, bot)

    assert bad_hash_msg.react.called
    assert bad_hash_msg.react.call_args[0][0][0].emoji == SOB_EMOJI
    assert "valid transaction hash" in bad_hash_msg.answer.call_args[0][0]

    # 3. User enters a duplicate hash -> accepted with 👍
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

    await process_tx_hash(dup_hash_msg, state, order_service, notifier, bot)

    assert dup_hash_msg.react.called
    assert dup_hash_msg.react.call_args[0][0][0].emoji == THUMBS_UP_EMOJI
    assert await state.get_state() is None

    # 4. User enters valid hash -> reacts with 👍
    order3 = await order_service.create_order(
        user_id=333444,
        username="user3",
        full_name="User Three",
        amount_usd=79.0,
        amount_ton=12.5,
        wallet_address="EQDtest_wallet",
    )
    await state.set_state(BuyerOrderStates.waiting_for_tx_hash)
    await state.update_data(order_number=order3.order_number)

    valid_hash_msg = MagicMock(spec=Message)
    valid_hash_msg.text = "fresh_unique_tx_hash_abcdef9876543210"
    valid_hash_msg.answer = AsyncMock()
    valid_hash_msg.react = AsyncMock()

    await process_tx_hash(valid_hash_msg, state, order_service, notifier, bot)

    assert valid_hash_msg.react.called
    assert valid_hash_msg.react.call_args[0][0][0].emoji == THUMBS_UP_EMOJI
    # State should now be cleared
    assert await state.get_state() is None
