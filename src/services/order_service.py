"""Order lifecycle management and business operations."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import BlockedUser, Order, OrderStatus, utc_now
from src.utils.code_generator import generate_order_number
from src.utils.logger import logger


class OrderServiceError(Exception):
    """Base domain error for order operations."""
    pass


class OrderNotFoundError(OrderServiceError):
    """Raised when an order number cannot be located."""
    pass


class DuplicateTxHashError(OrderServiceError):
    """Raised when a user attempts to submit an already-used transaction hash."""
    pass


class OrderStateError(OrderServiceError):
    """Raised when an illegal state transition is attempted."""
    pass


class OrderExpiredError(OrderServiceError):
    """Raised when attempting an operation on an expired order."""
    pass


class OrderService:
    """Encapsulates all order creation, transition, and query operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_order(
        self,
        user_id: int,
        username: Optional[str],
        full_name: str,
        amount_usd: float,
        amount_ton: float,
        wallet_address: str,
        timeout_minutes: int = 120,
    ) -> Order:
        """Creates a new order in AWAITING_PAYMENT state with an expiration window."""
        now = utc_now()
        expires_at = now + timedelta(minutes=timeout_minutes)

        # Generate unique order number (retry on improbable collision)
        order_number = ""
        for _ in range(5):
            candidate = generate_order_number()
            existing = await self.get_order_by_number(candidate)
            if existing is None:
                order_number = candidate
                break

        if not order_number:
            raise OrderServiceError("Failed to generate unique order number.")

        order = Order(
            order_number=order_number,
            user_id=user_id,
            username=username,
            full_name=full_name,
            amount_usd=amount_usd,
            amount_ton=amount_ton,
            wallet_address=wallet_address,
            status=OrderStatus.AWAITING_PAYMENT.value,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
        )
        self.session.add(order)
        await self.session.flush()
        logger.info(f"Order created: {order.order_number} for user {user_id} ({amount_ton} TON / ${amount_usd})")
        return order

    async def get_order_by_number(self, order_number: str) -> Optional[Order]:
        """Fetches an order by its unique order number."""
        stmt = select(Order).where(Order.order_number == order_number)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_active_order_by_user(self, user_id: int) -> Optional[Order]:
        """Finds any active pending order for the given user."""
        active_statuses = [
            OrderStatus.AWAITING_PAYMENT.value,
            OrderStatus.AWAITING_RECEIPT.value,
            OrderStatus.UNDER_REVIEW.value,
        ]
        stmt = (
            select(Order)
            .where(Order.user_id == user_id, Order.status.in_(active_statuses))
            .order_by(Order.created_at.desc())
        )
        result = await self.session.execute(stmt)
        order = result.scalars().first()
        if order and order.is_expired() and order.status in [OrderStatus.AWAITING_PAYMENT.value, OrderStatus.AWAITING_RECEIPT.value]:
            order.status = OrderStatus.EXPIRED.value
            order.updated_at = utc_now()
            await self.session.flush()
            logger.info(f"Order {order.order_number} has expired.")
            return None
        return order

    async def is_tx_hash_taken(self, tx_hash: str, current_order_number: Optional[str] = None) -> bool:
        """Checks if a transaction hash has already been registered in the database."""
        stmt = select(Order).where(Order.tx_hash == tx_hash)
        if current_order_number:
            stmt = stmt.where(Order.order_number != current_order_number)
        result = await self.session.execute(stmt)
        return result.scalars().first() is not None

    async def submit_tx_hash(self, order_number: str, tx_hash: str) -> Order:
        """Saves the buyer's transaction hash and advances order to AWAITING_RECEIPT."""
        order = await self.get_order_by_number(order_number)
        if not order:
            raise OrderNotFoundError(f"Order {order_number} not found.")

        if order.is_expired():
            order.status = OrderStatus.EXPIRED.value
            await self.session.flush()
            raise OrderExpiredError(f"Order {order_number} has expired.")

        if order.status != OrderStatus.AWAITING_PAYMENT.value:
            raise OrderStateError(f"Cannot submit transaction hash for order in state '{order.status}'.")

        cleaned_hash = tx_hash.strip()
        if await self.is_tx_hash_taken(cleaned_hash, order_number):
            raise DuplicateTxHashError("This transaction hash has already been submitted for another order.")

        order.tx_hash = cleaned_hash
        order.status = OrderStatus.AWAITING_RECEIPT.value
        order.updated_at = utc_now()
        await self.session.flush()
        logger.info(f"TX Hash recorded for order {order_number}.")
        return order

    async def submit_receipt(self, order_number: str, receipt_file_id: str) -> Order:
        """Saves the buyer's screenshot file_id and advances order to UNDER_REVIEW."""
        order = await self.get_order_by_number(order_number)
        if not order:
            raise OrderNotFoundError(f"Order {order_number} not found.")

        if order.is_expired():
            order.status = OrderStatus.EXPIRED.value
            await self.session.flush()
            raise OrderExpiredError(f"Order {order_number} has expired.")

        if order.status != OrderStatus.AWAITING_RECEIPT.value:
            raise OrderStateError(f"Cannot submit receipt screenshot for order in state '{order.status}'.")

        order.receipt_file_id = receipt_file_id
        order.status = OrderStatus.UNDER_REVIEW.value
        order.updated_at = utc_now()
        await self.session.flush()
        logger.info(f"Receipt submitted for order {order_number}. State changed to UNDER_REVIEW.")
        return order

    async def approve_order(self, order_number: str) -> Order:
        """Approves an order under review. Idempotent check ensures only UNDER_REVIEW orders can be approved."""
        order = await self.get_order_by_number(order_number)
        if not order:
            raise OrderNotFoundError(f"Order {order_number} not found.")

        if order.status == OrderStatus.APPROVED.value or order.status == OrderStatus.DELIVERED.value:
            logger.warning(f"Order {order_number} is already approved/delivered. Ignoring duplicate approval.")
            return order

        if order.status != OrderStatus.UNDER_REVIEW.value:
            raise OrderStateError(f"Cannot approve order in state '{order.status}'. Must be UNDER_REVIEW.")

        order.status = OrderStatus.APPROVED.value
        order.updated_at = utc_now()
        await self.session.flush()
        logger.info(f"Order {order_number} APPROVED by owner.")
        return order

    async def mark_delivered(self, order_number: str) -> Order:
        """Marks an approved order as DELIVERED after successful file dispatch."""
        order = await self.get_order_by_number(order_number)
        if not order:
            raise OrderNotFoundError(f"Order {order_number} not found.")

        order.status = OrderStatus.DELIVERED.value
        order.updated_at = utc_now()
        await self.session.flush()
        logger.info(f"Order {order_number} marked as DELIVERED.")
        return order

    async def mark_delivery_failed(self, order_number: str) -> Order:
        """Marks an order as DELIVERY_FAILED if Telegram sending fails."""
        order = await self.get_order_by_number(order_number)
        if not order:
            raise OrderNotFoundError(f"Order {order_number} not found.")

        order.status = OrderStatus.DELIVERY_FAILED.value
        order.updated_at = utc_now()
        await self.session.flush()
        logger.error(f"Order {order_number} marked as DELIVERY_FAILED.")
        return order

    async def reject_order(self, order_number: str, reason: str) -> Order:
        """Rejects an order under review. Idempotent check ensures only UNDER_REVIEW orders can be rejected."""
        order = await self.get_order_by_number(order_number)
        if not order:
            raise OrderNotFoundError(f"Order {order_number} not found.")

        if order.status == OrderStatus.REJECTED.value:
            logger.warning(f"Order {order_number} is already rejected. Ignoring duplicate rejection.")
            return order

        if order.status != OrderStatus.UNDER_REVIEW.value:
            raise OrderStateError(f"Cannot reject order in state '{order.status}'. Must be UNDER_REVIEW.")

        order.status = OrderStatus.REJECTED.value
        order.rejection_reason = reason
        order.updated_at = utc_now()
        await self.session.flush()
        logger.info(f"Order {order_number} REJECTED with reason: {reason}")
        return order

    async def cancel_order(self, order_number: str) -> Order:
        """Cancels an order by user request before final review."""
        order = await self.get_order_by_number(order_number)
        if not order:
            raise OrderNotFoundError(f"Order {order_number} not found.")

        if order.status in [OrderStatus.APPROVED.value, OrderStatus.DELIVERED.value]:
            raise OrderStateError("Cannot cancel an already approved or delivered order.")

        order.status = OrderStatus.CANCELLED.value
        order.updated_at = utc_now()
        await self.session.flush()
        logger.info(f"Order {order_number} CANCELLED by user.")
        return order

    async def block_user(self, user_id: int, reason: Optional[str] = None) -> BlockedUser:
        """Blocks a user from performing actions in the bot."""
        stmt = select(BlockedUser).where(BlockedUser.user_id == user_id)
        result = await self.session.execute(stmt)
        record = result.scalars().first()
        if not record:
            record = BlockedUser(user_id=user_id, reason=reason, blocked_at=utc_now())
            self.session.add(record)
            await self.session.flush()
            logger.info(f"User {user_id} added to blocked_users.")
        return record

    async def unblock_user(self, user_id: int) -> bool:
        """Removes a user from the blocked_users table."""
        stmt = select(BlockedUser).where(BlockedUser.user_id == user_id)
        result = await self.session.execute(stmt)
        record = result.scalars().first()
        if record:
            await self.session.delete(record)
            await self.session.flush()
            logger.info(f"User {user_id} unblocked.")
            return True
        return False

    async def is_user_blocked(self, user_id: int) -> bool:
        """Returns True if the user is in the blocked_users list."""
        stmt = select(BlockedUser).where(BlockedUser.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalars().first() is not None
