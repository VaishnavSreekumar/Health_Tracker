"""Tests for ORM models, relationships, and lifecycle semantics."""

from datetime import datetime, timezone
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment, AppointmentType
from app.models.patient import Patient
from app.models.reminder import FollowUpReminder, ReminderStatus


def test_patient_persistence_and_retrieval(db_session: Session) -> None:
    """Verify that a synthetic patient record can be created, committed, and retrieved."""
    new_patient = Patient(
        first_name="Synthetic",
        last_name="PatientA",
        email="synthetic.patient.a@example.com",
    )
    db_session.add(new_patient)
    db_session.commit()

    retrieved = db_session.scalar(
        select(Patient).where(Patient.email == "synthetic.patient.a@example.com")
    )
    assert retrieved is not None
    assert retrieved.id is not None
    assert retrieved.first_name == "Synthetic"
    assert retrieved.last_name == "PatientA"
    assert retrieved.created_at.tzinfo == timezone.utc


def test_patient_repr_protects_pii() -> None:
    """Verify that Patient.__repr__ does not expose patient names or emails."""
    patient_instance = Patient(
        id=42,
        first_name="SecretFirst",
        last_name="SecretLast",
        email="secret@example.com",
    )
    repr_str = repr(patient_instance)
    assert "SecretFirst" not in repr_str
    assert "SecretLast" not in repr_str
    assert "secret@example.com" not in repr_str
    assert "Patient(id=42)" in repr_str


def test_appointment_belongs_to_patient(db_session: Session) -> None:
    """Verify appointment creation and many-to-one relationship to Patient."""
    patient_rec = Patient(
        first_name="Synthetic",
        last_name="PatientB",
        email="synthetic.patient.b@example.com",
    )
    db_session.add(patient_rec)
    db_session.commit()

    apt_time = datetime(2026, 10, 15, 14, 30, tzinfo=timezone.utc)
    appointment = Appointment(
        patient_id=patient_rec.id,
        appointment_type=AppointmentType.ROUTINE_CHECKUP,
        appointment_datetime=apt_time,
    )
    db_session.add(appointment)
    db_session.commit()

    # Retrieve and verify bidirectional navigation
    db_session.expire_all()
    loaded_apt = db_session.get(Appointment, appointment.id)
    assert loaded_apt is not None
    assert loaded_apt.patient_id == patient_rec.id
    assert loaded_apt.patient.email == "synthetic.patient.b@example.com"
    assert loaded_apt.appointment_type == AppointmentType.ROUTINE_CHECKUP
    assert loaded_apt.appointment_datetime == apt_time

    # Verify patient side
    loaded_patient = db_session.get(Patient, patient_rec.id)
    assert loaded_patient is not None
    assert len(loaded_patient.appointments) == 1
    assert loaded_patient.appointments[0].id == appointment.id


def test_reminder_belongs_to_appointment(db_session: Session) -> None:
    """Verify follow-up reminder creation and 1:1 relationship with Appointment."""
    patient_rec = Patient(
        first_name="Synthetic",
        last_name="PatientC",
        email="synthetic.patient.c@example.com",
    )
    db_session.add(patient_rec)
    db_session.commit()

    appointment = Appointment(
        patient_id=patient_rec.id,
        appointment_type=AppointmentType.FOLLOW_UP,
        appointment_datetime=datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc),
    )
    db_session.add(appointment)
    db_session.commit()

    reminder = FollowUpReminder(
        appointment_id=appointment.id,
        message_text="Hello, this is a synthetic follow-up reminder regarding your recent visit.",
        status=ReminderStatus.DRAFT,
    )
    db_session.add(reminder)
    db_session.commit()

    db_session.expire_all()
    loaded_reminder = db_session.get(FollowUpReminder, reminder.id)
    assert loaded_reminder is not None
    assert loaded_reminder.appointment_id == appointment.id
    assert loaded_reminder.status == ReminderStatus.DRAFT
    assert loaded_reminder.appointment.patient.id == patient_rec.id

    # Verify navigating from appointment to reminder
    loaded_apt = db_session.get(Appointment, appointment.id)
    assert loaded_apt is not None
    assert loaded_apt.reminder is not None
    assert loaded_apt.reminder.id == reminder.id


def test_cascade_delete_patient_removes_appointments_and_reminders(
    db_session: Session,
) -> None:
    """Verify that deleting a patient cascades to appointments and reminders."""
    patient_rec = Patient(
        first_name="Synthetic",
        last_name="PatientD",
        email="synthetic.patient.d@example.com",
    )
    db_session.add(patient_rec)
    db_session.commit()

    appointment = Appointment(
        patient_id=patient_rec.id,
        appointment_type=AppointmentType.SPECIALIST_CONSULTATION,
        appointment_datetime=datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc),
    )
    db_session.add(appointment)
    db_session.commit()

    reminder = FollowUpReminder(
        appointment_id=appointment.id,
        message_text="Synthetic reminder message.",
        status=ReminderStatus.DRAFT,
    )
    db_session.add(reminder)
    db_session.commit()

    apt_id = appointment.id
    reminder_id = reminder.id

    # Delete the owning patient
    db_session.delete(patient_rec)
    db_session.commit()

    # Assert children are cleaned up
    assert db_session.get(Appointment, apt_id) is None
    assert db_session.get(FollowUpReminder, reminder_id) is None


def test_timezone_normalization_on_storage_and_retrieval(db_session: Session) -> None:
    """Verify that timezone-aware datetimes preserve UTC normalization across SQLite."""
    patient_rec = Patient(
        first_name="Synthetic",
        last_name="PatientE",
        email="synthetic.patient.e@example.com",
    )
    db_session.add(patient_rec)
    db_session.commit()

    # Appointment with UTC aware timestamp
    utc_dt = datetime(2026, 10, 25, 16, 45, tzinfo=timezone.utc)
    appointment = Appointment(
        patient_id=patient_rec.id,
        appointment_type=AppointmentType.ANNUAL_PHYSICAL,
        appointment_datetime=utc_dt,
    )
    db_session.add(appointment)
    db_session.commit()

    db_session.expire_all()
    loaded_apt = db_session.get(Appointment, appointment.id)
    assert loaded_apt is not None
    assert loaded_apt.appointment_datetime.tzinfo is not None
    assert loaded_apt.appointment_datetime.tzinfo == timezone.utc
    assert loaded_apt.appointment_datetime == utc_dt
    assert loaded_apt.created_at.tzinfo == timezone.utc
