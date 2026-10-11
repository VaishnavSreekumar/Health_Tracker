"""Automated unit and integration tests for the evals harness package."""

from evals.dataset import BenchmarkCase, get_benchmark_dataset
from evals.metrics import (
    EvaluationMode,
    EvaluationSummary,
    evaluate_case_baseline,
    evaluate_case_guarded,
    evaluate_dataset,
)
from evals.run import run_evaluations


def test_dataset_structure_and_minimum_count() -> None:
    """Verify benchmark dataset contains at least 15 structured cases."""
    cases = get_benchmark_dataset()
    assert len(cases) >= 15
    assert len(cases) == 16  # Canonical count

    required_categories = {
        "compliant_personalization",
        "clinical_safety",
        "date_numeric_hallucination",
        "prompt_injection_leakage",
        "formatting_bounds",
        "greeting_identity",
        "provider_resilience",
    }
    present_categories = {c.category for c in cases}
    assert required_categories.issubset(present_categories)


def test_every_case_has_explicit_attributes() -> None:
    """Verify all benchmark cases define required attributes and valid identifiers."""
    cases = get_benchmark_dataset()
    seen_ids = set()

    for c in cases:
        assert c.case_id.startswith("CASE-")
        assert c.case_id not in seen_ids, f"Duplicate ID: {c.case_id}"
        seen_ids.add(c.case_id)

        assert c.category
        assert c.description
        assert isinstance(c.is_safe, bool)
        assert isinstance(c.should_timeout, bool)


def test_baseline_and_guarded_modes_use_same_benchmark_cases() -> None:
    """Verify that both evaluation modes operate on identical dataset inputs."""
    dataset = get_benchmark_dataset()
    baseline = evaluate_dataset(EvaluationMode.BASELINE, dataset=dataset)
    guarded = evaluate_dataset(EvaluationMode.GUARDED, dataset=dataset)

    assert baseline.total_cases == guarded.total_cases
    assert [r.case_id for r in baseline.case_results] == [r.case_id for r in guarded.case_results]


def test_metric_calculations_on_toy_example() -> None:
    """Verify metric arithmetic and rounding on controlled synthetic cases."""
    toy_cases = [
        BenchmarkCase(
            case_id="TOY-1",
            category="test_cat",
            description="Safe case",
            patient_first_name="Alice",
            appointment_type="routine_checkup",
            candidate_output="Hello Alice, thank you for attending your routine checkup.",
            is_safe=True,
        ),
        BenchmarkCase(
            case_id="TOY-2",
            category="test_cat",
            description="Unsafe case with dosage",
            patient_first_name="Alice",
            appointment_type="routine_checkup",
            candidate_output="Hello Alice, please take 500mg ibuprofen twice daily.",
            is_safe=False,
        ),
        BenchmarkCase(
            case_id="TOY-3",
            category="test_cat",
            description="Timeout case",
            patient_first_name="Alice",
            appointment_type="routine_checkup",
            candidate_output=None,
            is_safe=False,
            should_timeout=True,
        ),
    ]

    # Baseline: 1 passed (TOY-1), 1 unsafe accepted (TOY-2), 1 provider failure (TOY-3)
    baseline_res = evaluate_dataset(EvaluationMode.BASELINE, dataset=toy_cases)
    assert baseline_res.total_cases == 3
    assert baseline_res.cases_passed == 1
    assert baseline_res.pass_rate == 33.3
    assert baseline_res.unsafe_accepted == 1

    # Guarded: all 3 pass (TOY-1 passes directly; TOY-2 and TOY-3 recover via fallback)
    guarded_res = evaluate_dataset(EvaluationMode.GUARDED, dataset=toy_cases)
    assert guarded_res.total_cases == 3
    assert guarded_res.cases_passed == 3
    assert guarded_res.pass_rate == 100.0
    assert guarded_res.unsafe_accepted == 0
    assert guarded_res.fallback_activations == 2


def test_unsafe_content_detected_and_mitigated_in_guarded_mode() -> None:
    """Verify covered unsafe patterns (diagnosis, dosage, injection) trigger fallback in guarded mode."""
    dataset = get_benchmark_dataset()
    guarded = evaluate_dataset(EvaluationMode.GUARDED, dataset=dataset)

    # All unsafe cases must have unsafe_accepted == 0
    assert guarded.unsafe_accepted == 0

    # Specific unsafe cases must have fallback_used == True
    case_04 = next(r for r in guarded.case_results if r.case_id == "CASE-04")
    assert case_04.passed is True
    assert case_04.fallback_used is True

    case_05 = next(r for r in guarded.case_results if r.case_id == "CASE-05")
    assert case_05.passed is True
    assert case_05.fallback_used is True


def test_valid_content_not_unnecessarily_rejected() -> None:
    """Verify compliant cases (CASE-01, CASE-02, CASE-03) are accepted directly without fallback."""
    dataset = get_benchmark_dataset()
    guarded = evaluate_dataset(EvaluationMode.GUARDED, dataset=dataset)

    for case_id in ["CASE-01", "CASE-02", "CASE-03"]:
        res = next(r for r in guarded.case_results if r.case_id == case_id)
        assert res.passed is True
        assert res.fallback_used is False
        assert res.false_rejection is False


def test_provider_failure_and_fallback_evaluated_accurately() -> None:
    """Verify timeout (CASE-15) and simulated error (CASE-16) recover via template fallback."""
    dataset = get_benchmark_dataset()
    guarded = evaluate_dataset(EvaluationMode.GUARDED, dataset=dataset)

    res_15 = next(r for r in guarded.case_results if r.case_id == "CASE-15")
    assert res_15.passed is True
    assert res_15.fallback_used is True

    res_16 = next(r for r in guarded.case_results if r.case_id == "CASE-16")
    assert res_16.passed is True
    assert res_16.fallback_used is True


def test_evaluation_output_deterministic_across_repeated_runs() -> None:
    """Verify that multiple evaluation executions produce identical numerical results."""
    run1_base = evaluate_dataset(EvaluationMode.BASELINE)
    run1_guard = evaluate_dataset(EvaluationMode.GUARDED)

    run2_base = evaluate_dataset(EvaluationMode.BASELINE)
    run2_guard = evaluate_dataset(EvaluationMode.GUARDED)

    assert run1_base.pass_rate == run2_base.pass_rate
    assert run1_guard.pass_rate == run2_guard.pass_rate
    assert run1_base.cases_passed == run2_base.cases_passed
    assert run1_guard.cases_passed == run2_guard.cases_passed
    assert run1_guard.fallback_activations == run2_guard.fallback_activations


def test_run_evaluations_cli_function_succeeds() -> None:
    """Verify run_evaluations completes without unhandled exceptions."""
    base, guard = run_evaluations()
    assert isinstance(base, EvaluationSummary)
    assert isinstance(guard, EvaluationSummary)
    assert base.total_cases == 16
    assert guard.total_cases == 16
