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
    clinic_name: str = "HealthTrack Clinic"
    version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False

    # Database configuration - defaults to local SQLite file
    database_url: str = "sqlite:///./healthtrack.db"

    # LLM Provider Configuration (Optional)
    # Supported: "none", "openrouter", "gemini", "openrouter_with_gemini_fallback"
    llm_provider: str = "none"
    llm_api_key: Optional[str] = None
    llm_model: str = "gemini-2.5-flash"
    llm_timeout_seconds: float = 15.0

    # Gemini-specific settings (read from GEMINI_API_KEY and GEMINI_MODEL)
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-3.6-flash"

    # OpenRouter-specific settings (read from OPENROUTER_API_KEY, OPENROUTER_MODEL, etc.)
    # STRICT ZERO-COST POLICY: OpenRouter model must be an active :free model.
    openrouter_api_key: Optional[str] = None
    openrouter_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_site_url: Optional[str] = None
    openrouter_app_name: str = "HealthTrack"

    @property
    def effective_gemini_api_key(self) -> Optional[str]:
        """Resolve API key from either GEMINI_API_KEY or LLM_API_KEY."""
        return self.gemini_api_key or (self.llm_api_key if self.llm_provider.lower() == "gemini" else None)

    @property
    def effective_gemini_model(self) -> str:
        """Resolve model name from either GEMINI_MODEL or LLM_MODEL."""
        return self.gemini_model or "gemini-3.6-flash"

    @property
    def effective_openrouter_api_key(self) -> Optional[str]:
        """Resolve API key for OpenRouter."""
        return self.openrouter_api_key or (
            self.llm_api_key if self.llm_provider.lower() in ("openrouter", "openrouter_with_gemini_fallback") else None
        )

    @property
    def effective_openrouter_model(self) -> str:
        """Resolve model name for OpenRouter."""
        if self.openrouter_model:
            return self.openrouter_model
        if self.llm_model and ":free" in self.llm_model.lower():
            return self.llm_model
        return "nvidia/nemotron-3-ultra-550b-a55b:free"

    @property
    def is_openrouter_model_free(self) -> bool:
        """Enforce strict zero-cost policy: check if OpenRouter model identifier is tagged with :free."""
        model = (self.effective_openrouter_model or "").strip().lower()
        return ":free" in model

    @property
    def is_openrouter_enabled(self) -> bool:
        """Return True if OpenRouter is active as primary or part of failover."""
        prov = self.llm_provider.lower()
        return (
            prov in ("openrouter", "openrouter_with_gemini_fallback")
            or (prov not in ("none", "gemini") and bool(self.effective_openrouter_api_key))
        )

    @property
    def is_gemini_enabled(self) -> bool:
        """Return True if Gemini is active as primary or backup failover."""
        prov = self.llm_provider.lower()
        return (
            prov in ("gemini", "openrouter_with_gemini_fallback")
            or (prov not in ("none", "openrouter") and bool(self.effective_gemini_api_key))
        )

    @property
    def is_failover_enabled(self) -> bool:
        """Return True if multi-provider failover is explicitly requested."""
        return self.llm_provider.lower() == "openrouter_with_gemini_fallback"


def get_settings() -> Settings:
    """Return application settings instance."""
    return Settings()
