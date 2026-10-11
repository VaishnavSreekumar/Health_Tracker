"""Patient ORM model definition."""

from datetime import datetime
from typing import TYPE_CHECKING, List
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime, utc_now

if TYPE_CHECKING:
    from app.models.appointment import Appointment


class Patient(Base):
    """Patient entity representing individuals receiving healthcare follow-up.

    Privacy Note:
    Names and emails are classified as PII. Patient email serves as the synthetic
    unique identifier. Avoid logging names and emails in application logs.
    """

    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        default=utc_now,
        nullable=False,
    )

    # Relationship to appointments
    appointments: Mapped[List["Appointment"]] = relationship(
        "Appointment",
        back_populates="patient",
        cascade="all, delete-orphan",
        order_by="Appointment.appointment_datetime",
    )

    def __repr__(self) -> str:
        # Avoid leaking PII (first_name, last_name, email) in string representation
        return f"<Patient(id={self.id})>"
