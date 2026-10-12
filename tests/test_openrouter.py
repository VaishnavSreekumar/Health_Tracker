"""Mocked unit and regression tests for OpenRouter provider adapter and failover mechanism.

Tests strictly verify OpenRouter parsing, error classification, zero-cost policy,
failover to Gemini, deterministic fallback, and secret redaction using synthetic mocks.
"""

from datetime import datetime, timezone
import json
from unittest.mock import MagicMock, patch
import pytest

from app.core.config import Settings
from app.models.appointment import Appointment, AppointmentType
from app.models.patient import Patient
from app.services.ai_personalizer import GuardrailedAIPersonalizer
from app.services.guardrails import GuardrailValidator
from app.services.llm_client import (
    ConfiguredLLMClient,
    FakeLLMClient,
    GeminiLLMClient,
    LLMAuthError,
    LLMConfigurationError,
    LLMInvalidRequestError,
    LLMModelNotFoundError,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponseError,
    LLMServiceUnavailableError,
    LLMTimeoutError,
    OpenRouterLLMClient,
    _scrub_sensitive,
)


def create_synthetic_appointment(first_name: str = "Elena") -> Appointment:
    """Helper creating synthetic in-memory encounter with no clinical PII."""
    patient = Patient(id=301, first_name=first_name, last_name="Vance", email="elena.vance@example.synthetic")
    appointment = Appointment(
        id=402,
        patient_id=patient.id,
        appointment_type=AppointmentType.ROUTINE_CHECKUP,
        appointment_datetime=datetime(2026, 10, 10, 10, 0, tzinfo=timezone.utc),
    )
    appointment.patient = patient
    return appointment


# ==============================================================================
# Phase 2 & 3: OpenRouter Configuration & Client Tests
# ==============================================================================

def test_openrouter_missing_api_key_raises_configuration_error() -> None:
    """Verify OpenRouterLLMClient raises LLMConfigurationError if no key is configured."""
    test_settings = Settings(openrouter_api_key=None, llm_api_key=None)
    with pytest.raises(LLMConfigurationError) as exc_info:
        OpenRouterLLMClient(api_key=None, settings=test_settings)

    assert "OpenRouter API key is not configured" in str(exc_info.value)


def test_openrouter_non_free_model_rejected_by_zero_cost_policy() -> None:
    """Verify strict zero-cost policy rejects any model lacking the ':free' tag."""
    test_settings = Settings(
        openrouter_api_key="synthetic-key",
        openrouter_model="openai/gpt-4o",  # Paid model without :free tag
    )
    with pytest.raises(LLMConfigurationError) as exc_info:
        OpenRouterLLMClient(settings=test_settings)

    assert "Strict zero-cost policy violation" in str(exc_info.value)
    assert ":free" in str(exc_info.value)


@patch("httpx.Client")
def test_openrouter_successful_generation_parsed(mock_httpx_client_class: MagicMock) -> None:
    """Verify successful 200 OK Chat Completions response is extracted and stripped."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "gen-123",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "  Hello Elena, thank you for attending your routine checkup. Please reach out if you have questions.  ",
                }
            }
        ],
    }

    mock_client_instance = MagicMock()
    mock_client_instance.__enter__.return_value = mock_client_instance
    mock_client_instance.post.return_value = mock_response
    mock_httpx_client_class.return_value = mock_client_instance

    client = OpenRouterLLMClient(
        api_key="synthetic-key",
        model="meta-llama/llama-3.3-70b-instruct:free",
    )
    result = client.generate("synthetic prompt")

    assert result == "Hello Elena, thank you for attending your routine checkup. Please reach out if you have questions."
    mock_client_instance.post.assert_called_once()


@patch("httpx.Client")
def test_openrouter_markdown_fence_and_quote_stripping(mock_httpx_client_class: MagicMock) -> None:
    """Verify surrounding markdown fences and quotation marks are cleanly stripped."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": '```\n"Hello Elena, thank you for visiting our clinic for your checkup."\n```',
                }
            }
        ]
    }

    mock_client_instance = MagicMock()
    mock_client_instance.__enter__.return_value = mock_client_instance
    mock_client_instance.post.return_value = mock_response
    mock_httpx_client_class.return_value = mock_client_instance

    client = OpenRouterLLMClient(
        api_key="synthetic-key",
        model="meta-llama/llama-3.3-70b-instruct:free",
    )
    result = client.generate("synthetic prompt")

    assert result == "Hello Elena, thank you for visiting our clinic for your checkup."


@patch("httpx.Client")
def test_openrouter_empty_choices_raises_response_error(mock_httpx_client_class: MagicMock) -> None:
    """Verify response with missing or empty choices array raises LLMResponseError."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"choices": []}

    mock_client_instance = MagicMock()
    mock_client_instance.__enter__.return_value = mock_client_instance
    mock_client_instance.post.return_value = mock_response
    mock_httpx_client_class.return_value = mock_client_instance

    client = OpenRouterLLMClient(api_key="synthetic-key", model="meta-llama/llama-3.3-70b-instruct:free")
    with pytest.raises(LLMResponseError) as exc_info:
        client.generate("prompt")

    assert "empty choices array" in str(exc_info.value).lower()


@patch("httpx.Client")
def test_openrouter_empty_content_raises_response_error(mock_httpx_client_class: MagicMock) -> None:
    """Verify empty message content string raises LLMResponseError."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "   "}}]
    }

    mock_client_instance = MagicMock()
    mock_client_instance.__enter__.return_value = mock_client_instance
    mock_client_instance.post.return_value = mock_response
    mock_httpx_client_class.return_value = mock_client_instance

    client = OpenRouterLLMClient(api_key="synthetic-key", model="meta-llama/llama-3.3-70b-instruct:free")
    with pytest.raises(LLMResponseError) as exc_info:
        client.generate("prompt")

    assert "empty message content" in str(exc_info.value).lower()


@patch("httpx.Client")
def test_openrouter_auth_error_handling(mock_httpx_client_class: MagicMock) -> None:
    """Verify HTTP 401 Unauthorized is mapped to LLMAuthError."""
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.json.return_value = {"error": {"message": "Invalid API key provided."}}

    mock_client_instance = MagicMock()
    mock_client_instance.__enter__.return_value = mock_client_instance
    mock_client_instance.post.return_value = mock_response
    mock_httpx_client_class.return_value = mock_client_instance

    client = OpenRouterLLMClient(api_key="invalid-key", model="meta-llama/llama-3.3-70b-instruct:free")
    with pytest.raises(LLMAuthError) as exc_info:
        client.generate("prompt")

    assert "authentication failed" in str(exc_info.value).lower()


@patch("httpx.Client")
def test_openrouter_rate_limit_error_handling(mock_httpx_client_class: MagicMock) -> None:
    """Verify HTTP 429 Too Many Requests is mapped to LLMRateLimitError."""
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.json.return_value = {"error": {"message": "Rate limit exceeded for free tier."}}

    mock_client_instance = MagicMock()
    mock_client_instance.__enter__.return_value = mock_client_instance
    mock_client_instance.post.return_value = mock_response
    mock_httpx_client_class.return_value = mock_client_instance

    client = OpenRouterLLMClient(api_key="synthetic-key", model="meta-llama/llama-3.3-70b-instruct:free")
    with pytest.raises(LLMRateLimitError) as exc_info:
        client.generate("prompt")

    assert "rate limit or quota exceeded" in str(exc_info.value).lower()


@patch("httpx.Client")
def test_openrouter_service_unavailable_error_handling(mock_httpx_client_class: MagicMock) -> None:
    """Verify HTTP 503 is mapped to LLMServiceUnavailableError."""
    mock_response = MagicMock()
    mock_response.status_code = 503
    mock_response.json.return_value = {"error": {"message": "Service Temporarily Unavailable"}}

    mock_client_instance = MagicMock()
    mock_client_instance.__enter__.return_value = mock_client_instance
    mock_client_instance.post.return_value = mock_response
    mock_httpx_client_class.return_value = mock_client_instance

    client = OpenRouterLLMClient(api_key="synthetic-key", model="meta-llama/llama-3.3-70b-instruct:free")
    with pytest.raises(LLMServiceUnavailableError) as exc_info:
        client.generate("prompt")

    assert "temporarily unavailable" in str(exc_info.value).lower()


@patch("httpx.Client")
def test_openrouter_timeout_error_handling(mock_httpx_client_class: MagicMock) -> None:
    """Verify network timeouts are mapped to LLMTimeoutError."""
    import httpx

    mock_client_instance = MagicMock()
    mock_client_instance.__enter__.return_value = mock_client_instance
    mock_client_instance.post.side_effect = httpx.ReadTimeout("Request timed out")
    mock_httpx_client_class.return_value = mock_client_instance

    client = OpenRouterLLMClient(api_key="synthetic-key", model="meta-llama/llama-3.3-70b-instruct:free", timeout=5.0)
    with pytest.raises(LLMTimeoutError) as exc_info:
        client.generate("prompt")

    assert "timed out" in str(exc_info.value).lower()


@patch("httpx.Client")
def test_openrouter_model_not_found_mapped_accurately(mock_httpx_client_class: MagicMock) -> None:
    """Verify HTTP 404 is mapped to LLMModelNotFoundError."""
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.json.return_value = {"error": {"message": "Model not found"}}

    mock_client_instance = MagicMock()
    mock_client_instance.__enter__.return_value = mock_client_instance
    mock_client_instance.post.return_value = mock_response
    mock_httpx_client_class.return_value = mock_client_instance

    client = OpenRouterLLMClient(api_key="synthetic-key", model="unknown/model:free")
    with pytest.raises(LLMModelNotFoundError) as exc_info:
        client.generate("prompt")

    assert "model not found" in str(exc_info.value).lower()


# ==============================================================================
# Phase 4 & 5: Guardrails & Safe Fallback with OpenRouter
# ==============================================================================

@patch("httpx.Client")
def test_openrouter_guardrail_rejection_triggers_safe_fallback_without_bypass(
    mock_httpx_client_class: MagicMock,
) -> None:
    """Verify that when OpenRouter produces clinically unsafe output, it is rejected and falls back safely."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    # Prohibited clinical diagnosis and prescription
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Hello Elena, take 20mg prednisone daily for your infection.",
                }
            }
        ]
    }

    mock_client_instance = MagicMock()
    mock_client_instance.__enter__.return_value = mock_client_instance
    mock_client_instance.post.return_value = mock_response
    mock_httpx_client_class.return_value = mock_client_instance

    openrouter_client = OpenRouterLLMClient(
        api_key="synthetic-key",
        model="meta-llama/llama-3.3-70b-instruct:free",
    )
    personalizer = GuardrailedAIPersonalizer(llm_client=openrouter_client)
    apt = create_synthetic_appointment(first_name="Elena")

    details = personalizer.personalize_with_details(apt)

    assert details["generation_source"] == "template_fallback"
    assert "Guardrail rejected AI candidate" in details["fallback_reason"]
    assert "prednisone" not in details["message_text"]
    assert "routine checkup" in details["message_text"]


@patch("httpx.Client")
def test_openrouter_compliant_output_accepted_with_ai_metadata(
    mock_httpx_client_class: MagicMock,
) -> None:
    """Verify compliant output from OpenRouter is accepted with generation_source='ai'."""
    safe_text = (
        "Hello Elena, thank you for attending your routine checkup with our clinic. "
        "Please contact our team if you have any questions."
    )
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": safe_text}}]
    }

    mock_client_instance = MagicMock()
    mock_client_instance.__enter__.return_value = mock_client_instance
    mock_client_instance.post.return_value = mock_response
    mock_httpx_client_class.return_value = mock_client_instance

    openrouter_client = OpenRouterLLMClient(
        api_key="synthetic-key",
        model="meta-llama/llama-3.3-70b-instruct:free",
    )
    personalizer = GuardrailedAIPersonalizer(llm_client=openrouter_client)
    apt = create_synthetic_appointment(first_name="Elena")

    details = personalizer.personalize_with_details(apt)

    assert details["generation_source"] == "ai"
    assert details["model_name"] == "meta-llama/llama-3.3-70b-instruct:free"
    assert details["fallback_reason"] is None
    assert details["message_text"] == safe_text


# ==============================================================================
# Phase 4 & 6: Provider Failover & Accurate Provenance
# ==============================================================================

def test_openrouter_failover_to_gemini_when_openrouter_fails() -> None:
    """Verify failover: when OpenRouter fails with service error, Gemini backup is invoked."""
    openrouter_failing = FakeLLMClient(
        error_to_raise=LLMServiceUnavailableError("OpenRouter 503 Service Unavailable"),
        model="meta-llama/llama-3.3-70b-instruct:free",
        provider_name="openrouter",
    )
    gemini_successful = FakeLLMClient(
        default_response="Hello Elena, thank you for attending your routine checkup with our clinic team.",
        model="gemini-3.6-flash",
        provider_name="gemini",
    )

    personalizer = GuardrailedAIPersonalizer(
        llm_client=openrouter_failing,
        secondary_client=gemini_successful,
    )
    apt = create_synthetic_appointment(first_name="Elena")

    details = personalizer.personalize_with_details(apt)

    # Provenance must truthfully record Gemini as the source!
    assert details["generation_source"] == "ai"
    assert details["model_name"] == "gemini-3.6-flash"
    assert details["fallback_reason"] is None
    assert "Elena" in details["message_text"]


def test_openrouter_failover_both_providers_fail_triggers_deterministic_template() -> None:
    """Verify that when both OpenRouter and Gemini fail, deterministic template fallback is used."""
    openrouter_failing = FakeLLMClient(
        error_to_raise=LLMRateLimitError("OpenRouter 429 quota exhausted"),
        model="meta-llama/llama-3.3-70b-instruct:free",
        provider_name="openrouter",
    )
    gemini_failing = FakeLLMClient(
        error_to_raise=LLMRateLimitError("Gemini 429 RESOURCE_EXHAUSTED"),
        model="gemini-3.6-flash",
        provider_name="gemini",
    )

    personalizer = GuardrailedAIPersonalizer(
        llm_client=openrouter_failing,
        secondary_client=gemini_failing,
    )
    apt = create_synthetic_appointment(first_name="Elena")

    details = personalizer.personalize_with_details(apt)

    assert details["generation_source"] == "template_fallback"
    assert details["model_name"] is None
    assert "Openrouter" in details["fallback_reason"] or "openrouter" in details["fallback_reason"].lower()
    assert "Gemini" in details["fallback_reason"] or "gemini" in details["fallback_reason"].lower()
    assert "routine checkup" in details["message_text"]


def test_secret_redaction_masks_openrouter_key() -> None:
    """Verify _scrub_sensitive masks OpenRouter format API keys (sk-or-v1-...)."""
    dummy_hex = "0123456789abcdef" * 4
    dummy_key = "sk-or-v1-" + dummy_hex
    sample_error = (
        f"HTTP 401 Unauthorized for Authorization: Bearer {dummy_key} "
        "with key=sk-or-test"
    )
    scrubbed = _scrub_sensitive(sample_error)

    assert dummy_hex not in scrubbed
    assert "sk-or-v1-...REDACTED" in scrubbed or "Bearer REDACTED" in scrubbed


def test_configured_llm_client_openrouter_support() -> None:
    """Verify ConfiguredLLMClient correctly recognizes openrouter provider configuration."""
    settings = Settings(
        llm_provider="openrouter",
        openrouter_api_key="synthetic-key",
        openrouter_model="meta-llama/llama-3.3-70b-instruct:free",
    )
    client = ConfiguredLLMClient(settings)
    assert client.is_configured is True
    assert client.model == "meta-llama/llama-3.3-70b-instruct:free"
