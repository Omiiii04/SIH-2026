"""
Configuration management for the SIH-2026 Orchestrator.

All settings are loaded from environment variables (via .env file).
Never hardcode secrets or credentials here.
"""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central settings object. Values are read from environment variables
    or the .env file in the project root.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Application ──────────────────────────────────────────────────────────
    app_name: str = "SIH-2026 Orchestrator"
    app_version: str = "0.1.0"
    debug: bool = False

    # ── Server ────────────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000

    # ── PostgreSQL ────────────────────────────────────────────────────────────
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "sih2026"
    postgres_user: str = "sih_user"
    postgres_password: str = "change_me"

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ── ChromaDB ──────────────────────────────────────────────────────────────
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    chroma_collection: str = "conversation_memory"

    # ── Worker Nodes (LM Studio endpoints) ───────────────────────────────────
    # Comma-separated list of base URLs, e.g. "http://192.168.1.1:1234"
    node_text_url: str = "http://192.168.1.101:1234"
    node_vision_url: str = "http://192.168.1.102:1234"
    node_reasoning_url: str = "http://192.168.1.103:1234"
    node_code_url: str = "http://192.168.1.104:1234"
    node_rag_url: str = "http://192.168.1.105:1234"

    # ── HTTP Client ───────────────────────────────────────────────────────────
    http_timeout: float = 30.0        # seconds
    http_max_retries: int = 3

    # ── Health-check ──────────────────────────────────────────────────────────
    health_check_interval: int = 30   # seconds between node health polls


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton Settings instance."""
    return Settings()
