from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from crux.failures.taxonomy import ReasonCode, TaskStage

Samples = Sequence[Sequence[float]]


def max_deviation(left: Samples, right: Samples) -> float:
    return max(
        abs(a - b)
        for left_row, right_row in zip(left, right, strict=True)
        for a, b in zip(left_row, right_row, strict=True)
    )


@dataclass(frozen=True, slots=True)
class TrialSignature:
    reason_code: ReasonCode
    task_stage: TaskStage
    steps: int


def signatures_agree(signatures: tuple[TrialSignature, ...]) -> bool:
    return len(set(signatures)) <= 1


def outcomes_agree(signatures: tuple[TrialSignature, ...]) -> bool:
    return len({(s.reason_code, s.task_stage) for s in signatures}) <= 1


def step_spread(signatures: tuple[TrialSignature, ...]) -> int:
    if not signatures:
        return 0
    steps = [s.steps for s in signatures]
    return max(steps) - min(steps)
