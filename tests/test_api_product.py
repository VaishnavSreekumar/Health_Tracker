"""Tests for extended product endpoints (patients, appointments, studio review, overview, system)."""

from datetime import datetime, timedelta, timezone
from starlette.testclient import TestClient

from app.models.appointment import Appointment, AppointmentType
from app.models.patient import Patient


def test_system_settings_endpoint(client: TestClient) -> None:
    """Verify GET /api/v1/system/settings returns safe integration status."""
    res = client.get("/api/v1/system/settings")
    assert res.status_code == 200
    data = res.json()
    assert data["project_name"] == "HealthTrack Follow-Up System"
    assert "llm_provider" in data
    assert "delivery_status" in data
    assert data["delivery_enabled"] is False


def test_seed_and_overview_metrics(client: TestClient) -> None:
    """Verify demo seed populates records and overview returns non-zero metrics."""
    seed_res = client.post("/api/v1/system/seed-demo")
    assert seed_res.status_code == 200
    assert seed_res.json()["status"] == "success"

    # Overview metrics
    metrics_res = client.get("/api/v1/overview/metrics")
    assert metrics_res.status_code == 200
    m = metrics_res.json()
    assert m["total_patients"] >= 6
    assert m["total_appointments"] >= 6
    assert m["drafts_pending_review"] >= 2
    assert m["approved_reminders"] >= 1

    # Activity list
    act_res = client.get("/api/v1/overview/activity")
    assert act_res.status_code == 200
    assert len(act_res.json()) > 0


def test_patient_registration_and_listing(client: TestClient) -> None:
    """Verify patient creation and retrieval."""
    res = client.post(
        "/api/v1/patients",
        json={
            "first_name": "Clara",
            "last_name": "Barton",
            "email": "clara.barton@example.synthetic",
        },
    )
    assert res.status_code == 201
    patient_id = res.json()["id"]

    # List patients
    list_res = client.get("/api/v1/patients")
    assert list_res.status_code == 200
    assert any(p["id"] == patient_id for p in list_res.json())


def test_studio_workflow_generate_edit_approve(client: TestClient) -> None:
    """Verify 3-step Follow-up Studio workflow: generate draft, edit text, approve."""
    # 1. Create patient and appointment in 7-day window
    p_res = client.post(
        "/api/v1/patients",
        json={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada.lovelace@example.synthetic",
        },
    )
    p_id = p_res.json()["id"]

    two_days_ago = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    apt_res = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": p_id,
            "appointment_type": "routine_checkup",
            "appointment_datetime": two_days_ago,
        },
    )
    apt_id = apt_res.json()["id"]

    # 2. Generate draft for this specific appointment
    draft_res = client.post(f"/api/v1/reminders/appointments/{apt_id}/draft")
    assert draft_res.status_code == 200
    draft_data = draft_res.json()
    assert draft_data["status"] == "draft"
    assert "Ada" in draft_data["message_text"]
    assert draft_data["is_edited"] is False
    assert len(draft_data["validation_checks"]) == 5
    reminder_id = draft_data["id"]

    # 3. Edit draft text
    edit_res = client.patch(
        f"/api/v1/reminders/{reminder_id}",
        json={
            "message_text": "Hello Ada, thank you for attending your routine checkup with Dr. Smith today.",
        },
    )
    assert edit_res.status_code == 200
    edit_data = edit_res.json()
    assert edit_data["is_edited"] is True
    assert "Dr. Smith" in edit_data["message_text"]

    # 4. Approve draft
    appr_res = client.post(f"/api/v1/reminders/{reminder_id}/approve")
    assert appr_res.status_code == 200
    assert appr_res.json()["status"] == "approved"
    assert appr_res.json()["approved_by"] == "Clinical Reviewer"

    # 5. Dispatch returns safe 503 unconfigured status
    disp_res = client.post(f"/api/v1/reminders/{reminder_id}/dispatch")
    assert disp_res.status_code == 503
