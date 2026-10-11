"""Clinical encounters and appointments API routes."""

from datetime import datetime, timedelta, timezone
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.db.base import utc_now
from app.db.session import get_db
from app.models.appointment import Appointment, AppointmentType
from app.models.patient import Patient
from app.models.reminder import FollowUpReminder
from app.schemas.appointment import AppointmentCreate, AppointmentResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=List[AppointmentResponse], summary="List Appointments")
def list_appointments(
    eligible_only: bool = Query(default=False, description="Filter for encounters in 7-day lookback window"),
    reference_time: Optional[datetime] = Query(default=None, description="Anchor timestamp in UTC"),
    session: Session = Depends(get_db),
) -> List[AppointmentResponse]:
    """Retrieve list of clinical encounters with patient context and eligibility status."""
    anchor = reference_time or utc_now()
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)

    window_start = anchor - timedelta(days=7)

    query = (
        session.query(Appointment)
        .options(
            joinedload(Appointment.patient),
            joinedload(Appointment.reminder),
        )
        .order_by(Appointment.appointment_datetime.desc())
    )

    appointments = query.all()
    results = []

    for apt in appointments:
        apt_dt = apt.appointment_datetime
        if apt_dt.tzinfo is None:
            apt_dt = apt_dt.replace(tzinfo=timezone.utc)

        is_eligible = (apt_dt >= window_start) and (apt_dt < anchor)

        if eligible_only and not is_eligible:
            continue

        results.append(
            AppointmentResponse(
                id=apt.id,
                patient_id=apt.patient_id,
                patient_name=f"{apt.patient.first_name} {apt.patient.last_name}" if apt.patient else "Unknown",
                patient_email=apt.patient.email if apt.patient else "",
                appointment_type=apt.appointment_type,
                appointment_datetime=apt.appointment_datetime,
                is_eligible=is_eligible,
                has_reminder=apt.reminder is not None,
                reminder_id=apt.reminder.id if apt.reminder else None,
                reminder_status=apt.reminder.status.value if apt.reminder else None,
                created_at=apt.created_at,
            )
        )

    return results


@router.post("", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED, summary="Create Appointment")
def create_appointment(payload: AppointmentCreate, session: Session = Depends(get_db)) -> AppointmentResponse:
    """Record a new clinical encounter."""
    patient = session.query(Patient).filter(Patient.id == payload.patient_id).first()
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient ID {payload.patient_id} does not exist.",
        )

    apt_dt = payload.appointment_datetime
    if apt_dt.tzinfo is None:
        apt_dt = apt_dt.replace(tzinfo=timezone.utc)

    appointment = Appointment(
        patient_id=payload.patient_id,
        appointment_type=payload.appointment_type,
        appointment_datetime=apt_dt,
    )
    session.add(appointment)
    session.commit()
    session.refresh(appointment)

    anchor = utc_now()
    is_eligible = (apt_dt >= anchor - timedelta(days=7)) and (apt_dt < anchor)

    return AppointmentResponse(
        id=appointment.id,
        patient_id=appointment.patient_id,
        patient_name=f"{patient.first_name} {patient.last_name}",
        patient_email=patient.email,
        appointment_type=appointment.appointment_type,
        appointment_datetime=appointment.appointment_datetime,
        is_eligible=is_eligible,
        has_reminder=False,
        reminder_id=None,
        reminder_status=None,
        created_at=appointment.created_at,
    )
