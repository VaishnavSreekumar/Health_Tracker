"""Reminder generation service orchestrating appointment selection and reminder persistence."""

from dataclasses import dataclass, field
from datetime import datetime
import logging
from typing import List, Optional
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.reminder import FollowUpReminder, ReminderStatus
from app.services.eligibility import get_eligible_appointments
from app.services.personalizer import MessagePersonalizer, TemplateMessagePersonalizer

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GenerationResult:
    """Summary of batch reminder generation processing."""

    total_reviewed: int
    reminders_created: int
    reminders_skipped: int
    failures: int
    created_reminder_ids: List[int] = field(default_factory=list)
    failed_appointment_ids: List[int] = field(default_factory=list)


class ReminderGenerationService:
    """Core business service for generating post-encounter follow-up reminders.

    Safeguards:
    - Review appointments within the eligible time boundary.
    - Prevent duplicate outreach using pre-flight checks and database unique constraints.
    - Recover cleanly from individual record failures using transactional savepoints.
    - Emit privacy-safe audit logs with internal IDs only (no patient names or emails).
    """

    def __init__(
        self,
        personalizer: Optional[MessagePersonalizer] = None,
        window_days: int = 7,
    ):
        self.personalizer: MessagePersonalizer = personalizer or TemplateMessagePersonalizer()
        self.window_days = window_days

    def generate_reminders(
        self,
        session: Session,
        reference_time: Optional[datetime] = None,
    ) -> GenerationResult:
        """Scan eligible encounters and persist draft reminders.

        Args:
            session: Active database session.
            reference_time: Deterministic reference anchor time (defaults to current UTC).

        Returns:
            GenerationResult containing aggregate counts and record IDs.
        """
        eligible_appointments = get_eligible_appointments(
            session=session,
            reference_time=reference_time,
            window_days=self.window_days,
        )

        total_reviewed = 0
        reminders_created = 0
        reminders_skipped = 0
        failures = 0
        created_reminder_ids: List[int] = []
        failed_appointment_ids: List[int] = []

        for appointment in eligible_appointments:
            total_reviewed += 1

            # Pre-flight check: skip if reminder already exists on the appointment model
            if appointment.reminder is not None:
                logger.debug(
                    "Skipping appointment_id=%d: reminder record already exists",
                    appointment.id,
                )
                reminders_skipped += 1
                continue

            # Integrity safeguard: skip and record failure if appointment lacks associated patient
            if not appointment.patient:
                logger.warning(
                    "Appointment id=%d has no associated patient; recording failure",
                    appointment.id,
                )
                failures += 1
                failed_appointment_ids.append(appointment.id)
                continue

            try:
                # Format non-clinical reminder message with provenance metadata if supported
                if hasattr(self.personalizer, "personalize_with_details"):
                    details = self.personalizer.personalize_with_details(appointment)
                    message_text = details["message_text"]
                    gen_source = details.get("generation_source", "template_fallback")
                    model_name = details.get("model_name")
                    fallback_reason = details.get("fallback_reason")
                else:
                    message_text = self.personalizer.personalize_reminder(appointment)
                    gen_source = "template_fallback"
                    model_name = None
                    fallback_reason = None

                # Use a nested transaction savepoint to isolate each record's persistence
                with session.begin_nested():
                    new_reminder = FollowUpReminder(
                        appointment_id=appointment.id,
                        message_text=message_text,
                        original_text=message_text,
                        status=ReminderStatus.DRAFT,
                        generation_source=gen_source,
                        model_name=model_name,
                        fallback_reason=fallback_reason,
                    )
                    session.add(new_reminder)
                    session.flush()

                reminders_created += 1
                created_reminder_ids.append(new_reminder.id)
                logger.info(
                    "Successfully drafted reminder_id=%d for appointment_id=%d",
                    new_reminder.id,
                    appointment.id,
                )

            except IntegrityError:
                # Handles race condition where duplicate reminder was inserted concurrently
                logger.warning(
                    "Database constraint violation on appointment_id=%d; skipping record",
                    appointment.id,
                )
                reminders_skipped += 1

            except Exception as exc:
                # Catch unexpected individual failure and preserve session usability
                logger.error(
                    "Failed processing appointment_id=%d with error=%s",
                    appointment.id,
                    type(exc).__name__,
                )
                failures += 1
                failed_appointment_ids.append(appointment.id)

        # Commit successfully drafted records in the active transaction
        try:
            session.commit()
        except SQLAlchemyError as commit_err:
            session.rollback()
            logger.error(
                "Database commit failed during reminder generation: %s",
                type(commit_err).__name__,
            )
            raise

        logger.info(
            "Reminder generation complete: reviewed=%d, created=%d, skipped=%d, failures=%d",
            total_reviewed,
            reminders_created,
            reminders_skipped,
            failures,
        )

        return GenerationResult(
            total_reviewed=total_reviewed,
            reminders_created=reminders_created,
            reminders_skipped=reminders_skipped,
            failures=failures,
            created_reminder_ids=created_reminder_ids,
            failed_appointment_ids=failed_appointment_ids,
        )
