"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration parameters for the application."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    project_name: str = "HealthTrack Follow-Up System"
    version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False

    # Database configuration - defaults to local SQLite file
    database_url: str = "sqlite:///./healthtrack.db"

    # LLM Provider Configuration (Optional)
    llm_provider: str = "none"
    llm_api_key: Optional[str] = None
    llm_model: str = "gemini-2.5-flash"
    llm_timeout_seconds: float = 10.0

    # Gemini-specific settings (read from GEMINI_API_KEY and GEMINI_MODEL)
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-3.5-flash"

    @property
    def effective_gemini_api_key(self) -> Optional[str]:
        """Resolve API key from either GEMINI_API_KEY or LLM_API_KEY."""
        return self.gemini_api_key or self.llm_api_key

    @property
    def effective_gemini_model(self) -> str:
        """Resolve model name from either GEMINI_MODEL or LLM_MODEL."""
        return self.gemini_model or self.llm_model or "gemini-3.5-flash"

    @property
    def is_gemini_enabled(self) -> bool:
        """Return True if Gemini is configured as the active provider."""
        return (
            self.llm_provider.lower() == "gemini"
            or (self.llm_provider.lower() != "none" and bool(self.effective_gemini_api_key))
        )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
