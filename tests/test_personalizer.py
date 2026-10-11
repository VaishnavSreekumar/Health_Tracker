"""Unit tests for message personalizer service and deterministic templates."""

from datetime import datetime, timezone
import pytest

from app.models.appointment import Appointment, AppointmentType
from app.models.patient import Patient
from app.services.personalizer import TemplateMessagePersonalizer


@pytest.fixture
def personalizer() -> TemplateMessagePersonalizer:
    return TemplateMessagePersonalizer()


def create_synthetic_appointment(
    first_name: str = "Alice",
    appointment_type: AppointmentType = AppointmentType.ROUTINE_CHECKUP,
) -> Appointment:
    patient = Patient(
        id=101,
        first_name=first_name,
        last_name="Tester",
        email="alice.tester@example.com",
    )
    appointment = Appointment(
        id=202,
        patient_id=patient.id,
        appointment_type=appointment_type,
        appointment_datetime=datetime(2026, 10, 10, 10, 0, tzinfo=timezone.utc),
    )
    appointment.patient = patient
    return appointment


def test_personalization_all_supported_appointment_types(
    personalizer: TemplateMessagePersonalizer,
) -> None:
    """Verify that each supported AppointmentType produces a polite, type-specific message."""
    expected_type_keywords = {
        AppointmentType.ROUTINE_CHECKUP: "routine checkup",
        AppointmentType.FOLLOW_UP: "follow-up appointment",
        AppointmentType.SPECIALIST_CONSULTATION: "specialist consultation",
        AppointmentType.ANNUAL_PHYSICAL: "annual physical examination",
        AppointmentType.POST_PROCEDURE: "post-procedure appointment",
    }

    for apt_type, keyword in expected_type_keywords.items():
        apt = create_synthetic_appointment(first_name="Jordan", appointment_type=apt_type)
        msg = personalizer.personalize_reminder(apt)

        assert "Jordan" in msg
        assert keyword in msg
        assert "Hello Jordan" in msg


def test_patient_first_name_inclusion(personalizer: TemplateMessagePersonalizer) -> None:
    """Verify patient first name is sanitized and included in the greeting."""
    apt = create_synthetic_appointment(first_name="Maya  ")
    msg = personalizer.personalize_reminder(apt)
    assert "Hello Maya," in msg


def test_fallback_when_patient_name_is_missing(
    personalizer: TemplateMessagePersonalizer,
) -> None:
    """Verify neutral fallback greeting when patient first_name is empty or patient is None."""
    # Empty string name
    apt_empty_name = create_synthetic_appointment(first_name="")
    msg_empty = personalizer.personalize_reminder(apt_empty_name)
    assert "Hello there," in msg_empty

    # Whitespace only name
    apt_ws_name = create_synthetic_appointment(first_name="   ")
    msg_ws = personalizer.personalize_reminder(apt_ws_name)
    assert "Hello there," in msg_ws

    # Appointment with no patient attached
    orphan_apt = Appointment(
        id=303,
        patient_id=999,
        appointment_type=AppointmentType.ROUTINE_CHECKUP,
        appointment_datetime=datetime(2026, 10, 10, 10, 0, tzinfo=timezone.utc),
    )
    msg_orphan = personalizer.personalize_reminder(orphan_apt)
    assert "Hello there," in msg_orphan


def test_fallback_for_unknown_appointment_type(
    personalizer: TemplateMessagePersonalizer,
) -> None:
    """Verify neutral fallback message for unrecognized appointment types."""
    apt = create_synthetic_appointment(first_name="Sam")
    # Simulate an unsupported appointment type value
    apt.appointment_type = "unsupported_type"  # type: ignore[assignment]
    msg = personalizer.personalize_reminder(apt)

    assert "Hello Sam" in msg
    assert "recent appointment with our clinic" in msg


def test_message_content_privacy_and_clinical_guardrails(
    personalizer: TemplateMessagePersonalizer,
) -> None:
    """Verify message does not contain PII (email, DB IDs) or unsupported clinical claims."""
    apt = create_synthetic_appointment(first_name="Taylor")
    msg = personalizer.personalize_reminder(apt)

    # Privacy check
    assert "alice.tester@example.com" not in msg
    assert "101" not in msg
    assert "202" not in msg

    # Non-clinical check (no prescription or diagnosis language)
    lower_msg = msg.lower()
    assert "diagnosis" not in lower_msg
    assert "medication" not in lower_msg
    assert "prescribe" not in lower_msg
    assert "sent" not in lower_msg
    assert "delivered" not in lower_msg
