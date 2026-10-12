"""LLM provider abstraction, Google Gemini adapter, OpenRouter adapter, and client implementations."""

import logging
import re
import time
from typing import Optional, Protocol, runtime_checkable

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _scrub_sensitive(text: str) -> str:
    """Mask potential API keys or query params from error messages and logs."""
    text = re.sub(r"(key=)[^&\s]+", r"\1REDACTED", text)
    text = re.sub(r"AIza[0-9A-Za-z\-_]{35}", "AIza...REDACTED", text)
    text = re.sub(r"sk-or-v1-[0-9a-fA-F]{64}", "sk-or-v1-...REDACTED", text)
    text = re.sub(r"sk-or-[0-9a-zA-Z\-_]+", "sk-or-...REDACTED", text)
    text = re.sub(r"Bearer\s+[^\s]+", "Bearer REDACTED", text)
    return text


class LLMProviderError(Exception):
    """Base exception for LLM provider failures."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        original_error: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.original_error = original_error


class LLMTimeoutError(LLMProviderError):
    """Raised when an LLM provider request exceeds timeout."""
    pass


class LLMConfigurationError(LLMProviderError):
    """Raised when an LLM provider is requested but required configuration/key is missing."""
    pass


class LLMServiceUnavailableError(LLMProviderError):
    """Raised when the LLM provider service is temporarily unavailable or overloaded."""
    pass


class LLMAuthError(LLMProviderError):
    """Raised when authentication with the LLM provider fails."""
    pass


class LLMRateLimitError(LLMProviderError):
    """Raised when LLM provider rate limits or quota are exceeded."""
    pass


class LLMModelNotFoundError(LLMProviderError):
    """Raised when the requested LLM model does not exist or is not available."""
    pass


class LLMInvalidRequestError(LLMProviderError):
    """Raised when the LLM provider rejects the request payload or arguments."""
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
        model: str = "fake-model:free",
        provider_name: str = "fake",
    ):
        self.default_response = default_response
        self.should_timeout = should_timeout
        self.error_to_raise = error_to_raise
        self.model = model
        self.provider_name = provider_name
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
        self.provider_name = "gemini"

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

            config_kwargs = {
                "temperature": 0.2,
                "max_output_tokens": 800,
            }
            if hasattr(types, "ThinkingConfig"):
                try:
                    config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
                except Exception:
                    pass

            config = types.GenerateContentConfig(**config_kwargs)

            logger.info(
                "Stage=request_attempt provider=gemini model=%s timeout=%.1fs prompt_length=%d",
                self.model,
                timeout_val,
                len(prompt),
            )
            response = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )

            if not response or not response.text:
                logger.warning("Stage=empty_response provider=gemini model=%s", self.model)
                raise LLMResponseError("Gemini provider returned an empty response.")

            clean_text = response.text.strip()
            # Strip surrounding markdown code block fences if present
            if clean_text.startswith("```") and clean_text.endswith("```"):
                lines = clean_text.splitlines()
                if len(lines) >= 3:
                    clean_text = "\n".join(lines[1:-1]).strip()
            # Strip surrounding quotation marks if present
            if clean_text.startswith(('"', "'")) and clean_text.endswith(('"', "'")) and len(clean_text) > 2:
                clean_text = clean_text[1:-1].strip()

            logger.info(
                "Stage=response_received provider=gemini model=%s response_length=%d",
                self.model,
                len(clean_text),
            )
            return clean_text

        except LLMProviderError:
            raise
        except Exception as exc:
            err_str = _scrub_sensitive(str(exc))
            err_type = type(exc).__name__
            code = getattr(exc, "code", None)
            status_val = getattr(exc, "status", None)

            # Check for authentication / authorization errors
            if (
                code in (401, 403)
                or status_val == "PERMISSION_DENIED"
                or (code == 400 and ("API_KEY" in err_str or "api key" in err_str.lower()))
                or "API_KEY_INVALID" in err_str
                or "API key not valid" in err_str
                or "PERMISSION_DENIED" in err_str
            ):
                logger.error("Stage=provider_error category=auth status=%s type=%s detail='%s'", code, err_type, err_str[:120])
                raise LLMAuthError(f"Gemini authentication failed: {err_str}", status_code=code, original_error=exc) from exc

            # Check for rate limit / quota exhaustion
            if (
                code == 429
                or status_val == "RESOURCE_EXHAUSTED"
                or "RESOURCE_EXHAUSTED" in err_str
                or "rate limit" in err_str.lower()
                or "quota" in err_str.lower()
            ):
                logger.error("Stage=provider_error category=rate_limit status=%s type=%s detail='%s'", code, err_type, err_str[:120])
                raise LLMRateLimitError(f"Gemini quota or rate limit exceeded (429 RESOURCE_EXHAUSTED): {err_str}", status_code=code, original_error=exc) from exc

            # Check for service unavailable / high demand (503)
            if (
                code == 503
                or status_val == "UNAVAILABLE"
                or "UNAVAILABLE" in err_str
                or "high demand" in err_str.lower()
            ):
                logger.error("Stage=provider_error category=service_unavailable status=%s type=%s detail='%s'", code, err_type, err_str[:120])
                raise LLMServiceUnavailableError(f"Gemini service temporarily unavailable (503 high demand): {err_str}", status_code=code, original_error=exc) from exc

            # Check for model not found / unsupported model
            if (
                code == 404
                or status_val == "NOT_FOUND"
                or ("models/" in err_str.lower() and "not found" in err_str.lower())
                or "is not found for api version" in err_str.lower()
            ):
                logger.error("Stage=provider_error category=model_not_found model=%s status=%s type=%s detail='%s'", self.model, code, err_type, err_str[:120])
                raise LLMModelNotFoundError(f"Gemini model not found or unsupported ({self.model}): {err_str}", status_code=code, original_error=exc) from exc

            # Check for invalid request / bad arguments
            if (
                code == 400
                or status_val == "INVALID_ARGUMENT"
                or "INVALID_ARGUMENT" in err_str
            ):
                logger.error("Stage=provider_error category=invalid_request status=%s type=%s detail='%s'", code, err_type, err_str[:120])
                raise LLMInvalidRequestError(f"Gemini request invalid (400 INVALID_ARGUMENT): {err_str}", status_code=code, original_error=exc) from exc

            # Check for timeouts
            if "timeout" in err_str.lower() or "timed out" in err_str.lower() or isinstance(exc, TimeoutError) or status_val == "DEADLINE_EXCEEDED" or code == 504:
                logger.error("Stage=provider_error category=timeout timeout=%.1fs type=%s detail='%s'", timeout_val, err_type, err_str[:120])
                raise LLMTimeoutError(f"Gemini request timed out after {timeout_val:.1f}s", status_code=code, original_error=exc) from exc

            # General provider errors
            logger.error("Stage=provider_error category=unknown status=%s type=%s detail='%s'", code, err_type, err_str[:120])
            raise LLMProviderError(f"Gemini provider error ({err_type}): {err_str}", status_code=code, original_error=exc) from exc


class OpenRouterLLMClient:
    """Official OpenRouter provider adapter using the OpenAI-compatible Chat Completions API.

    Strict Zero-Cost Policy:
    - Enforces that model identifier has explicit ':free' tag.
    - Never falls back to paid models or enables unverified billing.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        site_url: Optional[str] = None,
        app_name: Optional[str] = None,
        timeout: Optional[float] = None,
        settings: Optional[Settings] = None,
    ):
        app_settings = settings or get_settings()
        self.api_key = api_key or app_settings.effective_openrouter_api_key
        self.model = model or app_settings.effective_openrouter_model
        raw_base = base_url or app_settings.openrouter_base_url
        self.base_url = raw_base.rstrip("/")
        self.site_url = site_url or app_settings.openrouter_site_url
        self.app_name = app_name or app_settings.openrouter_app_name
        self.timeout = timeout if timeout is not None else app_settings.llm_timeout_seconds
        self.provider_name = "openrouter"

        if not self.api_key:
            raise LLMConfigurationError(
                "OpenRouter API key is not configured. Set OPENROUTER_API_KEY in environment or .env."
            )

        # Enforce strict zero-cost policy: verify model has ':free' suffix/tag
        if not self._is_free_model(self.model):
            raise LLMConfigurationError(
                f"Strict zero-cost policy violation: Configured OpenRouter model '{self.model}' "
                "does not contain ':free'. HealthTrack forbids non-free models to prevent accidental billing."
            )

    @staticmethod
    def _is_free_model(model_name: Optional[str]) -> bool:
        """Verify that the model identifier explicitly corresponds to a free model."""
        if not model_name:
            return False
        return ":free" in model_name.strip().lower()

    def generate(self, prompt: str, timeout: Optional[float] = None) -> str:
        """Send chat completion request to OpenRouter with strict validation and safe error mapping."""
        timeout_val = timeout if timeout is not None else self.timeout
        endpoint = f"{self.base_url}/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.site_url:
            headers["HTTP-Referer"] = self.site_url
        if self.app_name:
            headers["X-Title"] = self.app_name

        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
            "max_tokens": 800,
        }

        logger.info(
            "Stage=request_attempt provider=openrouter model=%s timeout=%.1fs prompt_length=%d",
            self.model,
            timeout_val,
            len(prompt),
        )

        try:
            import httpx

            with httpx.Client(timeout=timeout_val) as client:
                response = client.post(endpoint, json=payload, headers=headers)

            return self._handle_response(response)

        except LLMProviderError:
            raise
        except Exception as exc:
            err_type = type(exc).__name__
            err_str = _scrub_sensitive(str(exc))

            if "timeout" in err_str.lower() or "timed out" in err_str.lower() or "Timeout" in err_type:
                logger.error("Stage=provider_error provider=openrouter category=timeout timeout=%.1fs detail='%s'", timeout_val, err_str[:120])
                raise LLMTimeoutError(f"OpenRouter request timed out after {timeout_val:.1f}s", original_error=exc) from exc

            if "connect" in err_str.lower() or "network" in err_str.lower() or "Network" in err_type or "Connect" in err_type:
                logger.error("Stage=provider_error provider=openrouter category=network status=None type=%s detail='%s'", err_type, err_str[:120])
                raise LLMServiceUnavailableError(f"OpenRouter network connection failure: {err_str}", original_error=exc) from exc

            logger.error("Stage=provider_error provider=openrouter category=unknown status=None type=%s detail='%s'", err_type, err_str[:120])
            raise LLMProviderError(f"OpenRouter unexpected failure ({err_type}): {err_str}", original_error=exc) from exc

    def _handle_response(self, response: object) -> str:
        """Parse and validate OpenRouter HTTP response payload."""
        status_code = getattr(response, "status_code", 500)
        try:
            data = response.json() if hasattr(response, "json") else None  # type: ignore[union-attr]
        except Exception:
            data = None

        if status_code == 200:
            if not isinstance(data, dict):
                raise LLMResponseError("OpenRouter returned malformed response (non-dictionary JSON).", status_code=200)

            if "error" in data:
                err_data = data["error"]
                err_msg = _scrub_sensitive(err_data.get("message", str(err_data)) if isinstance(err_data, dict) else str(err_data))
                logger.error("Stage=provider_error provider=openrouter category=inline_error detail='%s'", err_msg[:120])
                raise LLMResponseError(f"OpenRouter returned error in 200 response: {err_msg}", status_code=200)

            choices = data.get("choices")
            if not choices or not isinstance(choices, list) or len(choices) == 0:
                logger.warning("Stage=empty_response provider=openrouter model=%s", self.model)
                raise LLMResponseError("OpenRouter returned empty choices array in response.", status_code=200)

            first_choice = choices[0]
            if not isinstance(first_choice, dict):
                raise LLMResponseError("OpenRouter choice item is not a dictionary.", status_code=200)

            message_obj = first_choice.get("message") or {}
            content = message_obj.get("content")
            if content is None or not str(content).strip():
                logger.warning("Stage=empty_response provider=openrouter model=%s", self.model)
                raise LLMResponseError("OpenRouter returned empty message content in response.", status_code=200)

            clean_text = str(content).strip()
            # Strip surrounding markdown code block fences if present
            if clean_text.startswith("```") and clean_text.endswith("```"):
                lines = clean_text.splitlines()
                if len(lines) >= 3:
                    clean_text = "\n".join(lines[1:-1]).strip()
            # Strip surrounding quotation marks if present
            if clean_text.startswith(('"', "'")) and clean_text.endswith(('"', "'")) and len(clean_text) > 2:
                clean_text = clean_text[1:-1].strip()

            logger.info(
                "Stage=response_received provider=openrouter model=%s response_length=%d",
                self.model,
                len(clean_text),
            )
            return clean_text

        # Non-200 status handling
        err_detail = ""
        if isinstance(data, dict) and "error" in data:
            err_data = data["error"]
            err_detail = err_data.get("message", str(err_data)) if isinstance(err_data, dict) else str(err_data)
        elif hasattr(response, "text") and response.text:
            err_detail = response.text
        else:
            err_detail = f"HTTP {status_code}"

        err_str = _scrub_sensitive(str(err_detail))

        # Check authentication / unauthorized
        if status_code in (401, 403) or "unauthorized" in err_str.lower() or "invalid api key" in err_str.lower():
            logger.error("Stage=provider_error provider=openrouter category=auth status=%d detail='%s'", status_code, err_str[:120])
            raise LLMAuthError(f"OpenRouter authentication failed ({status_code}): {err_str}", status_code=status_code)

        # Check rate limit / quota
        if status_code == 429 or "rate limit" in err_str.lower() or "quota" in err_str.lower() or "credits" in err_str.lower():
            logger.error("Stage=provider_error provider=openrouter category=rate_limit status=429 detail='%s'", err_str[:120])
            raise LLMRateLimitError(f"OpenRouter rate limit or quota exceeded (429): {err_str}", status_code=429)

        # Check model not found
        if status_code == 404 or ("model" in err_str.lower() and "not found" in err_str.lower()):
            logger.error("Stage=provider_error provider=openrouter category=model_not_found model=%s status=404 detail='%s'", self.model, err_str[:120])
            raise LLMModelNotFoundError(f"OpenRouter model not found or unsupported ({self.model}): {err_str}", status_code=404)

        # Check invalid request / argument
        if status_code in (400, 422):
            logger.error("Stage=provider_error provider=openrouter category=invalid_request status=%d detail='%s'", status_code, err_str[:120])
            raise LLMInvalidRequestError(f"OpenRouter request invalid ({status_code}): {err_str}", status_code=status_code)

        # Check service unavailable / bad gateway / gateway timeout
        if status_code in (502, 503, 504) or "unavailable" in err_str.lower() or "high demand" in err_str.lower():
            logger.error("Stage=provider_error provider=openrouter category=service_unavailable status=%d detail='%s'", status_code, err_str[:120])
            raise LLMServiceUnavailableError(f"OpenRouter service temporarily unavailable ({status_code}): {err_str}", status_code=status_code)

        # General provider error
        logger.error("Stage=provider_error provider=openrouter category=unknown status=%d detail='%s'", status_code, err_str[:120])
        raise LLMProviderError(f"OpenRouter provider error ({status_code}): {err_str}", status_code=status_code)


class ConfiguredLLMClient:
    """Production provider adapter reading configuration from environment."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()

    @property
    def is_configured(self) -> bool:
        """Return True if an external LLM provider and key are configured."""
        prov = self.settings.llm_provider.lower()
        if prov in ("openrouter", "openrouter_with_gemini_fallback"):
            return bool(self.settings.effective_openrouter_api_key)
        if prov == "gemini":
            return bool(self.settings.effective_gemini_api_key)
        return False

    @property
    def model(self) -> str:
        """Return the configured primary model name."""
        prov = self.settings.llm_provider.lower()
        if prov in ("openrouter", "openrouter_with_gemini_fallback"):
            return self.settings.effective_openrouter_model
        return self.settings.effective_gemini_model

    def generate(self, prompt: str, timeout: Optional[float] = None) -> str:
        """Call configured external provider with failover support where applicable."""
        provider = self.settings.llm_provider.lower()

        if provider == "none":
            raise LLMConfigurationError(
                "No external LLM provider configured. Set LLM_PROVIDER='openrouter' or 'gemini'."
            )

        if provider == "openrouter":
            if not self.settings.effective_openrouter_api_key:
                raise LLMConfigurationError(
                    "LLM provider 'openrouter' is enabled, but OPENROUTER_API_KEY is not configured."
                )
            client = OpenRouterLLMClient(settings=self.settings, timeout=timeout)
            return client.generate(prompt, timeout=timeout)

        if provider == "gemini":
            if not self.settings.effective_gemini_api_key:
                raise LLMConfigurationError(
                    "LLM provider 'gemini' is enabled, but GEMINI_API_KEY is not configured."
                )
            gemini_client = GeminiLLMClient(
                api_key=self.settings.effective_gemini_api_key,
                model=self.settings.effective_gemini_model,
                timeout=timeout or self.settings.llm_timeout_seconds,
                settings=self.settings,
            )
            return gemini_client.generate(prompt, timeout=timeout)

        if provider == "openrouter_with_gemini_fallback":
            if not self.settings.effective_openrouter_api_key and not self.settings.effective_gemini_api_key:
                raise LLMConfigurationError(
                    "LLM provider 'openrouter_with_gemini_fallback' is enabled, but neither OPENROUTER_API_KEY nor GEMINI_API_KEY is configured."
                )

            # Try OpenRouter first if configured
            if self.settings.effective_openrouter_api_key:
                try:
                    openrouter_client = OpenRouterLLMClient(settings=self.settings, timeout=timeout)
                    return openrouter_client.generate(prompt, timeout=timeout)
                except (LLMServiceUnavailableError, LLMTimeoutError, LLMRateLimitError) as primary_err:
                    if self.settings.effective_gemini_api_key:
                        logger.warning(
                            "Stage=provider_failover from=openrouter to=gemini reason='%s'",
                            _scrub_sensitive(str(primary_err))[:120],
                        )
                        gemini_client = GeminiLLMClient(
                            api_key=self.settings.effective_gemini_api_key,
                            model=self.settings.effective_gemini_model,
                            timeout=timeout or self.settings.llm_timeout_seconds,
                            settings=self.settings,
                        )
                        return gemini_client.generate(prompt, timeout=timeout)
                    raise

            # Fallback if only Gemini is configured
            if self.settings.effective_gemini_api_key:
                gemini_client = GeminiLLMClient(
                    api_key=self.settings.effective_gemini_api_key,
                    model=self.settings.effective_gemini_model,
                    timeout=timeout or self.settings.llm_timeout_seconds,
                    settings=self.settings,
                )
                return gemini_client.generate(prompt, timeout=timeout)

        raise LLMConfigurationError(f"Unsupported LLM provider: '{provider}'")
