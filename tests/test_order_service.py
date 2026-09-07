"""Unit tests for OrderService lifecycle, state machine, and data integrity."""

from datetime import timedelta
import pytest
from src.database.models import OrderStatus, utc_now
from src.services.order_service import (
    DuplicateTxHashError,
    OrderExpiredError,
    OrderNotFoundError,
    OrderService,
    OrderStateError,
)


@pytest.mark.asyncio
async def test_create_order(order_service: OrderService):
    """Tests creating a fresh order with correct defaults and fields."""
    order = await order_service.create_order(
        user_id=123456789,
        username="john_doe",
        full_name="John Doe",
        amount_usd=79.0,
        amount_ton=12.5,
        wallet_address="EQDtest_wallet_address",
        timeout_minutes=120,
    )

    assert order.id is not None
    assert order.order_number.startswith("ASH-")
    assert len(order.order_number) == 9  # ASH-XXXXX
    assert order.user_id == 123456789
    assert order.status == OrderStatus.AWAITING_PAYMENT.value
    assert order.amount_usd == 79.0
    assert order.amount_ton == 12.5
    assert not order.is_expired()


@pytest.mark.asyncio
async def test_order_full_happy_lifecycle(order_service: OrderService):
    """Tests full order progression: Create -> Submit TX -> Submit Receipt -> Approve -> Mark Delivered."""
    order = await order_service.create_order(
        user_id=987654321,
        username="buyer_user",
        full_name="Alice Buyer",
        amount_usd=79.0,
        amount_ton=12.5,
        wallet_address="EQDtest_wallet",
    )

    # 1. Submit TX hash
    tx_hash = "4a5b6c7d8e9f0123456789abcdef4a5b6c7d8e9f0123456789abcdef4a5b6c7d"
    order = await order_service.submit_tx_hash(order.order_number, tx_hash)
    assert order.status == OrderStatus.AWAITING_RECEIPT.value
    assert order.tx_hash == tx_hash

    # 2. Submit Receipt screenshot
    receipt_file_id = "AgACAgIAAxkBAAI..."
    order = await order_service.submit_receipt(order.order_number, receipt_file_id)
    assert order.status == OrderStatus.UNDER_REVIEW.value
    assert order.receipt_file_id == receipt_file_id

    # 3. Approve order
    order = await order_service.approve_order(order.order_number)
    assert order.status == OrderStatus.APPROVED.value

    # 4. Mark delivered
    order = await order_service.mark_delivered(order.order_number)
    assert order.status == OrderStatus.DELIVERED.value


@pytest.mark.asyncio
async def test_duplicate_tx_hash_blocked(order_service: OrderService):
    """Verifies that an already submitted transaction hash cannot be submitted again."""
    order1 = await order_service.create_order(
        user_id=111,
        username="user1",
        full_name="User One",
        amount_usd=79.0,
        amount_ton=12.5,
        wallet_address="EQDtest",
    )
    same_tx = "unique_tx_hash_12345"
    await order_service.submit_tx_hash(order1.order_number, same_tx)

    # Create second order and attempt to submit the exact same tx hash
    order2 = await order_service.create_order(
        user_id=222,
        username="user2",
        full_name="User Two",
        amount_usd=79.0,
        amount_ton=12.5,
        wallet_address="EQDtest",
    )

    with pytest.raises(DuplicateTxHashError):
        await order_service.submit_tx_hash(order2.order_number, same_tx)


@pytest.mark.asyncio
async def test_rejection_workflow(order_service: OrderService):
    """Tests rejecting an order under review and persisting rejection reason."""
    order = await order_service.create_order(
        user_id=333,
        username="user3",
        full_name="User Three",
        amount_usd=79.0,
        amount_ton=12.5,
        wallet_address="EQDtest",
    )
    await order_service.submit_tx_hash(order.order_number, "tx_hash_333")
    await order_service.submit_receipt(order.order_number, "receipt_333")

    reason = "Transaction not found on TON blockchain"
    order = await order_service.reject_order(order.order_number, reason)

    assert order.status == OrderStatus.REJECTED.value
    assert order.rejection_reason == reason


@pytest.mark.asyncio
async def test_idempotent_approval_and_rejection(order_service: OrderService):
    """Verifies repeated clicks on approve or reject do not corrupt state."""
    order = await order_service.create_order(
        user_id=444,
        username="user4",
        full_name="User Four",
        amount_usd=79.0,
        amount_ton=12.5,
        wallet_address="EQDtest",
    )
    await order_service.submit_tx_hash(order.order_number, "tx_hash_444")
    await order_service.submit_receipt(order.order_number, "receipt_444")

    # First approve
    approved = await order_service.approve_order(order.order_number)
    assert approved.status == OrderStatus.APPROVED.value

    # Second approve should return safely without error
    approved_again = await order_service.approve_order(order.order_number)
    assert approved_again.status == OrderStatus.APPROVED.value

    # Attempting to reject an approved order should raise OrderStateError
    with pytest.raises(OrderStateError):
        await order_service.reject_order(order.order_number, "Should fail")


@pytest.mark.asyncio
async def test_user_cancel_order(order_service: OrderService):
    """Tests that a user can cancel a pending order."""
    order = await order_service.create_order(
        user_id=555,
        username="user5",
        full_name="User Five",
        amount_usd=79.0,
        amount_ton=12.5,
        wallet_address="EQDtest",
    )
    cancelled = await order_service.cancel_order(order.order_number)
    assert cancelled.status == OrderStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_expired_order_handling(order_service: OrderService):
    """Verifies that an order past its expiration time raises OrderExpiredError upon submission."""
    order = await order_service.create_order(
        user_id=666,
        username="user6",
        full_name="User Six",
        amount_usd=79.0,
        amount_ton=12.5,
        wallet_address="EQDtest",
        timeout_minutes=120,
    )
    # Artificially expire the order in database
    order.expires_at = utc_now() - timedelta(minutes=1)
    await order_service.session.flush()

    assert order.is_expired() is True

    with pytest.raises(OrderExpiredError):
        await order_service.submit_tx_hash(order.order_number, "expired_tx")


@pytest.mark.asyncio
async def test_block_and_unblock_user(order_service: OrderService):
    """Verifies that an admin can block and unblock users via OrderService."""
    test_user_id = 99887766

    # Initially not blocked
    assert await order_service.is_user_blocked(test_user_id) is False

    # Block user
    blocked_record = await order_service.block_user(test_user_id, reason="Spamming support")
    assert blocked_record.user_id == test_user_id
    assert blocked_record.reason == "Spamming support"
    assert await order_service.is_user_blocked(test_user_id) is True

    # Blocking again is idempotent
    second_block = await order_service.block_user(test_user_id)
    assert second_block.user_id == test_user_id
    assert await order_service.is_user_blocked(test_user_id) is True

    # Unblock user
    unblocked = await order_service.unblock_user(test_user_id)
    assert unblocked is True
    assert await order_service.is_user_blocked(test_user_id) is False

    # Unblocking again returns False
    assert await order_service.unblock_user(test_user_id) is False

