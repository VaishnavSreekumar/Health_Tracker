"""LLM provider abstraction, Google Gemini adapter, and client implementations."""

import logging
from typing import Optional, Protocol, runtime_checkable

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class LLMProviderError(Exception):
    """Base exception for LLM provider failures."""
    pass


class LLMTimeoutError(LLMProviderError):
    """Raised when an LLM provider request exceeds timeout."""
    pass


class LLMConfigurationError(LLMProviderError):
    """Raised when an LLM provider is requested but required configuration/key is missing."""
    pass


class LLMAuthError(LLMProviderError):
    """Raised when authentication with the LLM provider fails."""
    pass


class LLMRateLimitError(LLMProviderError):
    """Raised when LLM provider rate limits or quota are exceeded."""
    pass


class LLMResponseError(LLMProviderError):
    """Raised when the LLM provider returns an empty, invalid, or malformed response."""
    pass


@runtime_checkable
class LLMClient(Protocol):
    """Protocol defining the contract for LLM provider adapters."""

    def generate(self, prompt: str, timeout: float = 5.0) -> str:
        """Send prompt to LLM provider and return response text."""
        ...


class FakeLLMClient:
    """Deterministic, configurable fake LLM client for testing."""

    def __init__(
        self,
        default_response: str = "Hello {name}, thank you for attending your appointment.",
        should_timeout: bool = False,
        error_to_raise: Optional[Exception] = None,
    ):
        self.default_response = default_response
        self.should_timeout = should_timeout
        self.error_to_raise = error_to_raise
        self.calls: list[dict[str, object]] = []

    def generate(self, prompt: str, timeout: float = 5.0) -> str:
        self.calls.append({"prompt": prompt, "timeout": timeout})

        if self.should_timeout:
            raise LLMTimeoutError(f"Request timed out after {timeout} seconds")

        if self.error_to_raise:
            raise self.error_to_raise

        return self.default_response


class GeminiLLMClient:
    """Official Google Gemini provider adapter using the google-genai SDK."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        settings: Optional[Settings] = None,
    ):
        app_settings = settings or get_settings()
        self.api_key = api_key or app_settings.effective_gemini_api_key
        self.model = model or app_settings.effective_gemini_model
        self.timeout = timeout if timeout is not None else app_settings.llm_timeout_seconds

        if not self.api_key:
            raise LLMConfigurationError(
                "Gemini API key is not configured. Set GEMINI_API_KEY or LLM_API_KEY in environment or .env."
            )

        try:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        except Exception as exc:
            raise LLMProviderError(f"Failed to initialize Google Gen AI client: {exc}") from exc

    def generate(self, prompt: str, timeout: Optional[float] = None) -> str:
        """Execute a text generation call to Google Gemini with safe error handling."""
        timeout_val = timeout if timeout is not None else self.timeout

        try:
            from google.genai import errors, types

            config = types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=300,
            )

            logger.info("Executing Gemini generation request (model=%s, timeout=%.1fs)", self.model, timeout_val)
            response = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )

            if not response or not response.text:
                raise LLMResponseError("Gemini provider returned an empty response.")

            return response.text.strip()

        except LLMProviderError:
            raise
        except Exception as exc:
            err_str = str(exc)
            err_type = type(exc).__name__
            code = getattr(exc, "code", None)

            # Check for authentication / authorization errors
            if (
                code in (401, 403)
                or (code == 400 and ("API_KEY" in err_str or "api key" in err_str.lower()))
                or "API_KEY_INVALID" in err_str
                or "API key not valid" in err_str
                or "PERMISSION_DENIED" in err_str
            ):
                logger.error("Gemini authentication failure (%s): %s", err_type, err_str)
                raise LLMAuthError(f"Gemini authentication failed: {err_str}") from exc

            # Check for rate limit / quota exhaustion
            if (
                code == 429
                or "RESOURCE_EXHAUSTED" in err_str
                or "rate limit" in err_str.lower()
                or "quota" in err_str.lower()
            ):
                logger.error("Gemini rate limit exceeded (%s): %s", err_type, err_str)
                raise LLMRateLimitError(f"Gemini rate limit exceeded: {err_str}") from exc

            # Check for timeouts
            if "timeout" in err_str.lower() or "timed out" in err_str.lower() or isinstance(exc, TimeoutError):
                logger.error("Gemini call timed out after %.1fs", timeout_val)
                raise LLMTimeoutError(f"Gemini request timed out after {timeout_val}s") from exc

            # General provider errors
            logger.error("Gemini provider error (%s): %s", err_type, err_str)
            raise LLMProviderError(f"Gemini provider error ({err_type}): {err_str}") from exc


class ConfiguredLLMClient:
    """Production provider adapter reading configuration from environment."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()

    @property
    def is_configured(self) -> bool:
        """Return True if an external LLM provider and key are configured."""
        return self.settings.is_gemini_enabled and bool(self.settings.effective_gemini_api_key)

    @property
    def model(self) -> str:
        """Return the configured model name."""
        return self.settings.effective_gemini_model

    def generate(self, prompt: str, timeout: Optional[float] = None) -> str:
        """Call external provider if configured; raise error otherwise."""
        provider = self.settings.llm_provider.lower()

        if provider == "none" and not self.settings.gemini_api_key:
            raise LLMConfigurationError(
                "No external LLM provider configured. Set LLM_PROVIDER='gemini' and GEMINI_API_KEY."
            )

        if not self.settings.effective_gemini_api_key:
            raise LLMConfigurationError(
                f"LLM provider '{provider}' is enabled, but GEMINI_API_KEY is not configured."
            )

        # Delegate to Gemini client
        gemini_client = GeminiLLMClient(
            api_key=self.settings.effective_gemini_api_key,
            model=self.settings.effective_gemini_model,
            timeout=timeout or self.settings.llm_timeout_seconds,
            settings=self.settings,
        )
        return gemini_client.generate(prompt, timeout=timeout)
