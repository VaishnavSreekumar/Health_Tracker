"""Pydantic validation schemas package."""

from .appointment import AppointmentCreate, AppointmentResponse
from .health import HealthResponse
from .overview import ActivityItemResponse, OverviewMetricsResponse
from .patient import PatientCreate, PatientResponse, PatientWithAppointmentsResponse
from .reminder import (
    ErrorResponse,
    ReminderDetailResponse,
    ReminderGenerationRequest,
    ReminderGenerationResponse,
    ReminderUpdateRequest,
    ValidationCheckDetail,
)
from .system import SystemSettingsResponse

__all__ = [
    "HealthResponse",
    "PatientCreate",
    "PatientResponse",
    "PatientWithAppointmentsResponse",
    "AppointmentCreate",
    "AppointmentResponse",
    "ReminderGenerationRequest",
    "ReminderGenerationResponse",
    "ReminderDetailResponse",
    "ReminderUpdateRequest",
    "ValidationCheckDetail",
    "OverviewMetricsResponse",
    "ActivityItemResponse",
    "SystemSettingsResponse",
    "ErrorResponse",
]
