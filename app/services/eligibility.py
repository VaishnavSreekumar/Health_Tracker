"""Appointment eligibility service for follow-up outreach.

Eligibility Criteria:
- Encounters occurring within the previous 7 days (by default).
- Lower boundary: Inclusive (appointment_datetime >= reference_time - window_days).
- Upper boundary: Exclusive (appointment_datetime < reference_time).
- Encounters in the future (>= reference_time) are strictly excluded.
- All datetimes are normalized to UTC before querying.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.base import utc_now
from app.models.appointment import Appointment


def normalize_to_utc(dt: Optional[datetime]) -> datetime:
    """Normalize a datetime to timezone-aware UTC.

    Treats naive datetimes as UTC and converts aware datetimes into UTC.
    """
    if dt is None:
        return utc_now()
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def get_eligible_appointments(
    session: Session,
    reference_time: Optional[datetime] = None,
    window_days: int = 7,
) -> List[Appointment]:
    """Retrieve appointments eligible for follow-up reminders.

    Args:
        session: Active SQLAlchemy database session.
        reference_time: Evaluation anchor time. Defaults to current UTC time.
        window_days: Lookback duration in days (default: 7).

    Returns:
        List of Appointment instances falling within [reference_time - window_days, reference_time).
    """
    ref_utc = normalize_to_utc(reference_time)
    window_start = ref_utc - timedelta(days=window_days)
    window_end = ref_utc

    stmt = (
        select(Appointment)
        .options(
            joinedload(Appointment.patient),
            joinedload(Appointment.reminder),
        )
        .where(
            Appointment.appointment_datetime >= window_start,
            Appointment.appointment_datetime < window_end,
        )
        .order_by(Appointment.appointment_datetime.asc())
    )

    return list(session.scalars(stmt).unique().all())
