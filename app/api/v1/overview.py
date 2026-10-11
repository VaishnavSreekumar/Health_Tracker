"""Operational overview and analytics API routes."""

from datetime import timedelta
import logging
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from app.db.base import utc_now
from app.db.session import get_db
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.reminder import FollowUpReminder, ReminderStatus
from app.schemas.overview import ActivityItemResponse, OverviewMetricsResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/metrics", response_model=OverviewMetricsResponse, summary="Get Overview Metrics")
def get_overview_metrics(session: Session = Depends(get_db)) -> OverviewMetricsResponse:
    """Calculate operational metrics derived directly from database state."""
    anchor = utc_now()
    seven_days_ago = anchor - timedelta(days=7)

    total_patients = session.query(Patient).count()
    total_appointments = session.query(Appointment).count()
    eligible_appointments = (
        session.query(Appointment)
        .filter(
            Appointment.appointment_datetime >= seven_days_ago,
            Appointment.appointment_datetime < anchor,
        )
        .count()
    )

    drafts = session.query(FollowUpReminder).filter(FollowUpReminder.status == ReminderStatus.DRAFT).count()
    approved = session.query(FollowUpReminder).filter(FollowUpReminder.status == ReminderStatus.APPROVED).count()
    dispatched = session.query(FollowUpReminder).filter(FollowUpReminder.status == ReminderStatus.SENT).count()
    failed = session.query(FollowUpReminder).filter(FollowUpReminder.status == ReminderStatus.FAILED).count()

    ai_count = session.query(FollowUpReminder).filter(FollowUpReminder.generation_source == "ai").count()
    fallback_count = (
        session.query(FollowUpReminder)
        .filter(FollowUpReminder.generation_source == "template_fallback")
        .count()
    )

    return OverviewMetricsResponse(
        total_patients=total_patients,
        total_appointments=total_appointments,
        eligible_appointments=eligible_appointments,
        drafts_pending_review=drafts,
        approved_reminders=approved,
        dispatched_reminders=dispatched,
        failed_deliveries=failed,
        ai_generated_count=ai_count,
        fallback_count=fallback_count,
    )


@router.get("/activity", response_model=List[ActivityItemResponse], summary="Get Recent Activity")
def get_recent_activity(session: Session = Depends(get_db)) -> List[ActivityItemResponse]:
    """Retrieve recent operational actions across reminder lifecycle."""
    reminders = (
        session.query(FollowUpReminder)
        .options(joinedload(FollowUpReminder.appointment).joinedload(Appointment.patient))
        .order_by(FollowUpReminder.created_at.desc())
        .limit(10)
        .all()
    )

    activity = []
    for r in reminders:
        patient = r.appointment.patient if r.appointment else None
        p_name = f"{patient.first_name} {patient.last_name}" if patient else "Patient"

        if r.status == ReminderStatus.APPROVED:
            action_type = "approved"
            detail = f"Draft approved by {r.approved_by or 'clinical operator'}"
            ts = r.approved_at or r.created_at
        elif r.status == ReminderStatus.REJECTED:
            action_type = "rejected"
            detail = "Draft rejected during human review"
            ts = r.created_at
        elif r.is_edited if hasattr(r, "is_edited") else (r.original_text and r.original_text != r.message_text):
            action_type = "edited"
            detail = "Draft message text edited"
            ts = r.created_at
        else:
            action_type = "draft_created"
            detail = (
                f"Generated via AI ({r.model_name or 'model'})"
                if r.generation_source == "ai"
                else "Drafted via deterministic template fallback"
            )
            ts = r.created_at

        activity.append(
            ActivityItemResponse(
                id=r.id,
                reminder_id=r.id,
                appointment_id=r.appointment_id,
                patient_name=p_name,
                action_type=action_type,
                timestamp=ts,
                detail=detail,
            )
        )

    return activity
