"""Metrics computation and evaluation execution for HealthTrack AI personalization."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from app.models.appointment import Appointment, AppointmentType
from app.models.patient import Patient
from app.services.ai_personalizer import sanitize_input_value
from app.services.guardrails import GuardrailValidator
from app.services.personalizer import TemplateMessagePersonalizer
from evals.dataset import BenchmarkCase, get_benchmark_dataset


class EvaluationMode(str, Enum):
    """Execution mode for the evaluation harness."""

    BASELINE = "baseline"
    GUARDED = "guarded"


@dataclass(frozen=True)
class CaseResult:
    """Outcome for an individual benchmark test case."""

    case_id: str
    category: str
    description: str
    passed: bool
    candidate_valid: bool
    is_safe_ground_truth: bool
    fallback_used: bool
    unsafe_accepted: bool
    false_rejection: bool
    final_message: str
    reason: Optional[str] = None


@dataclass(frozen=True)
class CategorySummary:
    """Aggregate evaluation metrics for a specific benchmark category."""

    category: str
    total: int
    passed: int
    pass_rate: float
    unsafe_accepted: int
    fallback_count: int


@dataclass(frozen=True)
class EvaluationSummary:
    """Complete summary of a benchmark evaluation run."""

    mode: EvaluationMode
    total_cases: int
    cases_passed: int
    pass_rate: float
    valid_candidates: int
    rejected_candidates: int
    fallback_activations: int
    unsafe_accepted: int
    false_rejections: int
    category_metrics: Dict[str, CategorySummary]
    case_results: List[CaseResult] = field(default_factory=list)


def evaluate_case_baseline(case: BenchmarkCase) -> CaseResult:
    """Evaluate a benchmark case in baseline (unguarded) mode without safety filtering."""
    # In baseline mode, provider failure or empty output fails without fallback
    if case.should_timeout or case.simulated_error or not case.candidate_output:
        return CaseResult(
            case_id=case.case_id,
            category=case.category,
            description=case.description,
            passed=False,
            candidate_valid=False,
            is_safe_ground_truth=case.is_safe,
            fallback_used=False,
            unsafe_accepted=False,
            false_rejection=False,
            final_message="",
            reason="Simulated provider failure or empty output (no baseline fallback)",
        )

    candidate = case.candidate_output.strip()

    # Unguarded acceptance: if ground truth is safe, passes; if ground truth is unsafe, fails
    if case.is_safe:
        return CaseResult(
            case_id=case.case_id,
            category=case.category,
            description=case.description,
            passed=True,
            candidate_valid=True,
            is_safe_ground_truth=True,
            fallback_used=False,
            unsafe_accepted=False,
            false_rejection=False,
            final_message=candidate,
            reason="Safe candidate accepted by baseline",
        )
    else:
        return CaseResult(
            case_id=case.case_id,
            category=case.category,
            description=case.description,
            passed=False,
            candidate_valid=True,
            is_safe_ground_truth=False,
            fallback_used=False,
            unsafe_accepted=True,
            false_rejection=False,
            final_message=candidate,
            reason="Unsafe output accepted without guardrail inspection (baseline defect)",
        )


def evaluate_case_guarded(
    case: BenchmarkCase,
    validator: GuardrailValidator,
    fallback_personalizer: TemplateMessagePersonalizer,
) -> CaseResult:
    """Evaluate a benchmark case in guarded mode using GuardrailValidator and fallback."""
    clean_name = sanitize_input_value(case.patient_first_name) or "there"

    # Create synthetic encounter for deterministic fallback generation
    patient = Patient(
        id=900,
        first_name=case.patient_first_name,
        last_name="EvaluationSubject",
        email="eval.subject@example.com",
    )
    # Parse appointment type
    try:
        apt_type = AppointmentType(case.appointment_type)
    except ValueError:
        apt_type = AppointmentType.ROUTINE_CHECKUP

    appointment = Appointment(
        id=901,
        patient_id=patient.id,
        appointment_type=apt_type,
        appointment_datetime=datetime(2026, 10, 10, 10, 0, tzinfo=timezone.utc),
    )
    appointment.patient = patient

    # Case 1: Provider timeout, simulated error, or missing candidate
    if case.should_timeout or case.simulated_error or case.candidate_output is None:
        fallback_msg = fallback_personalizer.personalize_reminder(appointment)
        val_fb = validator.validate(fallback_msg, expected_name=clean_name)
        if val_fb.is_valid:
            return CaseResult(
                case_id=case.case_id,
                category=case.category,
                description=case.description,
                passed=True,
                candidate_valid=False,
                is_safe_ground_truth=case.is_safe,
                fallback_used=True,
                unsafe_accepted=False,
                false_rejection=False,
                final_message=fallback_msg,
                reason="Recovered from provider failure via validated template fallback",
            )
        else:
            return CaseResult(
                case_id=case.case_id,
                category=case.category,
                description=case.description,
                passed=False,
                candidate_valid=False,
                is_safe_ground_truth=case.is_safe,
                fallback_used=True,
                unsafe_accepted=False,
                false_rejection=False,
                final_message=fallback_msg,
                reason=f"Provider failed and fallback failed validation: {val_fb.reason}",
            )

    # Case 2: Candidate text is provided
    candidate = case.candidate_output.strip()
    val_cand = validator.validate(candidate, expected_name=clean_name)

    if val_cand.is_valid:
        # Candidate passed guardrail
        if case.is_safe:
            return CaseResult(
                case_id=case.case_id,
                category=case.category,
                description=case.description,
                passed=True,
                candidate_valid=True,
                is_safe_ground_truth=True,
                fallback_used=False,
                unsafe_accepted=False,
                false_rejection=False,
                final_message=candidate,
                reason="Valid compliant candidate accepted",
            )
        else:
            # Unsafe candidate slipped past guardrail (Unsafe Accepted / False Negative)
            return CaseResult(
                case_id=case.case_id,
                category=case.category,
                description=case.description,
                passed=False,
                candidate_valid=True,
                is_safe_ground_truth=False,
                fallback_used=False,
                unsafe_accepted=True,
                false_rejection=False,
                final_message=candidate,
                reason="Unsafe candidate slipped past guardrail",
            )
    else:
        # Candidate rejected by guardrail!
        false_rejection = bool(case.is_safe)
        fallback_msg = fallback_personalizer.personalize_reminder(appointment)
        val_fb = validator.validate(fallback_msg, expected_name=clean_name)

        if val_fb.is_valid:
            # Successfully mitigated via fallback
            return CaseResult(
                case_id=case.case_id,
                category=case.category,
                description=case.description,
                passed=True,
                candidate_valid=False,
                is_safe_ground_truth=case.is_safe,
                fallback_used=True,
                unsafe_accepted=False,
                false_rejection=false_rejection,
                final_message=fallback_msg,
                reason=f"Rejected candidate ({val_cand.reason}) -> replaced with safe fallback",
            )
        else:
            return CaseResult(
                case_id=case.case_id,
                category=case.category,
                description=case.description,
                passed=False,
                candidate_valid=False,
                is_safe_ground_truth=case.is_safe,
                fallback_used=True,
                unsafe_accepted=False,
                false_rejection=false_rejection,
                final_message=fallback_msg,
                reason="Rejected candidate and fallback template also failed validation",
            )


def evaluate_dataset(
    mode: EvaluationMode,
    dataset: Optional[List[BenchmarkCase]] = None,
) -> EvaluationSummary:
    """Execute evaluation for all benchmark cases under the selected mode."""
    cases = dataset or get_benchmark_dataset()
    validator = GuardrailValidator()
    fallback_personalizer = TemplateMessagePersonalizer()

    results: List[CaseResult] = []
    for case in cases:
        if mode == EvaluationMode.BASELINE:
            res = evaluate_case_baseline(case)
        else:
            res = evaluate_case_guarded(case, validator, fallback_personalizer)
        results.append(res)

    total_cases = len(results)
    cases_passed = sum(1 for r in results if r.passed)
    pass_rate = round((cases_passed / total_cases * 100.0), 1) if total_cases > 0 else 0.0

    valid_candidates = sum(1 for r in results if r.candidate_valid)
    rejected_candidates = total_cases - valid_candidates
    fallback_activations = sum(1 for r in results if r.fallback_used)
    unsafe_accepted = sum(1 for r in results if r.unsafe_accepted)
    false_rejections = sum(1 for r in results if r.false_rejection)

    # Calculate per-category metrics
    category_groups: Dict[str, List[CaseResult]] = {}
    for r in results:
        category_groups.setdefault(r.category, []).append(r)

    category_summaries: Dict[str, CategorySummary] = {}
    for cat, group in sorted(category_groups.items()):
        cat_total = len(group)
        cat_passed = sum(1 for r in group if r.passed)
        cat_rate = round((cat_passed / cat_total * 100.0), 1) if cat_total > 0 else 0.0
        cat_unsafe = sum(1 for r in group if r.unsafe_accepted)
        cat_fallbacks = sum(1 for r in group if r.fallback_used)
        category_summaries[cat] = CategorySummary(
            category=cat,
            total=cat_total,
            passed=cat_passed,
            pass_rate=cat_rate,
            unsafe_accepted=cat_unsafe,
            fallback_count=cat_fallbacks,
        )

    return EvaluationSummary(
        mode=mode,
        total_cases=total_cases,
        cases_passed=cases_passed,
        pass_rate=pass_rate,
        valid_candidates=valid_candidates,
        rejected_candidates=rejected_candidates,
        fallback_activations=fallback_activations,
        unsafe_accepted=unsafe_accepted,
        false_rejections=false_rejections,
        category_metrics=category_summaries,
        case_results=results,
    )
