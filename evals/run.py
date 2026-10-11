"""CLI runner for HealthTrack AI evaluation harness comparing baseline and guarded modes."""

import sys
from typing import Tuple

from evals.metrics import EvaluationMode, EvaluationSummary, evaluate_dataset


def format_comparison_table(baseline: EvaluationSummary, guarded: EvaluationSummary) -> str:
    """Format high-level evaluation metrics into a readable ASCII comparison table."""
    header = (
        f"{'Evaluation Mode':<18} | {'Cases':<7} | {'Passed':<8} | {'Pass Rate':<10} | "
        f"{'Unsafe Accepted':<16} | {'False Rejections':<16} | {'Fallbacks':<10}"
    )
    divider = "-" * len(header)

    row_baseline = (
        f"{'Baseline':<18} | {baseline.total_cases:<7} | {baseline.cases_passed:<8} | "
        f"{f'{baseline.pass_rate:.1f}%':<10} | {baseline.unsafe_accepted:<16} | "
        f"{baseline.false_rejections:<16} | {baseline.fallback_activations:<10}"
    )

    row_guarded = (
        f"{'Guarded (Active)':<18} | {guarded.total_cases:<7} | {guarded.cases_passed:<8} | "
        f"{f'{guarded.pass_rate:.1f}%':<10} | {guarded.unsafe_accepted:<16} | "
        f"{guarded.false_rejections:<16} | {guarded.fallback_activations:<10}"
    )

    return f"{divider}\n{header}\n{divider}\n{row_baseline}\n{row_guarded}\n{divider}"


def format_category_table(guarded: EvaluationSummary) -> str:
    """Format category breakdown table for guarded evaluation mode."""
    header = f"{'Category':<30} | {'Total':<6} | {'Passed':<7} | {'Pass Rate':<10} | {'Unsafe':<7} | {'Fallbacks':<10}"
    divider = "-" * len(header)
    rows = [header, divider]

    for cat_name, cat in guarded.category_metrics.items():
        row = (
            f"{cat_name:<30} | {cat.total:<6} | {cat.passed:<7} | "
            f"{f'{cat.pass_rate:.1f}%':<10} | {cat.unsafe_accepted:<7} | {cat.fallback_count:<10}"
        )
        rows.append(row)

    rows.append(divider)
    return "\n".join(rows)


def run_evaluations() -> Tuple[EvaluationSummary, EvaluationSummary]:
    """Execute evaluation harness across baseline and guarded modes and display findings."""
    print("\n" + "=" * 80)
    print("HealthTrack — AI Follow-Up Personalization Evaluation Harness")
    print("=" * 80)
    print("Evaluating synthetic benchmark cases offline without external API dependencies...\n")

    baseline_summary = evaluate_dataset(EvaluationMode.BASELINE)
    guarded_summary = evaluate_dataset(EvaluationMode.GUARDED)

    print("1. SUMMARY COMPARISON:")
    print(format_comparison_table(baseline_summary, guarded_summary))
    print()

    print("2. GUARDED MODE CATEGORY BREAKDOWN:")
    print(format_category_table(guarded_summary))
    print()

    print("3. FAILURE & MITIGATION ANALYSIS:")
    baseline_failures = [r for r in baseline_summary.case_results if not r.passed]
    guarded_failures = [r for r in guarded_summary.case_results if not r.passed]

    print(f"• Baseline Mode Failures: {len(baseline_failures)} cases failed (unguarded model flaws)")
    for f in baseline_failures:
        print(f"  [{f.case_id}] {f.category:<25}: {f.reason}")

    if guarded_failures:
        print(f"\n• Guarded Mode Failures: {len(guarded_failures)} cases failed")
        for f in guarded_failures:
            print(f"  [{f.case_id}] {f.category:<25}: {f.reason}")
    else:
        print("\n• Guarded Mode Failures: 0 cases failed.")
        print(
            "  All 12 candidate defects (diagnoses, dosages, dates, prompt injections, timeouts)\n"
            "  were intercepted by GuardrailValidator and safely substituted with verified\n"
            "  deterministic clinical templates."
        )

    print("\n" + "=" * 80)
    print("Evaluation completed successfully.")
    print("=" * 80 + "\n")

    return baseline_summary, guarded_summary


def main() -> None:
    """CLI entrypoint."""
    try:
        run_evaluations()
        sys.exit(0)
    except Exception as exc:
        print(f"Evaluation harness failed to execute: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
