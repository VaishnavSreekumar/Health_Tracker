"""Tests for POST /api/v1/reminders/generate endpoint."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from app.api.v1.reminders import get_reminder_service
from app.models.appointment import Appointment, AppointmentType
from app.models.patient import Patient
from app.models.reminder import FollowUpReminder, ReminderStatus
from app.services.generator import ReminderGenerationService


def seed_appointment(
    db_session: Session,
    first_name: str = "Tanya",
    days_ago: int = 3,
    ref_time: datetime | None = None,
) -> tuple[Patient, Appointment]:
    anchor = ref_time or datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    patient = Patient(
        first_name=first_name,
        last_name="Novak",
        email=f"{first_name.lower()}.novak@example.com",
    )
    db_session.add(patient)
    db_session.commit()

    apt = Appointment(
        patient_id=patient.id,
        appointment_type=AppointmentType.ROUTINE_CHECKUP,
        appointment_datetime=anchor - timedelta(days=days_ago),
    )
    db_session.add(apt)
    db_session.commit()
    return patient, apt


def test_generate_endpoint_success(client: TestClient, db_session: Session) -> None:
    """Verify POST /api/v1/reminders/generate generates draft reminders for eligible appointments."""
    ref_time = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    _, apt = seed_appointment(db_session, first_name="Tanya", days_ago=2, ref_time=ref_time)

    response = client.post(
        "/api/v1/reminders/generate",
        json={"reference_time": ref_time.isoformat()},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "completed"
    assert data["total_reviewed"] == 1
    assert data["reminders_created"] == 1
    assert data["reminders_skipped"] == 0
    assert data["failures"] == 0
    assert len(data["created_reminder_ids"]) == 1
    assert data["window_days"] == 7

    # Verify persisted database entity
    db_session.expire_all()
    reminder = db_session.get(FollowUpReminder, data["created_reminder_ids"][0])
    assert reminder is not None
    assert reminder.appointment_id == apt.id
    assert reminder.status == ReminderStatus.DRAFT
    assert "Tanya" in reminder.message_text


def test_generate_endpoint_empty_batch(client: TestClient) -> None:
    """Verify POST /api/v1/reminders/generate on empty database returns successful empty counts."""
    response = client.post("/api/v1/reminders/generate", json={})
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "completed"
    assert data["total_reviewed"] == 0
    assert data["reminders_created"] == 0
    assert data["reminders_skipped"] == 0
    assert data["failures"] == 0
    assert data["created_reminder_ids"] == []


def test_generate_endpoint_respects_seven_day_window(
    client: TestClient, db_session: Session
) -> None:
    """Verify that encounters older than the 7-day lookback are ignored."""
    ref_time = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    # Inside window (4 days ago)
    seed_appointment(db_session, first_name="Inside", days_ago=4, ref_time=ref_time)
    # Outside window (9 days ago)
    seed_appointment(db_session, first_name="Outside", days_ago=9, ref_time=ref_time)

    response = client.post(
        "/api/v1/reminders/generate",
        json={"reference_time": ref_time.isoformat(), "window_days": 7},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_reviewed"] == 1
    assert data["reminders_created"] == 1


def test_generate_endpoint_repeated_invocation_is_idempotent(
    client: TestClient, db_session: Session
) -> None:
    """Verify that repeated endpoint calls do not create duplicate reminders."""
    ref_time = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    seed_appointment(db_session, first_name="Repeated", days_ago=2, ref_time=ref_time)

    # First call: creates 1
    res1 = client.post(
        "/api/v1/reminders/generate",
        json={"reference_time": ref_time.isoformat()},
    )
    assert res1.status_code == 200
    assert res1.json()["reminders_created"] == 1
    assert res1.json()["reminders_skipped"] == 0

    # Second call: skips 1
    res2 = client.post(
        "/api/v1/reminders/generate",
        json={"reference_time": ref_time.isoformat()},
    )
    assert res2.status_code == 200
    assert res2.json()["reminders_created"] == 0
    assert res2.json()["reminders_skipped"] == 1


def test_generate_endpoint_validates_request_parameters(client: TestClient) -> None:
    """Verify invalid window_days boundaries return HTTP 422."""
    # Zero days
    res_zero = client.post("/api/v1/reminders/generate", json={"window_days": 0})
    assert res_zero.status_code == 422

    # Negative days
    res_neg = client.post("/api/v1/reminders/generate", json={"window_days": -3})
    assert res_neg.status_code == 422

    # Greater than max (90)
    res_too_large = client.post("/api/v1/reminders/generate", json={"window_days": 91})
    assert res_too_large.status_code == 422

    # Extra unexpected fields (extra="forbid")
    res_extra = client.post("/api/v1/reminders/generate", json={"unsupported_field": True})
    assert res_extra.status_code == 422


def test_generate_endpoint_database_isolation(
    client: TestClient, db_session: Session
) -> None:
    """Verify that calling the endpoint does not write to the local healthtrack.db file."""
    ref_time = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    seed_appointment(db_session, first_name="IsoClient", days_ago=1, ref_time=ref_time)

    client.post(
        "/api/v1/reminders/generate",
        json={"reference_time": ref_time.isoformat()},
    )

    # Ensure no local file was created on disk
    local_db = Path("healthtrack.db")
    assert not local_db.exists(), "Local database file must not be created by test endpoint calls"


def test_generate_endpoint_safe_error_handling(client: TestClient) -> None:
    """Verify unhandled database failures return HTTP 500 with safe, sanitized error message."""
    # Mock service that raises an unhandled database error
    class BrokenService:
        def __init__(self) -> None:
            self.window_days = 7

        def generate_reminders(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            from sqlalchemy.exc import OperationalError

            raise OperationalError("SELECT * FROM sensitive_table", {}, Exception("Disk full"))

    client.app.dependency_overrides[get_reminder_service] = lambda: BrokenService()  # type: ignore[attr-defined]

    response = client.post("/api/v1/reminders/generate", json={})
    assert response.status_code == 500

    error_data = response.json()
    assert "detail" in error_data
    assert "database error occurred" in error_data["detail"]
    # Ensure no internal query or stack trace details leaked
    assert "sensitive_table" not in error_data["detail"]
    assert "Disk full" not in error_data["detail"]
