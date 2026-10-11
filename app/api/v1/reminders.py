"""Follow-up reminder generation, studio review, and lifecycle API routes."""

from datetime import datetime, timezone
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.db.base import utc_now
from app.db.session import get_db
from app.models.appointment import Appointment
from app.models.patient import Patient
from app.models.reminder import FollowUpReminder, ReminderStatus
from app.schemas.reminder import (
    ErrorResponse,
    ReminderDetailResponse,
    ReminderGenerationRequest,
    ReminderGenerationResponse,
    ReminderUpdateRequest,
    ValidationCheckDetail,
)
from app.services.ai_personalizer import GuardrailedAIPersonalizer
from app.services.generator import ReminderGenerationService
from app.services.guardrails import GuardrailValidator
from app.services.llm_client import ConfiguredLLMClient, LLMConfigurationError

logger = logging.getLogger(__name__)

router = APIRouter()


def get_personalizer() -> GuardrailedAIPersonalizer:
    """Dependency providing GuardrailedAIPersonalizer."""
    settings = get_settings()
    llm_client = (
        ConfiguredLLMClient(settings)
        if settings.is_gemini_enabled or settings.llm_provider.lower() == "gemini"
        else None
    )
    return GuardrailedAIPersonalizer(llm_client=llm_client)


def get_reminder_service() -> ReminderGenerationService:
    """Dependency providing configured ReminderGenerationService."""
    return ReminderGenerationService(personalizer=get_personalizer())


def _build_reminder_detail(reminder: FollowUpReminder) -> ReminderDetailResponse:
    """Construct full response object with guardrail breakdown."""
    validator = GuardrailValidator()
    patient = reminder.appointment.patient if reminder.appointment else None
    patient_name = f"{patient.first_name} {patient.last_name}" if patient else "Unknown"
    first_name = patient.first_name if patient else "there"

    # Evaluate validation checks
    checks_data = validator.get_validation_breakdown(
        reminder.message_text,
        expected_name=first_name,
    )
    validation_checks = [
        ValidationCheckDetail(
            id=c["id"],
            label=c["label"],
            passed=c["passed"],
            detail=c["detail"],
        )
        for c in checks_data
    ]

    is_edited = (
        reminder.original_text is not None
        and reminder.message_text.strip() != reminder.original_text.strip()
    )

    return ReminderDetailResponse(
        id=reminder.id,
        appointment_id=reminder.appointment_id,
        patient_id=patient.id if patient else 0,
        patient_name=patient_name,
        patient_email=patient.email if patient else "",
        appointment_type=reminder.appointment.appointment_type.value if reminder.appointment else "",
        appointment_datetime=reminder.appointment.appointment_datetime if reminder.appointment else utc_now(),
        message_text=reminder.message_text,
        original_text=reminder.original_text or reminder.message_text,
        is_edited=is_edited,
        status=reminder.status.value,
        generation_source=reminder.generation_source or "template_fallback",
        model_name=reminder.model_name,
        fallback_reason=reminder.fallback_reason,
        validation_checks=validation_checks,
        created_at=reminder.created_at,
        approved_at=reminder.approved_at,
        approved_by=reminder.approved_by,
        delivery_provider=reminder.delivery_provider,
        delivery_reference_id=reminder.delivery_reference_id,
        delivery_error=reminder.delivery_error,
    )


@router.post(
    "/generate",
    response_model=ReminderGenerationResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate Follow-Up Reminders Batch",
    description="Trigger draft follow-up reminder creation for appointments in the previous 7 days.",
)
def generate_reminders(
    payload: Optional[ReminderGenerationRequest] = None,
    session: Session = Depends(get_db),
    service: ReminderGenerationService = Depends(get_reminder_service),
) -> ReminderGenerationResponse:
    """Execute reminder generation for eligible encounters."""
    request_data = payload or ReminderGenerationRequest()

    try:
        service.window_days = request_data.window_days
        result = service.generate_reminders(
            session=session,
            reference_time=request_data.reference_time,
        )
        return ReminderGenerationResponse(
            status="completed",
            total_reviewed=result.total_reviewed,
            reminders_created=result.reminders_created,
            reminders_skipped=result.reminders_skipped,
            failures=result.failures,
            created_reminder_ids=result.created_reminder_ids,
            failed_appointment_ids=result.failed_appointment_ids,
            window_days=request_data.window_days,
        )
    except SQLAlchemyError as sql_err:
        logger.error("Database error during reminder generation batch: %s", type(sql_err).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="A database error occurred during reminder generation.",
        )
    except Exception as exc:
        logger.error("Unexpected error during reminder generation: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during reminder generation.",
        )


@router.get("", response_model=List[ReminderDetailResponse], summary="List Reminders")
def list_reminders(
    status_filter: Optional[str] = Query(default=None, alias="status", description="Filter by status (e.g. draft, approved)"),
    session: Session = Depends(get_db),
) -> List[ReminderDetailResponse]:
    """Retrieve all reminders with encounter and patient context."""
    query = (
        session.query(FollowUpReminder)
        .options(
            joinedload(FollowUpReminder.appointment).joinedload(Appointment.patient),
        )
        .order_by(FollowUpReminder.created_at.desc())
    )
    if status_filter:
        query = query.filter(FollowUpReminder.status == status_filter)

    reminders = query.all()
    return [_build_reminder_detail(r) for r in reminders]


@router.get("/{reminder_id}", response_model=ReminderDetailResponse, summary="Get Reminder Detail")
def get_reminder(reminder_id: int, session: Session = Depends(get_db)) -> ReminderDetailResponse:
    """Retrieve detailed reminder record including itemized guardrail validation."""
    reminder = (
        session.query(FollowUpReminder)
        .options(
            joinedload(FollowUpReminder.appointment).joinedload(Appointment.patient),
        )
        .filter(FollowUpReminder.id == reminder_id)
        .first()
    )
    if not reminder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found.")

    return _build_reminder_detail(reminder)


@router.post("/appointments/{appointment_id}/draft", response_model=ReminderDetailResponse, summary="Generate Draft for Appointment")
def draft_for_appointment(
    appointment_id: int,
    session: Session = Depends(get_db),
    personalizer: GuardrailedAIPersonalizer = Depends(get_personalizer),
) -> ReminderDetailResponse:
    """Generate or regenerate draft reminder specifically for one clinical encounter."""
    appointment = (
        session.query(Appointment)
        .options(
            joinedload(Appointment.patient),
            joinedload(Appointment.reminder),
        )
        .filter(Appointment.id == appointment_id)
        .first()
    )
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found.")

    # Execute personalization with details
    try:
        details = personalizer.personalize_with_details(appointment)
    except LLMConfigurationError as cfg_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"LLM Configuration Error: {cfg_err}",
        )
    msg_text = details["message_text"]
    gen_source = details["generation_source"]
    model_name = details["model_name"]
    fallback_reason = details["fallback_reason"]

    reminder = appointment.reminder
    if reminder:
        # Regenerate existing reminder
        reminder.message_text = msg_text
        reminder.original_text = msg_text
        reminder.status = ReminderStatus.DRAFT
        reminder.generation_source = gen_source
        reminder.model_name = model_name
        reminder.fallback_reason = fallback_reason
    else:
        # Create new reminder
        reminder = FollowUpReminder(
            appointment_id=appointment.id,
            message_text=msg_text,
            original_text=msg_text,
            status=ReminderStatus.DRAFT,
            generation_source=gen_source,
            model_name=model_name,
            fallback_reason=fallback_reason,
        )
        session.add(reminder)

    session.commit()
    session.refresh(reminder)
    return _build_reminder_detail(reminder)


@router.patch("/{reminder_id}", response_model=ReminderDetailResponse, summary="Update Draft Text")
def update_reminder_text(
    reminder_id: int,
    payload: ReminderUpdateRequest,
    session: Session = Depends(get_db),
) -> ReminderDetailResponse:
    """Update message text of a draft reminder while preserving original for diff."""
    reminder = (
        session.query(FollowUpReminder)
        .options(
            joinedload(FollowUpReminder.appointment).joinedload(Appointment.patient),
        )
        .filter(FollowUpReminder.id == reminder_id)
        .first()
    )
    if not reminder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found.")

    if reminder.status != ReminderStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot edit reminder in '{reminder.status.value}' state. Only draft reminders are editable.",
        )

    # Save edited text
    if not reminder.original_text:
        reminder.original_text = reminder.message_text

    reminder.message_text = payload.message_text.strip()
    session.commit()
    session.refresh(reminder)
    return _build_reminder_detail(reminder)


@router.post("/{reminder_id}/approve", response_model=ReminderDetailResponse, summary="Approve Reminder")
def approve_reminder(reminder_id: int, session: Session = Depends(get_db)) -> ReminderDetailResponse:
    """Authorize a draft reminder, moving it to approved state."""
    reminder = (
        session.query(FollowUpReminder)
        .options(
            joinedload(FollowUpReminder.appointment).joinedload(Appointment.patient),
        )
        .filter(FollowUpReminder.id == reminder_id)
        .first()
    )
    if not reminder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found.")

    if reminder.status != ReminderStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only draft reminders can be approved (current status: '{reminder.status.value}').",
        )

    reminder.status = ReminderStatus.APPROVED
    reminder.approved_at = utc_now()
    reminder.approved_by = "Clinical Reviewer"
    session.commit()
    session.refresh(reminder)
    return _build_reminder_detail(reminder)


@router.post("/{reminder_id}/reject", response_model=ReminderDetailResponse, summary="Reject Reminder")
def reject_reminder(reminder_id: int, session: Session = Depends(get_db)) -> ReminderDetailResponse:
    """Reject a draft reminder, marking it as rejected."""
    reminder = (
        session.query(FollowUpReminder)
        .options(
            joinedload(FollowUpReminder.appointment).joinedload(Appointment.patient),
        )
        .filter(FollowUpReminder.id == reminder_id)
        .first()
    )
    if not reminder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found.")

    reminder.status = ReminderStatus.REJECTED
    session.commit()
    session.refresh(reminder)
    return _build_reminder_detail(reminder)


@router.post("/{reminder_id}/dispatch", response_model=ReminderDetailResponse, summary="Dispatch Reminder")
def dispatch_reminder(reminder_id: int, session: Session = Depends(get_db)) -> ReminderDetailResponse:
    """Attempt message dispatch to delivery service."""
    reminder = (
        session.query(FollowUpReminder)
        .options(
            joinedload(FollowUpReminder.appointment).joinedload(Appointment.patient),
        )
        .filter(FollowUpReminder.id == reminder_id)
        .first()
    )
    if not reminder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found.")

    if reminder.status != ReminderStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Reminder must be in 'approved' status before dispatch (current: '{reminder.status.value}').",
        )

    # Truthful status: No live external delivery provider credentials configured by default
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="External message delivery provider is unconfigured. Safe local demonstration mode is active.",
    )
