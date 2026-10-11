"""Pydantic schemas for reminder generation requests, responses, and review workflows."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ReminderGenerationRequest(BaseModel):
    """Payload for triggering follow-up reminder generation."""

    model_config = ConfigDict(extra="forbid")

    window_days: int = Field(
        default=7,
        ge=1,
        le=90,
        description="Eligibility lookback window in days (default: 7).",
    )
    reference_time: Optional[datetime] = Field(
        default=None,
        description=(
            "Optional reference anchor timestamp in UTC for testing and controlled replays. "
            "In standard operation, leave unset to evaluate relative to the current UTC time."
        ),
    )


class ReminderGenerationResponse(BaseModel):
    """Response returned upon completion of reminder generation."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(default="completed", description="Batch execution status.")
    total_reviewed: int = Field(description="Total encounters inspected within the window.")
    reminders_created: int = Field(description="New follow-up reminders drafted and persisted.")
    reminders_skipped: int = Field(description="Encounters skipped because reminders already exist.")
    failures: int = Field(description="Encounters that encountered individual processing errors.")
    created_reminder_ids: List[int] = Field(
        default_factory=list, description="IDs of newly persisted FollowUpReminder records."
    )
    failed_appointment_ids: List[int] = Field(
        default_factory=list, description="IDs of encounters that failed processing."
    )
    window_days: int = Field(description="Applied lookback window in days.")


class ValidationCheckDetail(BaseModel):
    """Individual guardrail validation rule outcome."""

    id: str = Field(..., description="Check identifier")
    label: str = Field(..., description="Human-readable rule name")
    passed: bool = Field(..., description="Whether message passed this rule")
    detail: str = Field(..., description="Explanatory detail or detected pattern")


class ReminderDetailResponse(BaseModel):
    """Full follow-up reminder entity with encounter context and provenance."""

    model_config = ConfigDict(extra="forbid")

    id: int = Field(..., description="Reminder ID")
    appointment_id: int = Field(..., description="Associated encounter ID")
    patient_id: int = Field(..., description="Patient ID")
    patient_name: str = Field(..., description="Patient full name")
    patient_email: str = Field(..., description="Patient email")
    appointment_type: str = Field(..., description="Encounter type")
    appointment_datetime: datetime = Field(..., description="Encounter date in UTC")
    message_text: str = Field(..., description="Current draft or approved reminder text")
    original_text: Optional[str] = Field(default=None, description="Original unedited text")
    is_edited: bool = Field(default=False, description="Whether message text differs from original draft")
    status: str = Field(..., description="Status (draft, approved, rejected, pending, sent, failed)")
    generation_source: Optional[str] = Field(default=None, description="Source (ai or template_fallback)")
    model_name: Optional[str] = Field(default=None, description="LLM model used, if applicable")
    fallback_reason: Optional[str] = Field(default=None, description="Reason fallback was triggered")
    validation_checks: List[ValidationCheckDetail] = Field(default_factory=list, description="Itemized validation results")
    created_at: datetime = Field(..., description="Creation timestamp in UTC")
    approved_at: Optional[datetime] = Field(default=None, description="Approval timestamp in UTC")
    approved_by: Optional[str] = Field(default=None, description="Approver name or role")
    delivery_provider: Optional[str] = Field(default=None, description="Delivery provider name")
    delivery_reference_id: Optional[str] = Field(default=None, description="External provider message ID")
    delivery_error: Optional[str] = Field(default=None, description="Delivery error details if failed")


class ReminderUpdateRequest(BaseModel):
    """Payload to edit message text of a draft reminder."""

    model_config = ConfigDict(extra="forbid")

    message_text: str = Field(..., min_length=15, max_length=500, description="Updated reminder text")


class ErrorResponse(BaseModel):
    """Standardized error response payload."""

    model_config = ConfigDict(extra="forbid")

    detail: str = Field(description="Safe human-readable error description.")
