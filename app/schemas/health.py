"""Pydantic schemas for health and system status endpoints."""

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Schema for service health check response."""

    model_config = ConfigDict(extra="forbid")

    status: str
    service: str
    version: str
    environment: str
