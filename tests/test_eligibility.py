"""Unit tests for appointment eligibility evaluation and boundary conditions."""

from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy.orm import Session

from app.models.appointment import Appointment, AppointmentType
from app.models.patient import Patient
from app.services.eligibility import get_eligible_appointments, normalize_to_utc


@pytest.fixture
def test_patient(db_session: Session) -> Patient:
    patient = Patient(
        first_name="Eligible",
        last_name="Subject",
        email="eligible.subject@example.com",
    )
    db_session.add(patient)
    db_session.commit()
    return patient


def test_empty_eligible_appointment_batches(db_session: Session) -> None:
    """Verify that empty database returns empty list without error."""
    ref_time = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    results = get_eligible_appointments(db_session, reference_time=ref_time)
    assert results == []


def test_appointment_exactly_at_lower_boundary_is_eligible(
    db_session: Session, test_patient: Patient
) -> None:
    """Verify that an encounter exactly 7 days prior to reference time is INCLUDED (inclusive lower bound)."""
    ref_time = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    lower_bound_time = ref_time - timedelta(days=7)  # 2026-10-08 12:00:00

    apt = Appointment(
        patient_id=test_patient.id,
        appointment_type=AppointmentType.ROUTINE_CHECKUP,
        appointment_datetime=lower_bound_time,
    )
    db_session.add(apt)
    db_session.commit()

    eligible = get_eligible_appointments(db_session, reference_time=ref_time)
    assert len(eligible) == 1
    assert eligible[0].id == apt.id


def test_appointment_older_than_seven_days_is_excluded(
    db_session: Session, test_patient: Patient
) -> None:
    """Verify that an encounter even 1 second before the 7-day window is EXCLUDED."""
    ref_time = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    too_old_time = ref_time - timedelta(days=7, seconds=1)

    apt = Appointment(
        patient_id=test_patient.id,
        appointment_type=AppointmentType.ROUTINE_CHECKUP,
        appointment_datetime=too_old_time,
    )
    db_session.add(apt)
    db_session.commit()

    eligible = get_eligible_appointments(db_session, reference_time=ref_time)
    assert eligible == []


def test_future_appointments_are_excluded(
    db_session: Session, test_patient: Patient
) -> None:
    """Verify that appointments at or after the reference time are EXCLUDED (exclusive upper bound)."""
    ref_time = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)

    # Encounter exactly at reference time
    apt_at_ref = Appointment(
        patient_id=test_patient.id,
        appointment_type=AppointmentType.FOLLOW_UP,
        appointment_datetime=ref_time,
    )
    # Encounter in the future
    apt_future = Appointment(
        patient_id=test_patient.id,
        appointment_type=AppointmentType.FOLLOW_UP,
        appointment_datetime=ref_time + timedelta(hours=2),
    )
    db_session.add_all([apt_at_ref, apt_future])
    db_session.commit()

    eligible = get_eligible_appointments(db_session, reference_time=ref_time)
    assert eligible == []


def test_appointments_within_interval_are_included(
    db_session: Session, test_patient: Patient
) -> None:
    """Verify encounters strictly inside the 7-day window are returned and sorted."""
    ref_time = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)

    apt1 = Appointment(
        patient_id=test_patient.id,
        appointment_type=AppointmentType.ROUTINE_CHECKUP,
        appointment_datetime=ref_time - timedelta(days=5),
    )
    apt2 = Appointment(
        patient_id=test_patient.id,
        appointment_type=AppointmentType.ANNUAL_PHYSICAL,
        appointment_datetime=ref_time - timedelta(days=2),
    )
    db_session.add_all([apt1, apt2])
    db_session.commit()

    eligible = get_eligible_appointments(db_session, reference_time=ref_time)
    assert len(eligible) == 2
    assert eligible[0].id == apt1.id
    assert eligible[1].id == apt2.id


def test_naive_datetime_handling_normalized_to_utc(
    db_session: Session, test_patient: Patient
) -> None:
    """Verify naive datetimes passed as reference_time are safely treated as UTC."""
    # Naive reference time
    naive_ref = datetime(2026, 10, 15, 12, 0)
    apt_time = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)

    apt = Appointment(
        patient_id=test_patient.id,
        appointment_type=AppointmentType.POST_PROCEDURE,
        appointment_datetime=apt_time,
    )
    db_session.add(apt)
    db_session.commit()

    # Query using naive datetime
    eligible = get_eligible_appointments(db_session, reference_time=naive_ref)
    assert len(eligible) == 1
    assert eligible[0].id == apt.id


def test_configurable_window_days(
    db_session: Session, test_patient: Patient
) -> None:
    """Verify window_days parameter restricts or expands the lookback interval."""
    ref_time = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)

    # 4 days ago
    apt = Appointment(
        patient_id=test_patient.id,
        appointment_type=AppointmentType.ROUTINE_CHECKUP,
        appointment_datetime=ref_time - timedelta(days=4),
    )
    db_session.add(apt)
    db_session.commit()

    # 3-day window excludes 4-day-old appointment
    eligible_3d = get_eligible_appointments(
        db_session, reference_time=ref_time, window_days=3
    )
    assert eligible_3d == []

    # 5-day window includes 4-day-old appointment
    eligible_5d = get_eligible_appointments(
        db_session, reference_time=ref_time, window_days=5
    )
    assert len(eligible_5d) == 1
