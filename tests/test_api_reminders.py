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

    # Ensure local database file was not written to or created with test records
    local_db = Path("healthtrack.db")
    if local_db.exists():
        import sqlite3

        conn = sqlite3.connect(local_db)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='patients'")
        if cur.fetchone():
            cur.execute("SELECT COUNT(*) FROM patients WHERE first_name='IsoClient'")
            count = cur.fetchone()[0]
            assert count == 0, "Test patient must not be written to local database file"
        conn.close()
    else:
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


def test_generate_endpoint_get_success(client: TestClient, db_session: Session) -> None:
    """Verify GET /api/v1/reminders/generate triggers generation and returns reminders list (assessment contract)."""
    ref_time = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    patient, apt = seed_appointment(db_session, first_name="Aiden", days_ago=2, ref_time=ref_time)

    response = client.get(
        "/api/v1/reminders/generate",
        params={"reference_time": ref_time.isoformat(), "window_days": 7},
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

    # Verify returned reminder records in payload
    assert "reminders" in data
    assert len(data["reminders"]) == 1
    rem = data["reminders"][0]
    assert rem["id"] == data["created_reminder_ids"][0]
    assert rem["appointment_id"] == apt.id
    assert rem["patient_name"] == f"{patient.first_name} {patient.last_name}"
    assert rem["status"] == "draft"
    assert "Aiden" in rem["message_text"]


def test_generate_endpoint_get_as_list_format(client: TestClient, db_session: Session) -> None:
    """Verify GET /api/v1/reminders/generate with as_list=true returns raw JSON array of reminder records."""
    ref_time = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    _, apt = seed_appointment(db_session, first_name="DirectList", days_ago=3, ref_time=ref_time)

    response = client.get(
        "/api/v1/reminders/generate",
        params={"reference_time": ref_time.isoformat(), "as_list": "true"},
    )
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["appointment_id"] == apt.id
    assert data[0]["status"] == "draft"
    assert "DirectList" in data[0]["message_text"]


def test_generate_endpoint_get_repeated_invocation_is_idempotent(
    client: TestClient, db_session: Session
) -> None:
    """Verify that repeated GET requests do not create duplicate reminders and return existing drafts."""
    ref_time = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    seed_appointment(db_session, first_name="IdempotentGet", days_ago=1, ref_time=ref_time)

    # Initial GET invocation
    res1 = client.get(
        "/api/v1/reminders/generate",
        params={"reference_time": ref_time.isoformat()},
    )
    assert res1.status_code == 200
    assert res1.json()["reminders_created"] == 1
    assert res1.json()["reminders_skipped"] == 0
    assert len(res1.json()["reminders"]) == 1

    # Second GET invocation
    res2 = client.get(
        "/api/v1/reminders/generate",
        params={"reference_time": ref_time.isoformat()},
    )
    assert res2.status_code == 200
    assert res2.json()["reminders_created"] == 0
    assert res2.json()["reminders_skipped"] == 1
    # Reminders list still provides the existing draft for the encounter
    assert len(res2.json()["reminders"]) == 1
    assert res2.json()["reminders"][0]["id"] == res1.json()["reminders"][0]["id"]


def test_generate_endpoint_get_respects_seven_day_window(
    client: TestClient, db_session: Session
) -> None:
    """Verify GET /api/v1/reminders/generate filters strictly for encounters in the 7-day lookback window."""
    ref_time = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
    # Inside window (2 days ago)
    seed_appointment(db_session, first_name="InsideWin", days_ago=2, ref_time=ref_time)
    # Outside window (8 days ago)
    seed_appointment(db_session, first_name="OutsideWin", days_ago=8, ref_time=ref_time)

    response = client.get(
        "/api/v1/reminders/generate",
        params={"reference_time": ref_time.isoformat(), "window_days": 7},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_reviewed"] == 1
    assert data["reminders_created"] == 1
    assert len(data["reminders"]) == 1
    assert "InsideWin" in data["reminders"][0]["message_text"]


def test_generate_endpoint_get_empty_batch(client: TestClient) -> None:
    """Verify GET /api/v1/reminders/generate on empty database returns successful empty response."""
    response = client.get("/api/v1/reminders/generate")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["total_reviewed"] == 0
    assert data["reminders_created"] == 0
    assert data["reminders"] == []


def test_generate_endpoint_get_parameter_validation(client: TestClient) -> None:
    """Verify GET /api/v1/reminders/generate validates query parameter constraints."""
    # window_days < 1 -> 422
    res_zero = client.get("/api/v1/reminders/generate", params={"window_days": 0})
    assert res_zero.status_code == 422

    # window_days > 90 -> 422
    res_large = client.get("/api/v1/reminders/generate", params={"window_days": 95})
    assert res_large.status_code == 422


def test_legacy_lowercase_status_loaded_and_approval_rejected_for_incomplete_content(
    client: TestClient, db_session: Session
) -> None:
    """Regression: Verify reminders with legacy lowercase 'draft' status load cleanly without LookupError,
    and invalid content without terminal punctuation is rejected with HTTP 400 upon approval.
    """
    patient, apt = seed_appointment(db_session, first_name="Evelyn", days_ago=2)

    # Insert reminder directly with raw lowercase 'draft' status and abruptly ending text
    incomplete_text = "Dear Evelyn, thank you for attending your recent annual physical with and visiting our clinic"
    reminder = FollowUpReminder(
        appointment_id=apt.id,
        message_text=incomplete_text,
        original_text=incomplete_text,
        status=ReminderStatus.DRAFT,
    )
    db_session.add(reminder)
    db_session.commit()

    # Raw SQL injection of lowercase 'draft' to simulate legacy / manual un-normalized database state
    db_session.connection().exec_driver_sql(
        f"UPDATE follow_up_reminders SET status = 'draft' WHERE id = {reminder.id}"
    )
    db_session.commit()
    db_session.expire_all()

    # Approve attempt must NOT crash with 500 LookupError; it must evaluate guardrails and return 400
    res = client.post(f"/api/v1/reminders/{reminder.id}/approve")
    assert res.status_code == 400
    assert "terminal punctuation" in res.json()["detail"].lower()

    # Entity remains in draft state
    db_session.expire_all()
    reloaded = db_session.get(FollowUpReminder, reminder.id)
    assert reloaded is not None
    assert reloaded.status == ReminderStatus.DRAFT


def test_valid_draft_approval_and_canonical_status_persistence(
    client: TestClient, db_session: Session
) -> None:
    """Verify valid draft reminders approve cleanly (HTTP 200) and persist canonical uppercase status."""
    patient, apt = seed_appointment(db_session, first_name="Seraphina", days_ago=2)

    valid_text = "Hello Seraphina, thank you for visiting HealthTrack Clinic for your routine checkup. Please let us know if you need any follow-up care."
    reminder = FollowUpReminder(
        appointment_id=apt.id,
        message_text=valid_text,
        original_text=valid_text,
        status=ReminderStatus.DRAFT,
    )
    db_session.add(reminder)
    db_session.commit()

    # Approve valid draft
    res = client.post(f"/api/v1/reminders/{reminder.id}/approve")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "approved"
    assert data["approved_by"] == "Clinical Reviewer"

    # Verify canonical uppercase representation is written to SQLite storage
    raw_status = db_session.connection().exec_driver_sql(
        f"SELECT status FROM follow_up_reminders WHERE id = {reminder.id}"
    ).fetchone()[0]
    assert raw_status == "APPROVED"
