"""Output guardrail validation for follow-up reminders.

Ensures generated messages strictly adhere to clinical safety, privacy,
length bounds, and injection-prevention criteria before persistence.
"""

from dataclasses import dataclass
import re
from typing import Optional, Set


@dataclass(frozen=True)
class GuardrailResult:
    """Outcome of message guardrail validation."""

    is_valid: bool
    reason: Optional[str] = None


class GuardrailValidator:
    """Pre-persistence validator enforcing healthcare communication constraints.

    Limitations Notice:
    Pattern matching provides conservative defense-in-depth against obvious clinical
    claims, leaked instructions, and hallucinated dates, but does not guarantee semantic
    medical safety.
    """

    MIN_LENGTH: int = 15
    MAX_LENGTH: int = 350

    APPROVED_GREETINGS: Set[str] = {
        "there",
        "hello there",
        "hi there",
        "dear patient",
    }

    # Prohibited medical terms, diagnoses, medications, and dosages
    CLINICAL_PATTERNS = re.compile(
        r"\b("
        r"diagnos(?:is|ed|ing)|"
        r"prescrib(?:e|ed|ing|tion)|"
        r"medicat(?:e|ed|ion|ions)|"
        r"dos(?:e|age|ing)|"
        r"\d+\s*(?:mg|ml|mcg|g)\b|"
        r"antibiotic|ibuprofen|tylenol|aspirin|steroid|chemo|insulin|"
        r"treatment\s+plan|cur(?:e|ed)|take\s+\d+|pills?|tablets?|surgery"
        r")\b",
        re.IGNORECASE,
    )

    # Hallucinated dates, numeric times, dollars, and phone numbers
    DATE_AND_NUMERIC_PATTERNS = re.compile(
        r"("
        r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b|"
        r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b|"
        r"\b\d{4}-\d{2}-\d{2}\b|"
        r"\b\d{1,2}:\d{2}\s*(?:am|pm)?\b|"
        r"\$\d+|"
        r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b|"
        r"\b\d+\b"
        r")",
        re.IGNORECASE,
    )

    # PII patterns and leaked prompt/system instructions
    LEAKAGE_AND_INJECTION_PATTERNS = re.compile(
        r"("
        r"[\w.+-]+@[\w-]+\.[\w.-]+|"
        r"\b(?:patient_id|appointment_id)\b|"
        r"\bid\s*=\s*\d+|"
        r"\b(?:system|user|assistant|prompt|instructions?)\s*:|"
        r"\bignore\s+previous"
        r")",
        re.IGNORECASE,
    )

    def validate(
        self,
        message: Optional[str],
        expected_name: Optional[str] = None,
        allow_numbers: bool = False,
    ) -> GuardrailResult:
        """Validate candidate message text against all guardrail rules."""
        if not message or not isinstance(message, str):
            return GuardrailResult(is_valid=False, reason="Message is empty or not a string")

        trimmed = message.strip()

        # 1. Length constraints
        if len(trimmed) < self.MIN_LENGTH:
            return GuardrailResult(
                is_valid=False,
                reason=f"Message too short ({len(trimmed)} < {self.MIN_LENGTH})",
            )
        if len(trimmed) > self.MAX_LENGTH:
            return GuardrailResult(
                is_valid=False,
                reason=f"Message exceeds maximum length ({len(trimmed)} > {self.MAX_LENGTH})",
            )

        # 2. Required greeting / patient name check
        lower_msg = trimmed.lower()
        has_name = False
        if expected_name and expected_name.strip():
            clean_name = expected_name.strip().lower()
            if clean_name != "there" and clean_name in lower_msg:
                has_name = True

        if not has_name:
            # Check for approved neutral fallback greetings
            has_approved_greeting = any(
                greeting in lower_msg for greeting in self.APPROVED_GREETINGS
            )
            if not has_approved_greeting:
                return GuardrailResult(
                    is_valid=False,
                    reason="Message lacks expected patient name or approved neutral greeting",
                )

        # 3. Information leakage and prompt injection echo check
        leak_match = self.LEAKAGE_AND_INJECTION_PATTERNS.search(trimmed)
        if leak_match:
            return GuardrailResult(
                is_valid=False,
                reason=f"Message contains internal identifier, email, or leaked instruction: '{leak_match.group(0)}'",
            )

        # 4. Clinical and prescription pattern check
        clinical_match = self.CLINICAL_PATTERNS.search(trimmed)
        if clinical_match:
            return GuardrailResult(
                is_valid=False,
                reason=f"Message contains prohibited clinical or prescription language: '{clinical_match.group(0)}'",
            )

        # 5. Date and numeric claims check
        if not allow_numbers:
            date_num_match = self.DATE_AND_NUMERIC_PATTERNS.search(trimmed)
            if date_num_match:
                return GuardrailResult(
                    is_valid=False,
                    reason=f"Message contains unsupported date or numeric claim: '{date_num_match.group(0)}'",
                )

        return GuardrailResult(is_valid=True)

    def get_validation_breakdown(
        self,
        message: Optional[str],
        expected_name: Optional[str] = None,
        allow_numbers: bool = False,
    ) -> list[dict]:
        """Return itemized audit of each individual guardrail rule for UI display."""
        if not message:
            return [
                {"id": "length", "label": "Length Bounds (15–350 chars)", "passed": False, "detail": "Message is empty"},
                {"id": "greeting", "label": "Personalized Greeting", "passed": False, "detail": "Missing greeting"},
                {"id": "clinical", "label": "Non-Prescriptive Language", "passed": True, "detail": "No clinical claims"},
                {"id": "dates", "label": "Date & Time Consistency", "passed": True, "detail": "No hallucinated dates"},
                {"id": "leakage", "label": "Prompt & Injection Isolation", "passed": True, "detail": "No instruction leakage"},
            ]

        trimmed = message.strip()
        lower_msg = trimmed.lower()

        # 1. Length
        len_ok = self.MIN_LENGTH <= len(trimmed) <= self.MAX_LENGTH
        len_detail = (
            f"{len(trimmed)} chars (acceptable: {self.MIN_LENGTH}–{self.MAX_LENGTH})"
            if len_ok
            else f"Length {len(trimmed)} outside acceptable range ({self.MIN_LENGTH}–{self.MAX_LENGTH})"
        )

        # 2. Greeting
        has_name = False
        if expected_name and expected_name.strip():
            clean_name = expected_name.strip().lower()
            if clean_name != "there" and clean_name in lower_msg:
                has_name = True
        has_approved = any(g in lower_msg for g in self.APPROVED_GREETINGS)
        greet_ok = has_name or has_approved
        greet_detail = (
            "Addressed to patient"
            if has_name
            else ("Approved neutral greeting" if has_approved else "Missing patient name or greeting")
        )

        # 3. Clinical
        clin_match = self.CLINICAL_PATTERNS.search(trimmed)
        clin_ok = clin_match is None
        clin_detail = "Non-prescriptive, no medical advice" if clin_ok else f"Clinical term detected: '{clin_match.group(0)}'"

        # 4. Dates
        date_ok = True
        date_detail = "No hallucinated future dates/times"
        if not allow_numbers:
            date_match = self.DATE_AND_NUMERIC_PATTERNS.search(trimmed)
            date_ok = date_match is None
            if not date_ok:
                date_detail = f"Date/numeric claim detected: '{date_match.group(0)}'"

        # 5. Leakage
        leak_match = self.LEAKAGE_AND_INJECTION_PATTERNS.search(trimmed)
        leak_ok = leak_match is None
        leak_detail = "Zero instruction or PII leakage" if leak_ok else f"Detected pattern: '{leak_match.group(0)}'"

        return [
            {"id": "length", "label": "Length Bounds (15–350 chars)", "passed": len_ok, "detail": len_detail},
            {"id": "greeting", "label": "Personalized Greeting", "passed": greet_ok, "detail": greet_detail},
            {"id": "clinical", "label": "Non-Prescriptive Language", "passed": clin_ok, "detail": clin_detail},
            {"id": "dates", "label": "Date & Time Consistency", "passed": date_ok, "detail": date_detail},
            {"id": "leakage", "label": "Prompt & Injection Isolation", "passed": leak_ok, "detail": leak_detail},
        ]
