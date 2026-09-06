"""Security and authorization tests."""

import pytest
from aiogram.types import CallbackQuery, Message, User
from src.bot.middlewares.auth_middleware import OwnerAuthMiddleware
from src.services.order_service import DuplicateTxHashError, OrderService


@pytest.mark.asyncio
async def test_owner_auth_middleware_blocks_unauthorized_user():
    """Verifies OwnerAuthMiddleware intercepts and blocks requests from non-owner IDs."""
    owner_id = 72101760
    middleware = OwnerAuthMiddleware(owner_id=owner_id)

    called = False

    async def mock_handler(event, data):
        nonlocal called
        called = True
        return "HandlerExecuted"

    # 1. Attacker user (ID 999999999)
    attacker = User(id=999999999, is_bot=False, first_name="Attacker", username="hacker")
    data = {"event_from_user": attacker}

    # Test callback query event
    answered_text = None
    show_alert_val = False

    class MockCallback:
        async def answer(self, text, show_alert=False):
            nonlocal answered_text, show_alert_val
            answered_text = text
            show_alert_val = show_alert

    mock_cb = MockCallback()
    result = await middleware(mock_handler, mock_cb, data)

    assert result is None
    assert called is False
    assert "Access denied" in answered_text
    assert show_alert_val is True

    # 2. Legitimate Owner user (ID 72101760)
    owner_user = User(id=owner_id, is_bot=False, first_name="Owner", username="MoHo72")
    owner_data = {"event_from_user": owner_user}

    result = await middleware(mock_handler, mock_cb, owner_data)
    assert result == "HandlerExecuted"
    assert called is True


@pytest.mark.asyncio
async def test_replay_attack_duplicate_hash_rejection(order_service: OrderService):
    """Verifies that an attacker cannot reuse someone else's verified transaction hash."""
    order1 = await order_service.create_order(
        user_id=1001,
        username="legit_buyer",
        full_name="Legit Buyer",
        amount_usd=79.0,
        amount_ton=12.5,
        wallet_address="EQDtest_wallet",
    )
    victim_tx = "ton_tx_hash_secret_receipt_abc123"
    await order_service.submit_tx_hash(order1.order_number, victim_tx)

    # Attacker tries to submit the same hash for their order
    order_attacker = await order_service.create_order(
        user_id=9999,
        username="attacker",
        full_name="Attacker",
        amount_usd=79.0,
        amount_ton=12.5,
        wallet_address="EQDtest_wallet",
    )

    with pytest.raises(DuplicateTxHashError):
        await order_service.submit_tx_hash(order_attacker.order_number, victim_tx)
