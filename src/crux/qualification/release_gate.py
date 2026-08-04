from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from crux.config import ReleaseGateConfig
from crux.qualification.compare import MatchedComparison


class GateDecision(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class GateReason(StrEnum):
    STANDARD_REGRESSION_EXCEEDED = "STANDARD_REGRESSION_EXCEEDED"
    ADDITIONAL_STANDARD_FAILURES_EXCEEDED = "ADDITIONAL_STANDARD_FAILURES_EXCEEDED"
    NO_IMPROVEMENT_DEMONSTRATED = "NO_IMPROVEMENT_DEMONSTRATED"


@dataclass(frozen=True, slots=True)
class ReleaseGateResult:
    decision: GateDecision
    reason_codes: tuple[GateReason, ...]
    standard_regression_pp: float
    additional_standard_failures: int
    generalization_improvement_pp: float
    small_sample_rule_applied: bool

    @property
    def approved(self) -> bool:
        return self.decision is GateDecision.APPROVED


def evaluate_release_gate(
    standard: MatchedComparison,
    generalization: MatchedComparison,
    config: ReleaseGateConfig,
) -> ReleaseGateResult:
    regression_pp = standard.regression_percentage_points
    additional_failures = standard.baseline_only - standard.repaired_only
    small_sample = standard.pairs <= config.small_sample_episodes
    improvement_pp = generalization.delta_percentage_points

    reasons: list[GateReason] = []
    if small_sample:
        if additional_failures > config.max_additional_failures:
            reasons.append(GateReason.ADDITIONAL_STANDARD_FAILURES_EXCEEDED)
    elif regression_pp > config.max_regression_pp:
        reasons.append(GateReason.STANDARD_REGRESSION_EXCEEDED)
    if config.require_improvement and improvement_pp <= 0.0:
        reasons.append(GateReason.NO_IMPROVEMENT_DEMONSTRATED)

    return ReleaseGateResult(
        decision=GateDecision.REJECTED if reasons else GateDecision.APPROVED,
        reason_codes=tuple(reasons),
        standard_regression_pp=regression_pp,
        additional_standard_failures=additional_failures,
        generalization_improvement_pp=improvement_pp,
        small_sample_rule_applied=small_sample,
    )
