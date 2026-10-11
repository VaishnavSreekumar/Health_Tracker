"""Unit tests for ReminderGenerationService orchestration, idempotency, and error handling."""

from datetime import datetime, timedelta, timezone
import logging
import pytest
from sqlalchemy.orm import Session

from app.models.appointment import Appointment, AppointmentType
from app.models.patient import Patient
from app.models.reminder import FollowUpReminder, ReminderStatus
from app.services.generator import GenerationResult, ReminderGenerationService
from app.services.personalizer import MessagePersonalizer


@pytest.fixture
def service() -> ReminderGenerationService:
    return ReminderGenerationService()


def create_patient_and_appointment(
    db_session: Session,
    first_name: str = "Elena",
    last_name: str = "Rostova",
    email: str = "elena.rostova@example.com",
    appointment_type: AppointmentType = AppointmentType.ROUTINE_CHECKUP,
    days_ago: int = 3,
    ref_time: datetime | None = None,
) -> tuple[Patient, Appointment]:
    anchor = ref_time or datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    patient = Patient(
        first_name=first_name,
        last_name=last_name,
        email=email,
    )
    db_session.add(patient)
    db_session.commit()

    apt = Appointment(
        patient_id=patient.id,
        appointment_type=appointment_type,
        appointment_datetime=anchor - timedelta(days=days_ago),
    )
    db_session.add(apt)
    db_session.commit()
    return patient, apt


def test_successful_reminder_generation_and_persistence(
    db_session: Session, service: ReminderGenerationService
) -> None:
    """Verify that eligible appointments result in persisted draft reminders."""
    ref_time = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    patient, apt = create_patient_and_appointment(
        db_session,
        first_name="Marcus",
        email="marcus.test@example.com",
        appointment_type=AppointmentType.ROUTINE_CHECKUP,
        days_ago=2,
        ref_time=ref_time,
    )

    result = service.generate_reminders(db_session, reference_time=ref_time)

    assert result.total_reviewed == 1
    assert result.reminders_created == 1
    assert result.reminders_skipped == 0
    assert result.failures == 0
    assert len(result.created_reminder_ids) == 1

    # Verify database persistence
    db_session.expire_all()
    created_reminder = db_session.get(FollowUpReminder, result.created_reminder_ids[0])
    assert created_reminder is not None
    assert created_reminder.appointment_id == apt.id
    assert created_reminder.status == ReminderStatus.DRAFT
    assert "Marcus" in created_reminder.message_text
    assert created_reminder.created_at.tzinfo == timezone.utc


def test_idempotent_repeated_invocation(
    db_session: Session, service: ReminderGenerationService
) -> None:
    """Verify that executing generation multiple times does not produce duplicate reminders."""
    ref_time = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    create_patient_and_appointment(
        db_session,
        first_name="Ida",
        email="ida.repeat@example.com",
        days_ago=4,
        ref_time=ref_time,
    )

    # First invocation: creates 1 reminder
    res1 = service.generate_reminders(db_session, reference_time=ref_time)
    assert res1.total_reviewed == 1
    assert res1.reminders_created == 1
    assert res1.reminders_skipped == 0

    # Second invocation: skips existing reminder
    res2 = service.generate_reminders(db_session, reference_time=ref_time)
    assert res2.total_reviewed == 1
    assert res2.reminders_created == 0
    assert res2.reminders_skipped == 1
    assert res2.failures == 0


def test_existing_reminder_is_skipped(
    db_session: Session, service: ReminderGenerationService
) -> None:
    """Verify that an appointment already possessing a reminder is counted as skipped."""
    ref_time = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    patient, apt = create_patient_and_appointment(
        db_session,
        first_name="PreExisting",
        email="preexisting@example.com",
        days_ago=1,
        ref_time=ref_time,
    )

    # Manually pre-seed an existing reminder
    existing_reminder = FollowUpReminder(
        appointment_id=apt.id,
        message_text="Pre-existing draft message.",
        status=ReminderStatus.DRAFT,
    )
    db_session.add(existing_reminder)
    db_session.commit()

    result = service.generate_reminders(db_session, reference_time=ref_time)
    assert result.total_reviewed == 1
    assert result.reminders_created == 0
    assert result.reminders_skipped == 1
    assert result.failures == 0


def test_individual_record_failure_does_not_halt_batch(db_session: Session) -> None:
    """Verify that if one appointment encounters an error, subsequent appointments still succeed."""
    ref_time = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)

    # Create two appointments
    _, apt1 = create_patient_and_appointment(
        db_session,
        first_name="FailMe",
        email="fail.me@example.com",
        days_ago=2,
        ref_time=ref_time,
    )
    _, apt2 = create_patient_and_appointment(
        db_session,
        first_name="SucceedMe",
        email="succeed.me@example.com",
        days_ago=3,
        ref_time=ref_time,
    )

    # Faulty personalizer that raises on apt1 but succeeds on apt2
    class FaultyPersonalizer:
        def personalize_reminder(self, appointment: Appointment) -> str:
            if appointment.id == apt1.id:
                raise RuntimeError("Simulated formatting failure")
            return f"Hello, successful appointment {appointment.id}."

    faulty_service = ReminderGenerationService(personalizer=FaultyPersonalizer())
    result = faulty_service.generate_reminders(db_session, reference_time=ref_time)

    assert result.total_reviewed == 2
    assert result.reminders_created == 1
    assert result.failures == 1
    assert result.failed_appointment_ids == [apt1.id]
    assert len(result.created_reminder_ids) == 1

    # Verify apt2 reminder was committed and persisted
    db_session.expire_all()
    apt2_reminder = db_session.get(FollowUpReminder, result.created_reminder_ids[0])
    assert apt2_reminder is not None
    assert apt2_reminder.appointment_id == apt2.id


def test_concurrency_race_condition_handling_via_savepoint(
    db_session: Session, service: ReminderGenerationService
) -> None:
    """Verify that concurrent duplicate insertion caught via IntegrityError increments reminders_skipped."""
    ref_time = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    _, apt = create_patient_and_appointment(
        db_session,
        first_name="Racer",
        email="racer@example.com",
        days_ago=2,
        ref_time=ref_time,
    )

    # Intercept personalizer to simulate a concurrent worker inserting a reminder right before savepoint flush
    class InterceptingPersonalizer:
        def personalize_reminder(self, appointment: Appointment) -> str:
            # Simulate a concurrent transaction committing a reminder
            concurrent_reminder = FollowUpReminder(
                appointment_id=appointment.id,
                message_text="Concurrent reminder inserted by background worker.",
                status=ReminderStatus.DRAFT,
            )
            db_session.add(concurrent_reminder)
            db_session.flush()
            return "My reminder text."

    race_service = ReminderGenerationService(personalizer=InterceptingPersonalizer())
    result = race_service.generate_reminders(db_session, reference_time=ref_time)

    # Caught IntegrityError in begin_nested savepoint, recovered, and counted as skipped
    assert result.total_reviewed == 1
    assert result.reminders_created == 0
    assert result.reminders_skipped == 1
    assert result.failures == 0


def test_logging_contains_no_patient_pii(
    db_session: Session, service: ReminderGenerationService, caplog: pytest.LogCaptureFixture
) -> None:
    """Verify that logging statements contain internal IDs and counts but zero patient PII."""
    ref_time = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    first_name = "SuperSecretName"
    email = "supersecret.email@example.com"

    create_patient_and_appointment(
        db_session,
        first_name=first_name,
        email=email,
        days_ago=2,
        ref_time=ref_time,
    )

    with caplog.at_level(logging.DEBUG):
        result = service.generate_reminders(db_session, reference_time=ref_time)

    assert result.reminders_created == 1

    # Check all captured log output
    full_log_text = caplog.text
    assert first_name not in full_log_text, "Patient first name must not appear in logs"
    assert email not in full_log_text, "Patient email must not appear in logs"
    assert "SuperSecretName" not in full_log_text

    # Verify required operational information is present
    assert "Reminder generation complete:" in full_log_text
    assert "reviewed=1" in full_log_text
    assert "created=1" in full_log_text
    assert "appointment_id=" in full_log_text
