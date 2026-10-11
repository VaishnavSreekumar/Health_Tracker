"""Business logic and services package."""

from .ai_personalizer import GuardrailedAIPersonalizer, PersonalizationError
from .eligibility import get_eligible_appointments, normalize_to_utc
from .generator import GenerationResult, ReminderGenerationService
from .guardrails import GuardrailResult, GuardrailValidator
from .llm_client import (
    ConfiguredLLMClient,
    FakeLLMClient,
    LLMClient,
    LLMProviderError,
    LLMTimeoutError,
)
from .personalizer import MessagePersonalizer, TemplateMessagePersonalizer

__all__ = [
    "get_eligible_appointments",
    "normalize_to_utc",
    "MessagePersonalizer",
    "TemplateMessagePersonalizer",
    "GuardrailResult",
    "GuardrailValidator",
    "LLMClient",
    "FakeLLMClient",
    "ConfiguredLLMClient",
    "LLMProviderError",
    "LLMTimeoutError",
    "GuardrailedAIPersonalizer",
    "PersonalizationError",
    "ReminderGenerationService",
    "GenerationResult",
]
