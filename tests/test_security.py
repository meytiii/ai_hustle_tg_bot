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


@pytest.mark.asyncio
async def test_reaction_middleware_salute():
    """Verifies that incoming messages receive a salute emoji (🫡) reaction."""
    from unittest.mock import AsyncMock, MagicMock
    from src.bot.middlewares.reaction_middleware import ReactionMiddleware, SALUTE_EMOJI

    middleware = ReactionMiddleware()
    called = False

    async def mock_handler(event, data):
        nonlocal called
        called = True
        return "HandlerExecuted"

    # 1. Successful reaction
    mock_msg = MagicMock(spec=Message)
    mock_msg.react = AsyncMock()

    result = await middleware(mock_handler, mock_msg, {})
    assert result == "HandlerExecuted"
    assert called is True
    assert mock_msg.react.called
    call_args = mock_msg.react.call_args[0][0]
    assert call_args[0].emoji == SALUTE_EMOJI

    # 2. Resilient to client reaction failure
    failing_msg = MagicMock(spec=Message)
    failing_msg.react = AsyncMock(side_effect=Exception("Reactions not supported"))

    result = await middleware(mock_handler, failing_msg, {})
    assert result == "HandlerExecuted"


@pytest.mark.asyncio
async def test_blocked_user_middleware(order_service: OrderService):
    """Verifies that BlockedUserMiddleware blocks blocked users and permits unblocked users."""
    from unittest.mock import AsyncMock, MagicMock
    from src.bot.middlewares.blocked_user_middleware import BlockedUserMiddleware

    middleware = BlockedUserMiddleware()
    called = False

    async def mock_handler(event, data):
        nonlocal called
        called = True
        return "HandlerExecuted"

    blocked_user_id = 777111
    allowed_user_id = 888222

    # Block one user
    await order_service.block_user(blocked_user_id, reason="Abusive behavior")

    # 1. Blocked user sends Message
    blocked_user = User(id=blocked_user_id, is_bot=False, first_name="Blocked")
    msg_blocked = MagicMock(spec=Message)
    msg_blocked.answer = AsyncMock()

    called = False
    data_blocked = {"event_from_user": blocked_user, "order_service": order_service}
    result = await middleware(mock_handler, msg_blocked, data_blocked)

    assert result is None
    assert called is False
    msg_blocked.answer.assert_called_once_with("⚠️ Your account has been suspended.")

    # 2. Blocked user sends CallbackQuery
    cb_blocked = MagicMock(spec=CallbackQuery)
    cb_blocked.answer = AsyncMock()

    called = False
    result = await middleware(mock_handler, cb_blocked, data_blocked)

    assert result is None
    assert called is False
    cb_blocked.answer.assert_called_once_with("⚠️ Your account has been suspended.", show_alert=True)

    # 3. Unblocked user sends Message
    allowed_user = User(id=allowed_user_id, is_bot=False, first_name="Allowed")
    msg_allowed = MagicMock(spec=Message)
    msg_allowed.answer = AsyncMock()

    called = False
    data_allowed = {"event_from_user": allowed_user, "order_service": order_service}
    result = await middleware(mock_handler, msg_allowed, data_allowed)

    assert result == "HandlerExecuted"
    assert called is True

