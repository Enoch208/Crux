from __future__ import annotations

from dataclasses import dataclass

from crux.failures.taxonomy import ReasonCode, TaskStage, stage_index

SEAT_MISSING = 10**9


@dataclass(frozen=True, slots=True)
class Attempt:
    candidate_name: str
    reason_code: ReasonCode
    task_stage: TaskStage
    steps: int
    seat_lateral_m: float | None = None
    seat_depth_m: float | None = None

    @property
    def succeeded(self) -> bool:
        return not self.reason_code.is_failure

    @property
    def seat_cost(self) -> int:
        if self.succeeded:
            return 0
        if self.seat_lateral_m is None or self.seat_depth_m is None:
            return SEAT_MISSING
        return int(self.seat_lateral_m * 1000) + int(self.seat_depth_m * 1000)

    @property
    def score(self) -> tuple[int, int, int, int]:
        return (int(self.succeeded), stage_index(self.task_stage), -self.seat_cost, -self.steps)


def best_of(attempts: tuple[Attempt, ...]) -> Attempt | None:
    if not attempts:
        return None
    return max(attempts, key=lambda attempt: attempt.score)


def seating_improved(
    attempt: Attempt,
    current_lateral_m: float | None,
    current_depth_m: float | None,
) -> bool:
    if attempt.seat_lateral_m is None or attempt.seat_depth_m is None:
        return False
    if current_lateral_m is None or current_depth_m is None:
        return False
    before = current_lateral_m + current_depth_m
    after = attempt.seat_lateral_m + attempt.seat_depth_m
    return after < before - 1e-4


def advances(
    attempt: Attempt,
    current_stage: TaskStage,
    *,
    current_lateral_m: float | None = None,
    current_depth_m: float | None = None,
) -> bool:
    if attempt.succeeded:
        return True
    if stage_index(attempt.task_stage) > stage_index(current_stage):
        return True
    return (
        attempt.task_stage is TaskStage.VERIFY_SEATED
        and current_stage is TaskStage.VERIFY_SEATED
        and seating_improved(attempt, current_lateral_m, current_depth_m)
    )
