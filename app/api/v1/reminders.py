"""Follow-up reminder generation, studio review, and lifecycle API routes."""

from datetime import datetime, timezone
import logging
from typing import List, Optional, Union
import uuid
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
from app.services.eligibility import get_eligible_appointments
from app.services.generator import ReminderGenerationService
from app.services.guardrails import GuardrailValidator
from app.services.llm_client import (
    ConfiguredLLMClient,
    GeminiLLMClient,
    LLMClient,
    LLMConfigurationError,
    OpenRouterLLMClient,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def get_personalizer() -> GuardrailedAIPersonalizer:
    """Dependency providing GuardrailedAIPersonalizer configured with provider selection and failover."""
    settings = get_settings()
    provider = settings.llm_provider.lower()

    primary_client: Optional[LLMClient] = None
    secondary_client: Optional[LLMClient] = None

    if provider == "openrouter":
        if settings.effective_openrouter_api_key:
            primary_client = OpenRouterLLMClient(settings=settings)
    elif provider == "gemini":
        if settings.effective_gemini_api_key:
            primary_client = GeminiLLMClient(settings=settings)
    elif provider == "openrouter_with_gemini_fallback":
        if settings.effective_openrouter_api_key:
            primary_client = OpenRouterLLMClient(settings=settings)
        if settings.effective_gemini_api_key:
            secondary_client = GeminiLLMClient(settings=settings)
        # If OpenRouter key is missing but Gemini is configured, promote Gemini
        if primary_client is None and secondary_client is not None:
            primary_client = secondary_client
            secondary_client = None

    return GuardrailedAIPersonalizer(
        llm_client=primary_client,
        secondary_client=secondary_client,
        settings=settings,
    )


def get_reminder_service() -> ReminderGenerationService:
    """Dependency providing configured ReminderGenerationService."""
    return ReminderGenerationService(personalizer=get_personalizer())


def _build_reminder_detail(reminder: FollowUpReminder) -> ReminderDetailResponse:
    """Construct full response object with guardrail breakdown."""
    validator = GuardrailValidator()
    patient = reminder.appointment.patient if reminder.appointment else None
    patient_name = f"{patient.first_name} {patient.last_name}" if patient else "Unknown"
    first_name = patient.first_name if patient else "there"
    appointment_dt = reminder.appointment.appointment_datetime if reminder.appointment else None

    # Evaluate validation checks
    checks_data = validator.get_validation_breakdown(
        reminder.message_text,
        expected_name=first_name,
        allowed_date=appointment_dt,
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


def _execute_generation_batch(
    session: Session,
    service: ReminderGenerationService,
    window_days: int = 7,
    reference_time: Optional[datetime] = None,
    as_list: bool = False,
) -> Union[ReminderGenerationResponse, List[ReminderDetailResponse]]:
    """Execute reminder generation batch with error containment and populate reminder records."""
    try:
        service.window_days = window_days
        result = service.generate_reminders(
            session=session,
            reference_time=reference_time,
        )

        # Retrieve detailed reminder records for all eligible encounters in the window
        # (both newly created and pre-existing drafts), ensuring callers always receive
        # the complete set of reminders governing the lookback interval.
        eligible_appointments = get_eligible_appointments(
            session=session,
            reference_time=reference_time,
            window_days=window_days,
        )
        reminder_records: List[ReminderDetailResponse] = []
        for apt in eligible_appointments:
            if apt.reminder:
                reminder_records.append(_build_reminder_detail(apt.reminder))

        if as_list:
            return reminder_records

        return ReminderGenerationResponse(
            status="completed",
            total_reviewed=result.total_reviewed,
            reminders_created=result.reminders_created,
            reminders_skipped=result.reminders_skipped,
            failures=result.failures,
            created_reminder_ids=result.created_reminder_ids,
            failed_appointment_ids=result.failed_appointment_ids,
            window_days=window_days,
            reminders=reminder_records,
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


@router.get(
    "/generate",
    response_model=Union[ReminderGenerationResponse, List[ReminderDetailResponse]],
    status_code=status.HTTP_200_OK,
    summary="Generate Follow-Up Reminders (GET Assessment Contract)",
    description=(
        "Trigger follow-up reminder creation for patients whose appointments occurred "
        "during the previous 7 days (or specified lookback window). Returns the list of "
        "generated reminders alongside batch execution metadata.\n\n"
        "Design Trade-off Note:\n"
        "In strict REST semantics (RFC 7231 / RFC 9110), GET methods should be safe, "
        "read-only operations without side effects. However, this endpoint directly "
        "implements the explicit assessment requirement where the 7-day workflow is "
        "evaluated via GET requests. It is protected by pre-flight duplicate checks and "
        "database unique constraints to ensure safe, idempotent re-execution."
    ),
)
def generate_reminders_get(
    window_days: int = Query(default=7, ge=1, le=90, description="Eligibility lookback window in days (default: 7)."),
    reference_time: Optional[datetime] = Query(default=None, description="Optional UTC anchor timestamp for testing and controlled replays."),
    as_list: bool = Query(default=False, description="If True, returns a raw JSON array of reminder records."),
    session: Session = Depends(get_db),
    service: ReminderGenerationService = Depends(get_reminder_service),
) -> Union[ReminderGenerationResponse, List[ReminderDetailResponse]]:
    """Execute 7-day reminder generation via GET to satisfy assessment evaluation contract."""
    return _execute_generation_batch(
        session=session,
        service=service,
        window_days=window_days,
        reference_time=reference_time,
        as_list=as_list,
    )


@router.post(
    "/generate",
    response_model=ReminderGenerationResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate Follow-Up Reminders Batch (RESTful POST)",
    description="Trigger draft follow-up reminder creation for appointments in the previous 7 days.",
)
def generate_reminders(
    payload: Optional[ReminderGenerationRequest] = None,
    session: Session = Depends(get_db),
    service: ReminderGenerationService = Depends(get_reminder_service),
) -> ReminderGenerationResponse:
    """Execute reminder generation for eligible encounters via POST."""
    request_data = payload or ReminderGenerationRequest()
    response = _execute_generation_batch(
        session=session,
        service=service,
        window_days=request_data.window_days,
        reference_time=request_data.reference_time,
        as_list=False,
    )
    return response  # type: ignore[return-value]


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
    cid = f"req-{uuid.uuid4().hex[:8]}"
    logger.info("[%s] Stage=draft_requested appointment_id=%d", cid, appointment_id)
    try:
        details = personalizer.personalize_with_details(appointment, correlation_id=cid)
    except LLMConfigurationError as cfg_err:
        logger.error("[%s] Stage=draft_config_error appointment_id=%d detail='%s'", cid, appointment_id, cfg_err)
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
        if reminder.status != ReminderStatus.DRAFT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot regenerate reminder that has already been '{reminder.status.value}'.",
            )
        # Regenerate existing draft reminder
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
    logger.info(
        "[%s] Stage=draft_persisted appointment_id=%d reminder_id=%d source=%s model=%s fallback_reason='%s'",
        cid,
        appointment.id,
        reminder.id,
        gen_source,
        model_name,
        fallback_reason or "none",
    )
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

    # Validate updated text against clinical and formatting guardrails
    candidate_text = payload.message_text.strip()
    patient_name = (
        reminder.appointment.patient.first_name
        if reminder.appointment and reminder.appointment.patient
        else None
    )
    appointment_dt = reminder.appointment.appointment_datetime if reminder.appointment else None
    validator = GuardrailValidator()
    val_result = validator.validate(
        candidate_text,
        expected_name=patient_name,
        allowed_date=appointment_dt,
    )
    if not val_result.is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Guardrail validation failed: {val_result.reason}",
        )

    # Save edited text
    if not reminder.original_text:
        reminder.original_text = reminder.message_text

    reminder.message_text = candidate_text
    session.commit()
    session.refresh(reminder)
    logger.info("Updated draft text for reminder_id=%d (appointment_id=%d)", reminder.id, reminder.appointment_id)
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

    # Clinical safety assertion: cannot approve a reminder failing guardrails
    patient_name = (
        reminder.appointment.patient.first_name
        if reminder.appointment and reminder.appointment.patient
        else None
    )
    appointment_dt = reminder.appointment.appointment_datetime if reminder.appointment else None
    validator = GuardrailValidator()
    val_result = validator.validate(
        reminder.message_text,
        expected_name=patient_name,
        allowed_date=appointment_dt,
    )
    if not val_result.is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve reminder failing safety guardrails: {val_result.reason}",
        )

    reminder.status = ReminderStatus.APPROVED
    reminder.approved_at = utc_now()
    reminder.approved_by = "Clinical Reviewer"
    session.commit()
    session.refresh(reminder)
    logger.info("Approved reminder_id=%d for appointment_id=%d by %s", reminder.id, reminder.appointment_id, reminder.approved_by)
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

    if reminder.status != ReminderStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only draft reminders can be rejected (current status: '{reminder.status.value}').",
        )

    reminder.status = ReminderStatus.REJECTED
    session.commit()
    session.refresh(reminder)
    logger.info("Rejected reminder_id=%d for appointment_id=%d", reminder.id, reminder.appointment_id)
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
    logger.warning("Attempted dispatch on reminder_id=%d rejected: external delivery unconfigured", reminder.id)
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="External message delivery provider is unconfigured. Safe local demonstration mode is active.",
    )
