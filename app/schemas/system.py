"""Pydantic schemas for system status and settings."""

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class SystemSettingsResponse(BaseModel):
    """Safe system integration status for administrative review."""

    model_config = ConfigDict(extra="forbid")

    project_name: str = Field(..., description="Application name")
    version: str = Field(..., description="Service version")
    environment: str = Field(..., description="Running environment")
    database_type: str = Field(..., description="Active database engine")
    llm_provider: str = Field(..., description="Configured LLM provider name")
    llm_model: str = Field(..., description="Configured model name")
    llm_configured: bool = Field(..., description="Whether LLM credentials and provider are active")
    llm_status: str = Field(..., description="Status: 'configured', 'unverified', or 'offline_fallback'")
    delivery_provider: str = Field(..., description="Delivery transport provider")
    delivery_enabled: bool = Field(..., description="Whether external message dispatch is enabled")
    delivery_status: str = Field(..., description="Status: 'disabled_safe_mode', 'live', or 'unconfigured'")
