"""Message personalization interface and deterministic template implementation."""

from typing import Optional, Protocol, runtime_checkable

from app.models.appointment import Appointment, AppointmentType


@runtime_checkable
class MessagePersonalizer(Protocol):
    """Protocol defining the interface for message personalization engines."""

    def personalize_reminder(self, appointment: Appointment) -> str:
        """Generate a personalized follow-up message for the given appointment.

        Args:
            appointment: The Appointment record containing patient and clinical metadata.

        Returns:
            Formatted, non-clinical reminder message string.
        """
        ...


class TemplateMessagePersonalizer:
    """Deterministic, template-driven message personalizer for Phase 2.

    Clinical & Privacy Guardrails:
    - Never generates diagnoses, medical prescriptions, or clinical instructions.
    - Never claims a message has already been delivered.
    - Never includes patient emails, IDs, or database internal metadata.
    - Uses polite, concise language tailored to the encounter type.
    - Employs a safe fallback for missing names or unhandled encounter types.
    """

    TEMPLATES = {
        AppointmentType.ROUTINE_CHECKUP: (
            "Hello {name}, thank you for attending your routine checkup. "
            "We hope your visit went smoothly. "
            "Please contact our office if you have any questions or need to schedule your next visit."
        ),
        AppointmentType.FOLLOW_UP: (
            "Hello {name}, thank you for attending your follow-up appointment. "
            "Please reach out to our care team if you have any questions or need further assistance."
        ),
        AppointmentType.SPECIALIST_CONSULTATION: (
            "Hello {name}, thank you for attending your specialist consultation. "
            "Please contact our office if you have any questions or need help coordinating next steps."
        ),
        AppointmentType.ANNUAL_PHYSICAL: (
            "Hello {name}, thank you for completing your annual physical examination. "
            "Our care team is here to support your long-term health and wellness. "
            "Please contact us if you need anything."
        ),
        AppointmentType.POST_PROCEDURE: (
            "Hello {name}, thank you for attending your post-procedure appointment. "
            "Please contact our clinic if you have any questions or need assistance during your recovery."
        ),
    }

    FALLBACK_TEMPLATE = (
        "Hello {name}, thank you for attending your recent appointment with our clinic. "
        "Please contact our office if you have any questions or need further assistance."
    )

    def _extract_patient_greeting_name(self, appointment: Appointment) -> str:
        """Safely extract and sanitize patient first name or return neutral fallback."""
        if appointment.patient and appointment.patient.first_name:
            first_line = (
                appointment.patient.first_name.strip().splitlines()[0]
                if appointment.patient.first_name.strip().splitlines()
                else ""
            )
            token = first_line.split()[0] if first_line.split() else ""
            if token:
                return token
        return "there"

    def personalize_reminder(self, appointment: Appointment) -> str:
        """Produce a deterministic follow-up reminder message."""
        name = self._extract_patient_greeting_name(appointment)

        # Lookup template by appointment type
        template = self.TEMPLATES.get(
            appointment.appointment_type,  # type: ignore[arg-type]
            self.FALLBACK_TEMPLATE,
        )

        return template.format(name=name)
