"""FollowUpReminder ORM model definition and lifecycle statuses."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional
from sqlalchemy import Enum as SQLEnum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime, utc_now

if TYPE_CHECKING:
    from app.models.appointment import Appointment


class ReminderStatus(str, Enum):
    """Lifecycle states of a generated follow-up reminder."""

    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"

class ReminderStatusType(TypeDecorator):
    """Robust SQL type handling both canonical uppercase enum names ('DRAFT')
    and legacy/raw lowercase values ('draft').

    Always writes canonical uppercase representation ('DRAFT') to the database.
    """

    impl = String(20)
    cache_ok = True

    def process_bind_param(self, value, dialect) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, ReminderStatus):
            return value.name
        if isinstance(value, str):
            clean = value.strip().upper()
            if clean in ReminderStatus.__members__:
                return clean
            for member in ReminderStatus:
                if member.value.upper() == clean:
                    return member.name
            raise ValueError(f"'{value}' is not a valid ReminderStatus")
        return str(value)

    def process_result_value(self, value, dialect) -> Optional[ReminderStatus]:
        if value is None:
            return None
        if isinstance(value, ReminderStatus):
            return value
        if isinstance(value, str):
            clean = value.strip().upper()
            if clean in ReminderStatus.__members__:
                return ReminderStatus[clean]
            for member in ReminderStatus:
                if member.value.upper() == clean:
                    return member
        raise LookupError(f"'{value}' is not among the defined enum values for ReminderStatus")


class FollowUpReminder(Base):
    """Follow-up reminder associated with an appointment.

    Architecture Note on Duplicate Prevention:
    Initial product policy mandates at most one follow-up reminder per appointment.
    This rule is enforced at the database level via a UniqueConstraint on appointment_id,
    preventing concurrent race conditions or accidental duplicates from producing
    multiple reminders for the same clinical encounter.
    """

    __tablename__ = "follow_up_reminders"
    __table_args__ = (
        UniqueConstraint("appointment_id", name="uq_follow_up_reminders_appointment_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    appointment_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("appointments.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ReminderStatus] = mapped_column(
        ReminderStatusType(),
        default=ReminderStatus.DRAFT,
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        default=utc_now,
        nullable=False,
    )

    # Operational & Provenance Audit Fields
    generation_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, default="template_fallback")
    model_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    fallback_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    original_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    delivery_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    delivery_reference_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    delivery_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    appointment: Mapped["Appointment"] = relationship(
        "Appointment",
        back_populates="reminder",
    )

    def __repr__(self) -> str:
        return (
            f"<FollowUpReminder(id={self.id}, appointment_id={self.appointment_id}, "
            f"status='{self.status.value}')>"
        )
