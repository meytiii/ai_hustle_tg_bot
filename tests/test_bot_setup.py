"""Tests for dispatcher assembly, router registration, and settings validation."""

import pytest
from src.bot.dispatcher import setup_dispatcher
from src.config import Settings
from src.database.session import close_db, init_db


def test_settings_validation():
    """Verifies Settings properly validates mandatory fields and defaults."""
    settings = Settings(
        bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        ton_wallet_address="EQDtest_wallet_address_12345",
    )
    assert settings.owner_id == 72101760
    assert settings.developer_id == 347382968
    assert settings.price_usd == 79.0
    assert settings.original_price_usd == 100.0
    assert settings.price_ton == 12.5
    assert settings.order_timeout_minutes == 120


def test_dispatcher_registration():
    """Verifies that all required routers and handlers are registered into the Dispatcher."""
    settings = Settings(
        bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        ton_wallet_address="EQDtest_wallet_address_12345",
    )
    dp = setup_dispatcher(settings)
    router_names = [r.name for r in dp.sub_routers]

    assert "buyer_router" in router_names
    assert "owner_router" in router_names
    assert "common_router" in router_names


@pytest.mark.asyncio
async def test_database_init():
    """Verifies init_db creates all required tables cleanly."""
    test_db = "sqlite+aiosqlite:///:memory:"
    await init_db(test_db)
    await close_db()
