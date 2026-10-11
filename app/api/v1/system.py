"""System settings and controlled synthetic demonstration seed API routes."""

from datetime import datetime, timedelta, timezone
import logging
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import utc_now
from app.db.session import get_db
from app.models.appointment import Appointment, AppointmentType
from app.models.patient import Patient
from app.models.reminder import FollowUpReminder, ReminderStatus
from app.schemas.system import SystemSettingsResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/settings", response_model=SystemSettingsResponse, summary="Get Integration Readiness")
def get_system_settings() -> SystemSettingsResponse:
    """Return operational integration status without exposing credentials."""
    settings = get_settings()

    is_llm_configured = settings.is_gemini_enabled and bool(settings.effective_gemini_api_key)

    llm_status = (
        "configured"
        if is_llm_configured
        else ("unverified" if settings.llm_provider.lower() == "gemini" else "offline_fallback")
    )

    return SystemSettingsResponse(
        project_name=settings.project_name,
        version=settings.version,
        environment=settings.environment,
        database_type="SQLite (PRAGMA foreign_keys=ON, UTC timestamps)",
        llm_provider=settings.llm_provider,
        llm_model=settings.effective_gemini_model,
        llm_configured=is_llm_configured,
        llm_status=llm_status,
        delivery_provider="None",
        delivery_enabled=False,
        delivery_status="disabled_safe_mode",
    )


@router.post("/seed-demo", status_code=status.HTTP_200_OK, summary="Seed Controlled Demonstration Data")
def seed_demo_data(session: Session = Depends(get_db)) -> dict:
    """Populate database with synthetic clinical records across diverse lifecycle states.

    Includes:
    - Encounters within 7-day lookback window (eligible)
    - Encounters older than 7 days (ineligible)
    - Drafts pending human review
    - Approved reminders
    - Encounters ready to be drafted in the Follow-up Studio
    """
    anchor = utc_now()

    # Synthetic demo patients
    demo_patients_data = [
        ("Eleanor", "Vance", "eleanor.vance@example.synthetic"),
        ("Marcus", "Chen", "marcus.chen@example.synthetic"),
        ("Sophia", "Alvarez", "sophia.alvarez@example.synthetic"),
        ("David", "Kowalski", "david.kowalski@example.synthetic"),
        ("Amina", "Diallo", "amina.diallo@example.synthetic"),
        ("Julian", "Mercer", "julian.mercer@example.synthetic"),
    ]

    patients = []
    for first, last, email in demo_patients_data:
        existing = session.query(Patient).filter(Patient.email == email).first()
        if not existing:
            p = Patient(first_name=first, last_name=last, email=email)
            session.add(p)
            session.flush()
            patients.append(p)
        else:
            patients.append(existing)

    # 1. Eleanor Vance: Routine checkup 2 days ago -> Draft pending review
    apt1 = session.query(Appointment).filter(Appointment.patient_id == patients[0].id).first()
    if not apt1:
        apt1 = Appointment(
            patient_id=patients[0].id,
            appointment_type=AppointmentType.ROUTINE_CHECKUP,
            appointment_datetime=anchor - timedelta(days=2, hours=3),
        )
        session.add(apt1)
        session.flush()

        rem1 = FollowUpReminder(
            appointment_id=apt1.id,
            message_text="Hello Eleanor, thank you for attending your routine checkup. Please reach out if you have any questions or need further assistance.",
            original_text="Hello Eleanor, thank you for attending your routine checkup. Please reach out if you have any questions or need further assistance.",
            status=ReminderStatus.DRAFT,
            generation_source="template_fallback",
            fallback_reason="Offline mode: deterministic template selected for clinical consistency",
        )
        session.add(rem1)

    # 2. Marcus Chen: Follow-up visit 4 days ago -> Approved reminder
    apt2 = session.query(Appointment).filter(Appointment.patient_id == patients[1].id).first()
    if not apt2:
        apt2 = Appointment(
            patient_id=patients[1].id,
            appointment_type=AppointmentType.FOLLOW_UP,
            appointment_datetime=anchor - timedelta(days=4, hours=1),
        )
        session.add(apt2)
        session.flush()

        rem2 = FollowUpReminder(
            appointment_id=apt2.id,
            message_text="Hello Marcus, thank you for completing your follow-up appointment. Our care team is here to support your continued recovery and wellness.",
            original_text="Hello Marcus, thank you for attending your follow-up appointment.",
            status=ReminderStatus.APPROVED,
            generation_source="template_fallback",
            approved_at=anchor - timedelta(hours=6),
            approved_by="Clinical Reviewer",
        )
        session.add(rem2)

    # 3. Sophia Alvarez: Annual physical 1 day ago -> Ready to draft in Studio (no reminder yet)
    apt3 = session.query(Appointment).filter(Appointment.patient_id == patients[2].id).first()
    if not apt3:
        apt3 = Appointment(
            patient_id=patients[2].id,
            appointment_type=AppointmentType.ANNUAL_PHYSICAL,
            appointment_datetime=anchor - timedelta(days=1, hours=5),
        )
        session.add(apt3)

    # 4. David Kowalski: Specialist consultation 5 days ago -> Ready to draft in Studio
    apt4 = session.query(Appointment).filter(Appointment.patient_id == patients[3].id).first()
    if not apt4:
        apt4 = Appointment(
            patient_id=patients[3].id,
            appointment_type=AppointmentType.SPECIALIST_CONSULTATION,
            appointment_datetime=anchor - timedelta(days=5, hours=2),
        )
        session.add(apt4)

    # 5. Amina Diallo: Post-procedure 6 days ago -> Draft pending review
    apt5 = session.query(Appointment).filter(Appointment.patient_id == patients[4].id).first()
    if not apt5:
        apt5 = Appointment(
            patient_id=patients[4].id,
            appointment_type=AppointmentType.POST_PROCEDURE,
            appointment_datetime=anchor - timedelta(days=6, hours=4),
        )
        session.add(apt5)
        session.flush()

        rem5 = FollowUpReminder(
            appointment_id=apt5.id,
            message_text="Hello Amina, thank you for your post-procedure visit. Please contact our clinic team if you have any questions during your recovery.",
            original_text="Hello Amina, thank you for your post-procedure visit. Please contact our clinic team if you have any questions during your recovery.",
            status=ReminderStatus.DRAFT,
            generation_source="template_fallback",
            fallback_reason="Offline mode: deterministic template selected for clinical consistency",
        )
        session.add(rem5)

    # 6. Julian Mercer: Routine checkup 12 days ago (OUTSIDE 7-day lookback window)
    apt6 = session.query(Appointment).filter(Appointment.patient_id == patients[5].id).first()
    if not apt6:
        apt6 = Appointment(
            patient_id=patients[5].id,
            appointment_type=AppointmentType.ROUTINE_CHECKUP,
            appointment_datetime=anchor - timedelta(days=12),
        )
        session.add(apt6)

    session.commit()
    logger.info("Successfully seeded synthetic demonstration records.")
    return {
        "status": "success",
        "message": "Synthetic demonstration dataset loaded successfully.",
        "patients_count": len(patients),
    }


@router.post("/reset-demo", status_code=status.HTTP_200_OK, summary="Reset Demonstration Records")
def reset_demo_data(session: Session = Depends(get_db)) -> dict:
    """Clear synthetic demonstration records to return to a clean operational state."""
    session.query(FollowUpReminder).delete()
    session.query(Appointment).delete()
    session.query(Patient).delete()
    session.commit()
    return {"status": "success", "message": "All records cleared."}
