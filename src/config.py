"""Application configuration managed by Pydantic Settings."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram Credentials
    bot_token: str = Field(..., description="Telegram Bot token from @BotFather")
    owner_id: int = Field(72101760, description="Owner numeric Telegram ID (@MoHo72)")
    developer_id: int = Field(347382968, description="Developer numeric Telegram ID (@mehdi_kh_278)")

    # Payment & Product
    ton_wallet_address: str = Field(..., description="Receiving TON wallet address")
    price_usd: float = Field(79.0, description="Launch discount price in USD")
    original_price_usd: float = Field(100.0, description="Regular price in USD")
    price_ton: float = Field(12.5, description="Equivalent price in TON cryptocurrency")
    order_timeout_minutes: int = Field(120, description="Order validity duration in minutes")
    pdf_file_path: str = Field("./assets/AI_Side_Hustle.pdf", description="Path to digital product PDF")

    # Database
    database_url: str = Field(
        "sqlite+aiosqlite:///./data/bot.db",
        description="Async SQLite database connection string",
    )


# Singleton instance loaded on demand or cached
def get_settings() -> Settings:
    return Settings()
