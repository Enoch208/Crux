from __future__ import annotations

import pytest

from crux.failures.taxonomy import ReasonCode, TaskStage
from crux.simulation.determinism import (
    TrialSignature,
    max_deviation,
    outcomes_agree,
    signatures_agree,
    step_spread,
)


def signature(
    reason_code: ReasonCode = ReasonCode.CABLE_SLIP,
    task_stage: TaskStage = TaskStage.ROUTE_CLIP_1,
    steps: int = 1000,
) -> TrialSignature:
    return TrialSignature(reason_code=reason_code, task_stage=task_stage, steps=steps)


def test_max_deviation_is_zero_for_identical_rows() -> None:
    rows = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
    assert max_deviation(rows, rows) == 0.0


def test_max_deviation_finds_the_largest_component_gap() -> None:
    left = [[1.0, 2.0, 3.0]]
    right = [[1.0, 2.5, 2.9]]
    assert max_deviation(left, right) == pytest.approx(0.5)


def test_max_deviation_rejects_mismatched_shapes() -> None:
    with pytest.raises(ValueError):
        max_deviation([[1.0, 2.0]], [[1.0, 2.0], [3.0, 4.0]])


def test_signatures_agree_on_an_empty_or_single_trial() -> None:
    assert signatures_agree(())
    assert signatures_agree((signature(),))


def test_signatures_disagree_when_step_counts_differ() -> None:
    trials = (signature(steps=1000), signature(steps=1001))
    assert not signatures_agree(trials)
    assert outcomes_agree(trials)
    assert step_spread(trials) == 1


def test_outcomes_disagree_when_the_failure_changes() -> None:
    trials = (
        signature(reason_code=ReasonCode.CABLE_SLIP),
        signature(reason_code=ReasonCode.MISSED_GRASP),
    )
    assert not outcomes_agree(trials)


def test_step_spread_is_zero_without_trials() -> None:
    assert step_spread(()) == 0
