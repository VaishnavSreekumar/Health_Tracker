"""Tests for database constraints, foreign-key integrity, and test isolation."""

from datetime import datetime, timezone
from pathlib import Path
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.appointment import Appointment, AppointmentType
from app.models.patient import Patient
from app.models.reminder import FollowUpReminder, ReminderStatus


def test_unique_patient_email_constraint(db_session: Session) -> None:
    """Verify that inserting duplicate patient email raises IntegrityError."""
    p1 = Patient(
        first_name="Duplicate",
        last_name="One",
        email="duplicate.email@example.com",
    )
    db_session.add(p1)
    db_session.commit()

    p2 = Patient(
        first_name="Duplicate",
        last_name="Two",
        email="duplicate.email@example.com",
    )
    db_session.add(p2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_sqlite_foreign_key_enforcement_for_appointment(db_session: Session) -> None:
    """Verify that foreign key constraints are enforced when inserting appointment with nonexistent patient."""
    invalid_appointment = Appointment(
        patient_id=999999,  # Non-existent patient ID
        appointment_type=AppointmentType.ROUTINE_CHECKUP,
        appointment_datetime=datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc),
    )
    db_session.add(invalid_appointment)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_sqlite_foreign_key_enforcement_for_reminder(db_session: Session) -> None:
    """Verify that foreign key constraints are enforced when inserting reminder with nonexistent appointment."""
    invalid_reminder = FollowUpReminder(
        appointment_id=888888,  # Non-existent appointment ID
        message_text="Orphan reminder message text.",
        status=ReminderStatus.DRAFT,
    )
    db_session.add(invalid_reminder)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_unique_reminder_per_appointment_constraint(db_session: Session) -> None:
    """Verify that attempting to create a second reminder for the same appointment is rejected by the database."""
    patient = Patient(
        first_name="Synthetic",
        last_name="ConstraintPatient",
        email="constraint.patient@example.com",
    )
    db_session.add(patient)
    db_session.commit()

    appointment = Appointment(
        patient_id=patient.id,
        appointment_type=AppointmentType.ROUTINE_CHECKUP,
        appointment_datetime=datetime(2026, 10, 22, 11, 0, tzinfo=timezone.utc),
    )
    db_session.add(appointment)
    db_session.commit()

    # First reminder succeeds
    first_reminder = FollowUpReminder(
        appointment_id=appointment.id,
        message_text="Initial reminder message.",
        status=ReminderStatus.DRAFT,
    )
    db_session.add(first_reminder)
    db_session.commit()

    # Second reminder for same appointment must fail with IntegrityError
    second_reminder = FollowUpReminder(
        appointment_id=appointment.id,
        message_text="Duplicate reminder message that violates policy.",
        status=ReminderStatus.DRAFT,
    )
    db_session.add(second_reminder)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_required_nullable_fields_enforced(db_session: Session) -> None:
    """Verify that null values for non-nullable columns raise IntegrityError."""
    # Patient missing non-null email
    invalid_patient = Patient(
        first_name="NoEmail",
        last_name="Patient",
        email=None,  # type: ignore
    )
    db_session.add(invalid_patient)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_database_isolation_does_not_modify_local_db(db_session: Session) -> None:
    """Verify that tests execute in memory and do not write test records to healthtrack.db."""
    # Verify the test session engine is strictly in-memory
    assert db_session.bind is not None
    assert db_session.bind.url.database == ":memory:"

    # Write a record into the test session
    p = Patient(
        first_name="Isolated",
        last_name="Test",
        email="isolated.test@example.com",
    )
    db_session.add(p)
    db_session.commit()

    # Verify that the test record was not written to local healthtrack.db
    local_db_path = Path("healthtrack.db")
    if local_db_path.exists():
        import sqlite3

        conn = sqlite3.connect("healthtrack.db")
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='patients'")
        if cur.fetchone():
            cur.execute("SELECT COUNT(*) FROM patients WHERE email='isolated.test@example.com'")
            count = cur.fetchone()[0]
            assert count == 0
        conn.close()
    else:
        assert not local_db_path.exists(), "Local database file should not be touched during tests"


def test_session_isolation_state_cleanup_a(db_session: Session) -> None:
    """Part A of isolation check: inserting record A."""
    p = Patient(
        first_name="IsolatedA",
        last_name="UserA",
        email="isolated.a@example.com",
    )
    db_session.add(p)
    db_session.commit()
    assert db_session.scalar(select(Patient).where(Patient.email == "isolated.a@example.com")) is not None


def test_session_isolation_state_cleanup_b(db_session: Session) -> None:
    """Part B of isolation check: verifying record A does not exist in a new test session."""
    assert db_session.scalar(select(Patient).where(Patient.email == "isolated.a@example.com")) is None
