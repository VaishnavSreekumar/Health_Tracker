"""Pydantic schemas for appointment management."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.appointment import AppointmentType


class AppointmentCreate(BaseModel):
    """Payload to record a clinical encounter."""

    model_config = ConfigDict(extra="forbid")

    patient_id: int = Field(..., description="ID of the registered patient")
    appointment_type: AppointmentType = Field(..., description="Type of clinical visit")
    appointment_datetime: datetime = Field(..., description="Encounter timestamp in UTC")


class AppointmentResponse(BaseModel):
    """Appointment record response with patient and reminder status."""

    model_config = ConfigDict(extra="forbid")

    id: int = Field(..., description="Internal appointment ID")
    patient_id: int = Field(..., description="Patient ID")
    patient_name: str = Field(..., description="Patient full name")
    patient_email: str = Field(..., description="Patient email")
    appointment_type: AppointmentType = Field(..., description="Type of clinical encounter")
    appointment_datetime: datetime = Field(..., description="Encounter timestamp in UTC")
    is_eligible: bool = Field(..., description="Whether appointment falls within 7-day follow-up window")
    has_reminder: bool = Field(..., description="Whether a follow-up reminder has already been created")
    reminder_id: Optional[int] = Field(default=None, description="Associated reminder ID if drafted")
    reminder_status: Optional[str] = Field(default=None, description="Status of reminder (e.g. draft, approved, sent)")
    created_at: datetime = Field(..., description="Record creation timestamp")
