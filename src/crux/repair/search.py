from __future__ import annotations

from dataclasses import dataclass

from crux.failures.taxonomy import ReasonCode, TaskStage, stage_index


@dataclass(frozen=True, slots=True)
class Attempt:
    candidate_name: str
    reason_code: ReasonCode
    task_stage: TaskStage
    steps: int

    @property
    def succeeded(self) -> bool:
        return not self.reason_code.is_failure

    @property
    def score(self) -> tuple[int, int, int]:
        return (int(self.succeeded), stage_index(self.task_stage), -self.steps)


def best_of(attempts: tuple[Attempt, ...]) -> Attempt | None:
    if not attempts:
        return None
    return max(attempts, key=lambda attempt: attempt.score)


def advances(attempt: Attempt, current_stage: TaskStage) -> bool:
    if attempt.succeeded:
        return True
    return stage_index(attempt.task_stage) > stage_index(current_stage)
