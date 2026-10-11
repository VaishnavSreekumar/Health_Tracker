"""Patient registration and directory API routes."""

import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.schemas.patient import (
    PatientCreate,
    PatientResponse,
    PatientWithAppointmentsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=List[PatientResponse], summary="List Patients")
def list_patients(session: Session = Depends(get_db)) -> List[PatientResponse]:
    """Retrieve list of registered patients with encounter counts."""
    patients = (
        session.query(Patient)
        .options(joinedload(Patient.appointments))
        .order_by(Patient.created_at.desc())
        .all()
    )
    return [
        PatientResponse(
            id=p.id,
            first_name=p.first_name,
            last_name=p.last_name,
            email=p.email,
            created_at=p.created_at,
            appointment_count=len(p.appointments),
        )
        for p in patients
    ]


@router.post("", response_model=PatientResponse, status_code=status.HTTP_201_CREATED, summary="Create Patient")
def create_patient(payload: PatientCreate, session: Session = Depends(get_db)) -> PatientResponse:
    """Register a new synthetic patient record."""
    existing = session.query(Patient).filter(Patient.email == payload.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Patient with email '{payload.email}' already exists.",
        )

    patient = Patient(
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        email=payload.email.lower().strip(),
    )
    session.add(patient)
    session.commit()
    session.refresh(patient)

    return PatientResponse(
        id=patient.id,
        first_name=patient.first_name,
        last_name=patient.last_name,
        email=patient.email,
        created_at=patient.created_at,
        appointment_count=0,
    )


@router.get("/{patient_id}", response_model=PatientWithAppointmentsResponse, summary="Get Patient Detail")
def get_patient(patient_id: int, session: Session = Depends(get_db)) -> PatientWithAppointmentsResponse:
    """Retrieve single patient record with associated encounters."""
    patient = (
        session.query(Patient)
        .options(joinedload(Patient.appointments))
        .filter(Patient.id == patient_id)
        .first()
    )
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")

    apts = [
        {
            "id": a.id,
            "appointment_type": a.appointment_type.value,
            "appointment_datetime": a.appointment_datetime.isoformat(),
            "has_reminder": a.reminder is not None,
            "reminder_id": a.reminder.id if a.reminder else None,
            "reminder_status": a.reminder.status.value if a.reminder else None,
        }
        for a in patient.appointments
    ]

    return PatientWithAppointmentsResponse(
        id=patient.id,
        first_name=patient.first_name,
        last_name=patient.last_name,
        email=patient.email,
        created_at=patient.created_at,
        appointment_count=len(patient.appointments),
        appointments=apts,
    )
