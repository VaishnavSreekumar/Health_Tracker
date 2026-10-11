"""Unit and integration tests for Google Gemini LLMClient adapter."""

from datetime import datetime, timezone
import os
from unittest.mock import MagicMock, patch
import pytest

from app.core.config import Settings
from app.models.appointment import Appointment, AppointmentType
from app.models.patient import Patient
from app.services.ai_personalizer import GuardrailedAIPersonalizer
from app.services.guardrails import GuardrailValidator
from app.services.llm_client import (
    ConfiguredLLMClient,
    GeminiLLMClient,
    LLMAuthError,
    LLMConfigurationError,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
)


def create_synthetic_appointment(first_name: str = "Arthur") -> Appointment:
    """Helper creating synthetic in-memory encounter."""
    patient = Patient(id=101, first_name=first_name, last_name="Dent", email="arthur.dent@example.synthetic")
    appointment = Appointment(
        id=202,
        patient_id=patient.id,
        appointment_type=AppointmentType.ROUTINE_CHECKUP,
        appointment_datetime=datetime(2026, 10, 10, 10, 0, tzinfo=timezone.utc),
    )
    appointment.patient = patient
    return appointment


def test_gemini_missing_api_key_raises_configuration_error() -> None:
    """Verify GeminiLLMClient raises LLMConfigurationError if no key is configured."""
    test_settings = Settings(gemini_api_key=None, llm_api_key=None)
    with pytest.raises(LLMConfigurationError) as exc_info:
        GeminiLLMClient(api_key=None, settings=test_settings)

    assert "Gemini API key is not configured" in str(exc_info.value)


@patch("google.genai.Client")
def test_gemini_successful_generation_parsed(mock_genai_client_class: MagicMock) -> None:
    """Verify successful response from Gemini SDK is extracted and stripped."""
    mock_response = MagicMock()
    mock_response.text = "  Hello Arthur, thank you for attending your routine checkup. Please reach out if you have questions.  "

    mock_client_instance = MagicMock()
    mock_client_instance.models.generate_content.return_value = mock_response
    mock_genai_client_class.return_value = mock_client_instance

    client = GeminiLLMClient(api_key="synthetic-test-key", model="gemini-2.5-flash")
    result = client.generate("synthetic prompt")

    assert result == "Hello Arthur, thank you for attending your routine checkup. Please reach out if you have questions."
    mock_client_instance.models.generate_content.assert_called_once()


@patch("google.genai.Client")
def test_gemini_empty_response_raises_response_error(mock_genai_client_class: MagicMock) -> None:
    """Verify empty response text from Gemini SDK raises LLMResponseError."""
    mock_response = MagicMock()
    mock_response.text = ""

    mock_client_instance = MagicMock()
    mock_client_instance.models.generate_content.return_value = mock_response
    mock_genai_client_class.return_value = mock_client_instance

    client = GeminiLLMClient(api_key="synthetic-test-key")
    with pytest.raises(LLMResponseError) as exc_info:
        client.generate("prompt")

    assert "empty response" in str(exc_info.value)


@patch("google.genai.Client")
def test_gemini_auth_error_handling(mock_genai_client_class: MagicMock) -> None:
    """Verify invalid API key errors are mapped to LLMAuthError."""
    from google.genai import errors

    mock_client_instance = MagicMock()
    mock_client_instance.models.generate_content.side_effect = errors.ClientError(
        400, {"error": {"message": "API_KEY_INVALID: API key not valid. Please pass a valid API key."}}
    )
    mock_genai_client_class.return_value = mock_client_instance

    client = GeminiLLMClient(api_key="invalid-key")
    with pytest.raises(LLMAuthError) as exc_info:
        client.generate("prompt")

    assert "authentication failed" in str(exc_info.value).lower()


@patch("google.genai.Client")
def test_gemini_rate_limit_error_handling(mock_genai_client_class: MagicMock) -> None:
    """Verify rate limit / quota exhaustion errors are mapped to LLMRateLimitError."""
    from google.genai import errors

    mock_client_instance = MagicMock()
    mock_client_instance.models.generate_content.side_effect = errors.ClientError(
        429, {"error": {"message": "RESOURCE_EXHAUSTED: Quota exceeded for quota metric 'GenerateContent'."}}
    )
    mock_genai_client_class.return_value = mock_client_instance

    client = GeminiLLMClient(api_key="valid-key")
    with pytest.raises(LLMRateLimitError) as exc_info:
        client.generate("prompt")

    assert "rate limit exceeded" in str(exc_info.value).lower()


@patch("google.genai.Client")
def test_gemini_timeout_error_handling(mock_genai_client_class: MagicMock) -> None:
    """Verify network timeouts are mapped to LLMTimeoutError."""
    mock_client_instance = MagicMock()
    mock_client_instance.models.generate_content.side_effect = TimeoutError("Request timed out")
    mock_genai_client_class.return_value = mock_client_instance

    client = GeminiLLMClient(api_key="valid-key", timeout=5.0)
    with pytest.raises(LLMTimeoutError) as exc_info:
        client.generate("prompt")

    assert "timed out" in str(exc_info.value).lower()


def test_configured_llm_client_missing_key_raises_configuration_error() -> None:
    """Verify ConfiguredLLMClient raises LLMConfigurationError if LLM_PROVIDER='gemini' without key."""
    settings = Settings(llm_provider="gemini", gemini_api_key=None, llm_api_key=None)
    client = ConfiguredLLMClient(settings)
    with pytest.raises(LLMConfigurationError) as exc_info:
        client.generate("prompt")

    assert "GEMINI_API_KEY is not configured" in str(exc_info.value)


@patch("google.genai.Client")
def test_gemini_guardrail_rejection_triggers_fallback_with_metadata(
    mock_genai_client_class: MagicMock,
) -> None:
    """Verify that when Gemini produces unsafe output, guardrails reject it and fallback metadata is populated."""
    mock_response = MagicMock()
    # Unsafe output with medication dosage
    mock_response.text = "Hello Arthur, please take 500mg amoxicillin twice daily."

    mock_client_instance = MagicMock()
    mock_client_instance.models.generate_content.return_value = mock_response
    mock_genai_client_class.return_value = mock_client_instance

    gemini_client = GeminiLLMClient(api_key="mock-key")
    personalizer = GuardrailedAIPersonalizer(llm_client=gemini_client)
    apt = create_synthetic_appointment(first_name="Arthur")

    details = personalizer.personalize_with_details(apt)

    assert details["generation_source"] == "template_fallback"
    assert "Guardrail rejected AI candidate" in details["fallback_reason"]
    assert "amoxicillin" not in details["message_text"]
    assert "routine checkup" in details["message_text"]


@patch("google.genai.Client")
def test_gemini_compliant_output_accepted_with_ai_metadata(
    mock_genai_client_class: MagicMock,
) -> None:
    """Verify compliant output from Gemini is accepted with generation_source='ai'."""
    safe_text = (
        "Hello Arthur, thank you for attending your routine checkup. "
        "Please contact our clinic if you have any questions."
    )
    mock_response = MagicMock()
    mock_response.text = safe_text

    mock_client_instance = MagicMock()
    mock_client_instance.models.generate_content.return_value = mock_response
    mock_genai_client_class.return_value = mock_client_instance

    gemini_client = GeminiLLMClient(api_key="mock-key", model="gemini-2.5-flash")
    personalizer = GuardrailedAIPersonalizer(llm_client=gemini_client)
    apt = create_synthetic_appointment(first_name="Arthur")

    details = personalizer.personalize_with_details(apt)

    assert details["generation_source"] == "ai"
    assert details["model_name"] == "gemini-2.5-flash"
    assert details["fallback_reason"] is None
    assert details["message_text"] == safe_text


# ==============================================================================
# REAL PROVIDER INTEGRATION TEST (OPT-IN VIA GEMINI_API_KEY)
# ==============================================================================
_settings = Settings()
_has_gemini_key = bool(_settings.effective_gemini_api_key)


@pytest.mark.skipif(
    not _has_gemini_key,
    reason="Live Gemini integration test skipped: GEMINI_API_KEY environment variable not set.",
)
def test_gemini_live_provider_integration() -> None:
    """Opt-in live integration test executed against the real Gemini API.

    Safety Guarantee:
    Only runs when GEMINI_API_KEY is present in the local environment.
    Uses purely synthetic patient names and non-clinical prompts.
    """
    settings = Settings()
    real_key = settings.effective_gemini_api_key
    assert real_key, "GEMINI_API_KEY must be set"

    client = GeminiLLMClient(
        api_key=real_key,
        model=settings.effective_gemini_model,
        timeout=15.0,
    )

    apt = create_synthetic_appointment(first_name="Beatrice")
    personalizer = GuardrailedAIPersonalizer(llm_client=client)

    details = personalizer.personalize_with_details(apt)

    # Validate output
    assert details["message_text"], "Generated message must not be empty"
    validator = GuardrailValidator()
    val = validator.validate(details["message_text"], expected_name="Beatrice")

    assert val.is_valid, f"Live Gemini output failed guardrails: {val.reason}"
    assert details["generation_source"] in ("ai", "template_fallback")
    if details["generation_source"] == "ai":
        assert details["model_name"] == settings.effective_gemini_model
