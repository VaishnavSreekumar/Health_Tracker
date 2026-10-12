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


def test_empty_workspace_returns_zero_metrics(client: TestClient) -> None:
    """Verify clean workspace returns exact zero counts without manufactured activity."""
    metrics_res = client.get("/api/v1/overview/metrics")
    assert metrics_res.status_code == 200
    m = metrics_res.json()
    assert m["total_patients"] == 0
    assert m["total_appointments"] == 0
    assert m["eligible_appointments"] == 0
    assert m["drafts_pending_review"] == 0
    assert m["approved_reminders"] == 0
    assert m["dispatched_reminders"] == 0
    assert m["failed_deliveries"] == 0
    assert m["ai_generated_count"] == 0
    assert m["fallback_count"] == 0

    act_res = client.get("/api/v1/overview/activity")
    assert act_res.status_code == 200
    assert act_res.json() == []


def test_patient_registration_and_listing(client: TestClient) -> None:
    """Verify patient creation, retrieval, and validation."""
    # Invalid empty payload -> 422
    invalid_res = client.post("/api/v1/patients", json={})
    assert invalid_res.status_code == 422

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

    # Duplicate email -> 409
    dup_res = client.post(
        "/api/v1/patients",
        json={
            "first_name": "Clara",
            "last_name": "Duplicate",
            "email": "clara.barton@example.synthetic",
        },
    )
    assert dup_res.status_code == 409

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
    assert len(draft_data["validation_checks"]) == 7
    reminder_id = draft_data["id"]

    # 3. Edit draft text with valid modification
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

    # 4. Attempt invalid edits: Pydantic catches length < 15 (422), Guardrail catches clinical advice (400)
    short_edit = client.patch(f"/api/v1/reminders/{reminder_id}", json={"message_text": "Hi Ada"})
    assert short_edit.status_code == 422

    med_edit = client.patch(
        f"/api/v1/reminders/{reminder_id}",
        json={"message_text": "Hello Ada, please take 500mg amoxicillin twice daily."},
    )
    assert med_edit.status_code == 400
    assert "Guardrail validation failed" in med_edit.json()["detail"]

    # 5. Approve draft
    appr_res = client.post(f"/api/v1/reminders/{reminder_id}/approve")
    assert appr_res.status_code == 200
    assert appr_res.json()["status"] == "approved"
    assert appr_res.json()["approved_by"] == "Clinical Reviewer"

    # 6. Cannot approve a second time -> 400 Bad Request
    second_appr = client.post(f"/api/v1/reminders/{reminder_id}/approve")
    assert second_appr.status_code == 400

    # 7. Cannot reject an already approved reminder -> 400 Bad Request
    reject_after_appr = client.post(f"/api/v1/reminders/{reminder_id}/reject")
    assert reject_after_appr.status_code == 400

    # 8. Cannot regenerate reminder after approval -> 400 Bad Request
    regen_after_appr = client.post(f"/api/v1/reminders/appointments/{apt_id}/draft")
    assert regen_after_appr.status_code == 400

    # 9. Dispatch returns safe 503 unconfigured status
    disp_res = client.post(f"/api/v1/reminders/{reminder_id}/dispatch")
    assert disp_res.status_code == 503


def test_reject_workflow_and_edge_cases(client: TestClient) -> None:
    """Verify rejection flow, nonexistent record errors, and duplicate protections."""
    # 1. Nonexistent appointment drafting -> 404
    non_apt = client.post("/api/v1/reminders/appointments/99999/draft")
    assert non_apt.status_code == 404

    # 2. Nonexistent reminder approval/rejection -> 404
    non_appr = client.post("/api/v1/reminders/99999/approve")
    assert non_appr.status_code == 404
    non_rej = client.post("/api/v1/reminders/99999/reject")
    assert non_rej.status_code == 404

    # 3. Create patient and appointment to test rejection
    p_res = client.post(
        "/api/v1/patients",
        json={
            "first_name": "Grace",
            "last_name": "Hopper",
            "email": "grace.hopper@example.synthetic",
        },
    )
    p_id = p_res.json()["id"]

    apt_res = client.post(
        "/api/v1/appointments",
        json={
            "patient_id": p_id,
            "appointment_type": "specialist_consultation",
            "appointment_datetime": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
        },
    )
    apt_id = apt_res.json()["id"]

    draft_res = client.post(f"/api/v1/reminders/appointments/{apt_id}/draft")
    rem_id = draft_res.json()["id"]

    # Reject draft
    rej_res = client.post(f"/api/v1/reminders/{rem_id}/reject")
    assert rej_res.status_code == 200
    assert rej_res.json()["status"] == "rejected"

    # Repeated rejection -> 400 Bad Request
    second_rej = client.post(f"/api/v1/reminders/{rem_id}/reject")
    assert second_rej.status_code == 400

    # Cannot approve after rejection -> 400 Bad Request
    appr_after_rej = client.post(f"/api/v1/reminders/{rem_id}/approve")
    assert appr_after_rej.status_code == 400
