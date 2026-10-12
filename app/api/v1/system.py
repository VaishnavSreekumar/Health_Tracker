"""System settings and controlled synthetic demonstration seed API routes."""

from datetime import datetime, timedelta, timezone
import logging
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import utc_now
from app.db.session import get_db
from app.models.appointment import Appointment, AppointmentType
from app.models.patient import Patient
from app.models.reminder import FollowUpReminder, ReminderStatus
from app.schemas.system import SystemSettingsResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/settings", response_model=SystemSettingsResponse, summary="Get Integration Readiness")
def get_system_settings() -> SystemSettingsResponse:
    """Return operational integration status without exposing credentials."""
    settings = get_settings()

    if settings.is_openrouter_enabled:
        llm_model = settings.effective_openrouter_model
        is_llm_configured = bool(settings.effective_openrouter_api_key)
    elif settings.is_gemini_enabled:
        llm_model = settings.effective_gemini_model
        is_llm_configured = bool(settings.effective_gemini_api_key)
    else:
        llm_model = "None"
        is_llm_configured = False

    llm_status = (
        "configured"
        if is_llm_configured
        else ("offline_fallback" if settings.llm_provider.lower() == "none" else "unverified")
    )

    return SystemSettingsResponse(
        project_name=settings.project_name,
        version=settings.version,
        environment=settings.environment,
        database_type="SQLite (PRAGMA foreign_keys=ON, UTC timestamps)",
        llm_provider=settings.llm_provider,
        llm_model=llm_model,
        llm_configured=is_llm_configured,
        llm_status=llm_status,
        delivery_provider="None",
        delivery_enabled=False,
        delivery_status="disabled_safe_mode",
    )


@router.post("/reset", status_code=status.HTTP_200_OK, summary="Reset Workspace Records")
def reset_workspace(session: Session = Depends(get_db)) -> dict:
    """Clear local operational records to return to a clean, empty workspace state."""
    session.query(FollowUpReminder).delete()
    session.query(Appointment).delete()
    session.query(Patient).delete()
    session.commit()
    logger.info("Workspace database reset to empty state.")
    return {"status": "success", "message": "All workspace records cleared."}
