"""Tests for DeliveryService caching, NotificationService bilingual messages, and CodeGenerator."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Order, OrderStatus, utc_now
from src.services.delivery_service import DeliveryError, DeliveryService
from src.services.notification_service import NotificationService
from src.utils.code_generator import UNAMBIGUOUS_CHARS, generate_order_number


@pytest.mark.asyncio
async def test_code_generator_uniqueness_and_charset():
    """Verifies that generated order codes adhere to ASH-XXXXX format with only unambiguous characters."""
    generated = set()
    for _ in range(200):
        code = generate_order_number(prefix="ASH", length=5)
        assert code.startswith("ASH-")
        assert len(code) == 9
        suffix = code.split("-")[1]
        for char in suffix:
            assert char in UNAMBIGUOUS_CHARS
            assert char not in ("0", "O", "1", "I")  # Strict check
        generated.add(code)

    assert len(generated) == 200  # No collisions in small batch


@pytest.mark.asyncio
async def test_delivery_service_file_id_caching(db_session: AsyncSession):
    """Verifies that DeliveryService properly stores and retrieves cached Telegram file IDs."""
    delivery_service = DeliveryService(session=db_session, pdf_path="./assets/AI_Side_Hustle.pdf")

    # Initially None
    cached = await delivery_service.get_cached_file_id()
    assert cached is None

    # Cache a mock file_id
    mock_file_id = "BAACAgIAAxkBAAICam..."
    await delivery_service.set_cached_file_id(mock_file_id)

    # Retrieve again
    retrieved = await delivery_service.get_cached_file_id()
    assert retrieved == mock_file_id


@pytest.mark.asyncio
async def test_delivery_service_missing_file_error(db_session: AsyncSession):
    """Verifies DeliveryService raises DeliveryError if local file does not exist when not cached."""
    delivery_service = DeliveryService(session=db_session, pdf_path="./assets/non_existent_file.pdf")

    class MockBot:
        pass

    with pytest.raises(DeliveryError) as exc_info:
        await delivery_service.deliver_pdf(MockBot(), user_id=123, order_number="ASH-12345")

    assert "PDF asset not found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_notification_service_bilingual_dispatch():
    """Verifies NotificationService generates correct bilingual text for Owner, Dev, and Buyer."""
    owner_id = 72101760
    dev_id = 347382968
    notifier = NotificationService(owner_id=owner_id, developer_id=dev_id)

    sent_messages = []

    class MockBot:
        async def send_message(self, chat_id, text, **kwargs):
            sent_messages.append({"chat_id": chat_id, "text": text})

        async def send_photo(self, chat_id, photo, caption, **kwargs):
            sent_messages.append({"chat_id": chat_id, "photo": photo, "caption": caption})

    mock_bot = MockBot()

    order = Order(
        order_number="ASH-TEST1",
        user_id=11223344,
        username="mehdi_kh_278",
        full_name="Mehdi_Tester",
        amount_usd=79.0,
        amount_ton=12.5,
        wallet_address="EQDtest_wallet",
        tx_hash="hash_123456",
        receipt_file_id="photo_file_id_999",
        status=OrderStatus.UNDER_REVIEW.value,
        created_at=utc_now(),
        updated_at=utc_now(),
        expires_at=utc_now(),
    )

    # 1. Owner notification (must be in Persian, escaped username, $79 price)
    await notifier.notify_owner_new_order(mock_bot, order, reply_markup=None)
    owner_msg = sent_messages[-1]
    assert owner_msg["chat_id"] == owner_id
    assert "بررسی پرداخت جدید" in owner_msg["caption"]
    assert "هش تراکنش" in owner_msg["caption"]
    assert r"@mehdi\_kh\_278" in owner_msg["caption"]
    assert "$79" in owner_msg["caption"]
    assert "مبلغ" in owner_msg["caption"]

    # 2. Developer completion report (must be in English, Shamsi date, $79 price without TON)
    await notifier.notify_developer_completed(mock_bot, order)
    dev_msg = sent_messages[-1]
    assert dev_msg["chat_id"] == dev_id
    assert "[SALES REPORT: APPROVED]" in dev_msg["text"]
    assert "ASH-TEST1" in dev_msg["text"]
    assert r"@mehdi\_kh\_278" in dev_msg["text"]
    assert "• **Amount:** $79" in dev_msg["text"]
    assert "(Tehran)" in dev_msg["text"]

    # 3. Buyer rejection notice (must be in English matching Step 11)
    await notifier.notify_buyer_rejected(
        mock_bot,
        user_id=order.user_id,
        order_number=order.order_number,
    )
    buyer_msg = sent_messages[-1]
    assert buyer_msg["chat_id"] == order.user_id
    assert "Payment Could Not Be Confirmed" in buyer_msg["text"]
    assert "contact support" in buyer_msg["text"]

    # 4. Buyer approval notice (must be in English matching Step 9)
    await notifier.notify_buyer_approved(
        mock_bot,
        user_id=order.user_id,
        order_number=order.order_number,
    )
    buyer_approved_msg = sent_messages[-1]
    assert buyer_approved_msg["chat_id"] == order.user_id
    assert "Payment Confirmed!" in buyer_approved_msg["text"]
    assert "Download your product below:" in buyer_approved_msg["text"]
