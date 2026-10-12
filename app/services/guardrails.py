"""Output guardrail validation for follow-up reminders.

Ensures generated messages strictly adhere to clinical safety, privacy,
length bounds, and injection-prevention criteria before persistence.
"""

from dataclasses import dataclass
from datetime import datetime
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
        "hello,",
        "hello!",
        "hi,",
        "hi!",
        "good morning,",
        "good afternoon,",
        "good day,",
        "greetings,",
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

    # Terminal punctuation check for complete sentences
    TERMINAL_PUNCTUATION_PATTERN = re.compile(r"[.!?][)\"']?$", re.DOTALL)

    # Dangling trailing connectors / prepositions indicating truncated sentence
    DANGLING_CONNECTOR_PATTERN = re.compile(
        r"\b(?:and|or|but|if|with|to|for|at|by|from|in|on|the|a|an|of|please|contact|reach)\s*[.!?][)\"']?$",
        re.IGNORECASE,
    )

    # Trailing ellipsis or truncated ellipsis markers
    TRAILING_ELLIPSIS_PATTERN = re.compile(r"(?:\.\.\.|…)\s*[)\"']?$", re.IGNORECASE)

    # Relevance keywords indicating clinical encounter or healthcare context
    RELEVANCE_PATTERN = re.compile(
        r"\b("
        r"appointment|visit|checkup|check-up|consultation|physical|"
        r"examination|care|clinic|practice|office|doctor|physician|"
        r"team|wellness|health|healthcare|follow-up|followup|encounter"
        r")\b",
        re.IGNORECASE,
    )

    # Unsupported URLs or web links
    URL_PATTERN = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)

    def _is_modal_may(self, text: str, match_start: int, match_end: int) -> bool:
        """Check if 'may' at the given span is used as a modal auxiliary verb rather than calendar month May."""
        prefix = text[max(0, match_start - 35):match_start].lower()
        suffix = text[match_end:min(len(text), match_end + 35)].lower()

        preceding_modal = bool(
            re.search(r"\b(?:you|we|they|questions?\s+(?:that\s+)?you|patient|anyone)\s*$", prefix)
        )
        following_verb = bool(
            re.search(r"^\s*(?:contact|reach|call|have|need|wish|want|ask|be|feel|schedule|require|experience)\b", suffix)
        )
        return preceding_modal or following_verb

    def _check_structural_completeness(self, trimmed: str) -> tuple[bool, str]:
        """Check for abruptly truncated messages, incomplete final sentences, and unclosed delimiters."""
        if not trimmed:
            return False, "Message is empty"

        # Trailing ellipsis check
        if self.TRAILING_ELLIPSIS_PATTERN.search(trimmed):
            return False, "Message appears truncated with trailing ellipsis"

        # Dangling connector check
        dang_match = self.DANGLING_CONNECTOR_PATTERN.search(trimmed)
        if dang_match:
            return False, f"Message appears truncated with trailing connector: '{dang_match.group(0).strip()}'"

        # Terminal sentence punctuation check
        if not self.TERMINAL_PUNCTUATION_PATTERN.search(trimmed):
            return False, "Message ends abruptly without terminal punctuation (incomplete final sentence)"

        # Balanced paired delimiters check
        if trimmed.count('"') % 2 != 0:
            return False, "Message contains unclosed quotation mark"
        if trimmed.count("“") != trimmed.count("”"):
            return False, "Message contains unclosed curly quotation mark"
        if trimmed.count("(") != trimmed.count(")"):
            return False, "Message contains unclosed parenthesis"
        if trimmed.count("[") != trimmed.count("]"):
            return False, "Message contains unclosed bracket"

        return True, "Complete sentence structure with terminal punctuation"

    def _check_contextual_relevance(self, trimmed: str) -> tuple[bool, str]:
        """Check for clinical encounter relevance and contextual substance."""
        if not trimmed:
            return False, "Message is empty"

        rel_match = self.RELEVANCE_PATTERN.search(trimmed)
        if not rel_match:
            return False, "Message lacks appointment, clinic, or healthcare follow-up context"

        return True, f"Relevant encounter context verified ('{rel_match.group(0)}')"

    def _get_allowed_date_tokens(self, allowed_date: datetime) -> Set[str]:
        """Extract valid date and numeric tokens from a verified appointment datetime."""
        tokens: Set[str] = set()
        month_name = allowed_date.strftime("%B").lower()
        month_abbr = allowed_date.strftime("%b").lower()
        tokens.add(month_name)
        tokens.add(month_abbr)

        day_str = str(allowed_date.day)
        tokens.add(day_str)
        tokens.add(f"{allowed_date.day:02d}")
        if allowed_date.day in (1, 21, 31):
            tokens.add(f"{day_str}st")
        elif allowed_date.day in (2, 22):
            tokens.add(f"{day_str}nd")
        elif allowed_date.day in (3, 23):
            tokens.add(f"{day_str}rd")
        else:
            tokens.add(f"{day_str}th")

        year_str = str(allowed_date.year)
        tokens.add(year_str)
        tokens.add(year_str[-2:])

        tokens.add(f"{allowed_date.month}/{allowed_date.day}")
        tokens.add(f"{allowed_date.month}/{allowed_date.day}/{year_str}")
        tokens.add(f"{allowed_date.month}/{allowed_date.day}/{year_str[-2:]}")
        tokens.add(f"{allowed_date.year}-{allowed_date.month:02d}-{allowed_date.day:02d}")

        tokens.add(allowed_date.strftime("%A").lower())
        tokens.add(allowed_date.strftime("%a").lower())
        return tokens

    def _find_unsupported_date_or_numeric_match(
        self,
        trimmed: str,
        allowed_date: Optional[datetime] = None,
        allowed_tokens: Optional[Set[str]] = None,
    ) -> Optional[re.Match]:
        """Find the first unsupported date, time, currency, or numeric match, if any."""
        allowed_tokens_set: Set[str] = set()
        if allowed_date:
            allowed_tokens_set.update(self._get_allowed_date_tokens(allowed_date))
        if allowed_tokens:
            allowed_tokens_set.update(t.lower() for t in allowed_tokens)

        for match in self.DATE_AND_NUMERIC_PATTERNS.finditer(trimmed):
            token = match.group(0).lower().strip()

            # Handle modal 'may'
            if token == "may" and self._is_modal_may(trimmed, match.start(), match.end()):
                continue

            # Check if token matches verified date or allowed token
            if token in allowed_tokens_set:
                continue

            # Check if alphanumeric-only version matches
            clean_token = re.sub(r"[^\w]", "", token)
            if clean_token and clean_token in allowed_tokens_set:
                continue

            return match
        return None

    def validate(
        self,
        message: Optional[str],
        expected_name: Optional[str] = None,
        allow_numbers: bool = False,
        allowed_date: Optional[datetime] = None,
        allowed_tokens: Optional[Set[str]] = None,
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

        # 5. Unsupported URL or contact link check
        url_match = self.URL_PATTERN.search(trimmed)
        if url_match:
            url_token = url_match.group(0)
            if not (allowed_tokens and url_token.lower() in [t.lower() for t in allowed_tokens]):
                return GuardrailResult(
                    is_valid=False,
                    reason=f"Message contains unsupported URL or web link: '{url_token}'",
                )

        # 6. Date and numeric claims check
        if not allow_numbers:
            unsupported_match = self._find_unsupported_date_or_numeric_match(
                trimmed, allowed_date=allowed_date, allowed_tokens=allowed_tokens
            )
            if unsupported_match:
                return GuardrailResult(
                    is_valid=False,
                    reason=f"Message contains unsupported date or numeric claim: '{unsupported_match.group(0)}'",
                )

        # 7. Sentence & structural completeness check
        complete_ok, complete_reason = self._check_structural_completeness(trimmed)
        if not complete_ok:
            return GuardrailResult(is_valid=False, reason=complete_reason)

        # 8. Contextual relevance check
        rel_ok, rel_reason = self._check_contextual_relevance(trimmed)
        if not rel_ok:
            return GuardrailResult(is_valid=False, reason=rel_reason)

        return GuardrailResult(is_valid=True)

    def get_validation_breakdown(
        self,
        message: Optional[str],
        expected_name: Optional[str] = None,
        allow_numbers: bool = False,
        allowed_date: Optional[datetime] = None,
        allowed_tokens: Optional[Set[str]] = None,
    ) -> list[dict]:
        """Return itemized audit of each individual guardrail rule for UI display."""
        if not message:
            return [
                {"id": "length", "label": "Length Bounds (15–350 chars)", "passed": False, "detail": "Message is empty"},
                {"id": "greeting", "label": "Personalized Greeting", "passed": False, "detail": "Missing greeting"},
                {"id": "completeness", "label": "Sentence & Structural Completeness", "passed": False, "detail": "Message is empty"},
                {"id": "relevance", "label": "Clinical Encounter Relevance", "passed": False, "detail": "Message is empty"},
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

        # 3. Completeness
        complete_ok, complete_reason = self._check_structural_completeness(trimmed)
        complete_detail = "Complete sentence structure with terminal punctuation" if complete_ok else complete_reason

        # 4. Relevance
        rel_ok, rel_reason = self._check_contextual_relevance(trimmed)
        rel_detail = rel_reason

        # 5. Clinical
        clin_match = self.CLINICAL_PATTERNS.search(trimmed)
        clin_ok = clin_match is None
        clin_detail = "Non-prescriptive, no medical advice" if clin_ok else f"Clinical term detected: '{clin_match.group(0)}'"

        # 6. Dates & URLs
        url_match = self.URL_PATTERN.search(trimmed)
        url_ok = True
        if url_match:
            url_token = url_match.group(0)
            url_ok = bool(allowed_tokens and url_token.lower() in [t.lower() for t in allowed_tokens])

        date_ok = True
        date_detail = "No hallucinated future dates/times"
        if not url_ok and url_match:
            date_ok = False
            date_detail = f"Unsupported URL detected: '{url_match.group(0)}'"
        elif not allow_numbers:
            unsupported_match = self._find_unsupported_date_or_numeric_match(
                trimmed, allowed_date=allowed_date, allowed_tokens=allowed_tokens
            )
            date_ok = unsupported_match is None
            if not date_ok:
                date_detail = f"Date/numeric claim detected: '{unsupported_match.group(0)}'"
            elif allowed_date:
                date_detail = "Verified encounter date reference"

        # 7. Leakage
        leak_match = self.LEAKAGE_AND_INJECTION_PATTERNS.search(trimmed)
        leak_ok = leak_match is None
        leak_detail = "Zero instruction or PII leakage" if leak_ok else f"Detected pattern: '{leak_match.group(0)}'"

        return [
            {"id": "length", "label": "Length Bounds (15–350 chars)", "passed": len_ok, "detail": len_detail},
            {"id": "greeting", "label": "Personalized Greeting", "passed": greet_ok, "detail": greet_detail},
            {"id": "completeness", "label": "Sentence & Structural Completeness", "passed": complete_ok, "detail": complete_detail},
            {"id": "relevance", "label": "Clinical Encounter Relevance", "passed": rel_ok, "detail": rel_detail},
            {"id": "clinical", "label": "Non-Prescriptive Language", "passed": clin_ok, "detail": clin_detail},
            {"id": "dates", "label": "Date & Time Consistency", "passed": date_ok, "detail": date_detail},
            {"id": "leakage", "label": "Prompt & Injection Isolation", "passed": leak_ok, "detail": leak_detail},
        ]
