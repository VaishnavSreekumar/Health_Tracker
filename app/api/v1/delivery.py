"""Message delivery log API routes."""

import logging
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.reminder import FollowUpReminder, ReminderStatus

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/logs", summary="List Delivery Logs")
def get_delivery_logs(session: Session = Depends(get_db)) -> List[dict]:
    """Retrieve transmission log for outbound reminders."""
    reminders = (
        session.query(FollowUpReminder)
        .options(joinedload(FollowUpReminder.appointment).joinedload(Appointment.patient))
        .filter(FollowUpReminder.status.in_([ReminderStatus.SENT, ReminderStatus.FAILED, ReminderStatus.PENDING]))
        .order_by(FollowUpReminder.created_at.desc())
        .all()
    )

    logs = []
    for r in reminders:
        patient = r.appointment.patient if r.appointment else None
        logs.append({
            "id": r.id,
            "reminder_id": r.id,
            "patient_name": f"{patient.first_name} {patient.last_name}" if patient else "Unknown",
            "patient_email": patient.email if patient else "",
            "status": r.status.value,
            "provider": r.delivery_provider or "None (Unconfigured)",
            "reference_id": r.delivery_reference_id,
            "error_detail": r.delivery_error,
            "created_at": r.created_at.isoformat(),
        })

    return logs
