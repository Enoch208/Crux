from __future__ import annotations

from crux.config import ReleaseGateConfig
from crux.qualification.compare import MatchedComparison
from crux.qualification.release_gate import GateDecision, GateReason, evaluate_release_gate
from crux.qualification.suites import SuiteName

LARGE_SAMPLE_GATE = ReleaseGateConfig(
    max_regression_pp=2.0,
    max_additional_failures=1,
    small_sample_episodes=0,
    require_improvement=True,
)

SMALL_SAMPLE_GATE = ReleaseGateConfig(
    max_regression_pp=2.0,
    max_additional_failures=1,
    small_sample_episodes=60,
    require_improvement=True,
)


def comparison(
    both_succeed: int,
    baseline_only: int,
    repaired_only: int,
    both_fail: int,
    suite: SuiteName = SuiteName.STANDARD,
) -> MatchedComparison:
    return MatchedComparison(
        suite=suite,
        baseline_version="baseline-v1",
        repaired_version="repair-v1",
        both_succeed=both_succeed,
        baseline_only=baseline_only,
        repaired_only=repaired_only,
        both_fail=both_fail,
    )


IMPROVED_HELDOUT = comparison(40, 0, 20, 40, suite=SuiteName.HELDOUT)


def test_gate_approves_when_standard_holds_and_heldout_improves() -> None:
    standard = comparison(190, 1, 1, 8)
    result = evaluate_release_gate(standard, IMPROVED_HELDOUT, LARGE_SAMPLE_GATE)
    assert result.decision is GateDecision.APPROVED
    assert result.reason_codes == ()
    assert result.approved


def test_gate_rejects_when_standard_regression_exceeds_tolerance() -> None:
    standard = comparison(180, 10, 2, 8)
    result = evaluate_release_gate(standard, IMPROVED_HELDOUT, LARGE_SAMPLE_GATE)
    assert result.decision is GateDecision.REJECTED
    assert GateReason.STANDARD_REGRESSION_EXCEEDED in result.reason_codes
    assert result.standard_regression_pp == 4.0


def test_gate_tolerates_regression_at_exactly_the_threshold() -> None:
    standard = comparison(180, 6, 2, 12)
    result = evaluate_release_gate(standard, IMPROVED_HELDOUT, LARGE_SAMPLE_GATE)
    assert result.standard_regression_pp == 2.0
    assert result.decision is GateDecision.APPROVED


def test_small_sample_uses_the_additional_failure_rule() -> None:
    standard = comparison(50, 3, 1, 6)
    result = evaluate_release_gate(standard, IMPROVED_HELDOUT, SMALL_SAMPLE_GATE)
    assert result.small_sample_rule_applied
    assert result.additional_standard_failures == 2
    assert GateReason.ADDITIONAL_STANDARD_FAILURES_EXCEEDED in result.reason_codes


def test_small_sample_allows_one_additional_failure() -> None:
    standard = comparison(50, 2, 1, 7)
    result = evaluate_release_gate(standard, IMPROVED_HELDOUT, SMALL_SAMPLE_GATE)
    assert result.additional_standard_failures == 1
    assert result.decision is GateDecision.APPROVED


def test_gate_rejects_a_repair_that_does_not_generalize() -> None:
    standard = comparison(190, 1, 1, 8)
    flat_heldout = comparison(40, 10, 10, 40, suite=SuiteName.HELDOUT)
    result = evaluate_release_gate(standard, flat_heldout, LARGE_SAMPLE_GATE)
    assert result.decision is GateDecision.REJECTED
    assert result.reason_codes == (GateReason.NO_IMPROVEMENT_DEMONSTRATED,)


def test_gate_can_reject_for_several_reasons_at_once() -> None:
    standard = comparison(180, 10, 2, 8)
    flat_heldout = comparison(40, 10, 10, 40, suite=SuiteName.HELDOUT)
    result = evaluate_release_gate(standard, flat_heldout, LARGE_SAMPLE_GATE)
    assert set(result.reason_codes) == {
        GateReason.STANDARD_REGRESSION_EXCEEDED,
        GateReason.NO_IMPROVEMENT_DEMONSTRATED,
    }
