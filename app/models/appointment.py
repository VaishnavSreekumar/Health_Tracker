"""Appointment ORM model definition and supported appointment types."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional
from sqlalchemy import Enum as SQLEnum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime, utc_now

if TYPE_CHECKING:
    from app.models.patient import Patient
    from app.models.reminder import FollowUpReminder


class AppointmentType(str, Enum):
    """Categorization of clinical encounters for follow-up workflows."""

    ROUTINE_CHECKUP = "routine_checkup"
    FOLLOW_UP = "follow_up"
    SPECIALIST_CONSULTATION = "specialist_consultation"
    ANNUAL_PHYSICAL = "annual_physical"
    POST_PROCEDURE = "post_procedure"


class Appointment(Base):
    """Appointment entity linking clinical encounters with patients and follow-ups.

    Timezone Policy:
    All appointment datetimes and timestamps are stored in UTC with explicit
    timezone normalization handled by UTCDateTime.
    """

    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    appointment_type: Mapped[AppointmentType] = mapped_column(
        SQLEnum(AppointmentType, native_enum=False, length=50),
        nullable=False,
        index=True,
    )
    appointment_datetime: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        default=utc_now,
        nullable=False,
    )

    # Relationships
    patient: Mapped["Patient"] = relationship(
        "Patient",
        back_populates="appointments",
    )
    reminder: Mapped[Optional["FollowUpReminder"]] = relationship(
        "FollowUpReminder",
        back_populates="appointment",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<Appointment(id={self.id}, patient_id={self.patient_id}, "
            f"type='{self.appointment_type.value}', datetime='{self.appointment_datetime.isoformat()}')>"
        )
