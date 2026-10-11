"""Pydantic schemas for patient management."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class PatientBase(BaseModel):
    """Base patient data."""

    model_config = ConfigDict(extra="forbid")

    first_name: str = Field(..., min_length=1, max_length=100, description="Patient first name")
    last_name: str = Field(..., min_length=1, max_length=100, description="Patient last name")
    email: str = Field(
        ...,
        pattern=r"^[\w\.-]+@[\w\.-]+\.\w+$",
        description="Synthetic patient email address",
    )


class PatientCreate(PatientBase):
    """Payload to register a new patient."""
    pass


class PatientResponse(PatientBase):
    """Public patient record response."""

    id: int = Field(..., description="Internal patient database ID")
    created_at: datetime = Field(..., description="Registration timestamp in UTC")
    appointment_count: int = Field(default=0, description="Number of recorded clinical encounters")


class PatientWithAppointmentsResponse(PatientResponse):
    """Patient record including encounter history."""

    appointments: List[dict] = Field(default_factory=list, description="Associated appointment records")
