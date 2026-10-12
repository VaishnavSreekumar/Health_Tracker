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
            "Hello {name}, thank you for visiting our clinic for your routine checkup. "
            "If you have any questions following your visit or wish to arrange your next routine appointment, "
            "please feel free to reach out to our office team."
        ),
        AppointmentType.FOLLOW_UP: (
            "Hello {name}, thank you for attending your follow-up appointment with our care team. "
            "If you require administrative assistance or have questions regarding your encounter, "
            "please contact our office."
        ),
        AppointmentType.SPECIALIST_CONSULTATION: (
            "Hello {name}, thank you for attending your specialist consultation with our practice. "
            "If you have any appointment-related questions or need help coordinating next steps with our clinic, "
            "please reach out to our team."
        ),
        AppointmentType.ANNUAL_PHYSICAL: (
            "Hello {name}, thank you for completing your annual physical examination with our practice. "
            "If you have questions about your visit or need assistance scheduling future care, "
            "our clinic team is here to assist you."
        ),
        AppointmentType.POST_PROCEDURE: (
            "Hello {name}, thank you for attending your post-procedure appointment with our clinic. "
            "We appreciate your visit and are here to support you. "
            "If you have any clinical questions or concerns, please contact our care team directly."
        ),
    }

    FALLBACK_TEMPLATE = (
        "Hello {name}, thank you for attending your recent appointment with our clinic. "
        "If you have any questions about your visit or need assistance with next steps, "
        "please reach out to our office."
    )

    def _extract_patient_greeting_name(self, appointment: Optional[Appointment]) -> str:
        """Safely extract and sanitize patient first name or return neutral fallback."""
        if appointment and appointment.patient and appointment.patient.first_name:
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

        # Lookup template by appointment type (supporting both Enum and string values)
        apt_type = appointment.appointment_type if appointment else None
        template = self.TEMPLATES.get(apt_type)  # type: ignore[arg-type]

        if template is None and hasattr(apt_type, "value"):
            template = self.TEMPLATES.get(apt_type.value)  # type: ignore[arg-type]

        if template is None and isinstance(apt_type, str):
            try:
                enum_val = AppointmentType(apt_type)
                template = self.TEMPLATES.get(enum_val)
            except ValueError:
                template = None

        if template is None:
            template = self.FALLBACK_TEMPLATE

        return template.format(name=name)
