"""Pydantic schemas for operational overview and activity logs."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class OverviewMetricsResponse(BaseModel):
    """Operational summary metrics computed directly from database."""

    model_config = ConfigDict(extra="forbid")

    total_patients: int = Field(..., description="Registered patients")
    total_appointments: int = Field(..., description="Total appointments recorded")
    eligible_appointments: int = Field(..., description="Appointments within 7-day lookback window")
    drafts_pending_review: int = Field(..., description="Reminders in draft status awaiting review")
    approved_reminders: int = Field(..., description="Reminders approved and ready for delivery")
    dispatched_reminders: int = Field(..., description="Reminders sent or delivered")
    failed_deliveries: int = Field(..., description="Failed delivery attempts")
    ai_generated_count: int = Field(..., description="Reminders produced via AI generation")
    fallback_count: int = Field(..., description="Reminders produced via deterministic fallback")


class ActivityItemResponse(BaseModel):
    """Operational activity record."""

    model_config = ConfigDict(extra="forbid")

    id: int = Field(..., description="Activity ID")
    reminder_id: int = Field(..., description="Target reminder ID")
    appointment_id: int = Field(..., description="Associated appointment ID")
    patient_name: str = Field(..., description="Patient name")
    action_type: str = Field(..., description="Action type (draft_created, edited, approved, rejected, sent, failed)")
    timestamp: datetime = Field(..., description="Event timestamp")
    detail: str = Field(..., description="Safe description of event")
