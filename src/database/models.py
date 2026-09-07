"""SQLAlchemy models and status definitions for Order and BotCache."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class OrderStatus(str, Enum):
    """Lifecycle states for customer orders."""
    AWAITING_PAYMENT = "AWAITING_PAYMENT"
    AWAITING_RECEIPT = "AWAITING_RECEIPT"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    DELIVERED = "DELIVERED"
    DELIVERY_FAILED = "DELIVERY_FAILED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base declarative class."""
    pass


class Order(Base):
    """Order record persisting customer purchase attempts, payments, and review status."""
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_number: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str] = mapped_column(String(128), nullable=False)

    amount_usd: Mapped[float] = mapped_column(Float, nullable=False)
    amount_ton: Mapped[float] = mapped_column(Float, nullable=False)
    wallet_address: Mapped[str] = mapped_column(String(128), nullable=False)

    # Submitted payment proof
    tx_hash: Mapped[Optional[str]] = mapped_column(String(128), unique=True, index=True, nullable=True)
    receipt_file_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    status: Mapped[str] = mapped_column(
        String(32), default=OrderStatus.AWAITING_PAYMENT.value, index=True, nullable=False
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)

    def is_expired(self) -> bool:
        """Returns True if the order has passed its expiration window."""
        now = datetime.now(timezone.utc)
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return now > expires


class BotCache(Base):
    """Key-value persistence for Telegram file IDs and operational caches."""
    __tablename__ = "bot_cache"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class BlockedUser(Base):
    """Tracks users who have been blocked by the administrator."""
    __tablename__ = "blocked_users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    blocked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
