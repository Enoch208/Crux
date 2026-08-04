from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from crux.failures.taxonomy import FailureFamily, ReasonCode, TaskStage
from crux.qualification.suites import SuiteName
from crux.schema import Frozen


class CheckpointRef(Frozen):
    checkpoint_id: str
    task_stage: TaskStage
    simulation_step: int
    path: str


class EpisodeMetrics(Frozen):
    completion_steps: int = Field(ge=0)
    completion_seconds: float = Field(ge=0.0)
    max_cable_tension: float = Field(ge=0.0)
    max_collision_impulse: float = Field(ge=0.0)
    insertion_position_error_m: float | None = Field(default=None, ge=0.0)
    insertion_orientation_error_rad: float | None = Field(default=None, ge=0.0)


class EpisodeRecord(Frozen):
    run_id: str
    episode_id: str
    seed: int
    controller_version: str
    suite: SuiteName
    reason_code: ReasonCode
    task_stage: TaskStage
    simulation_step: int = Field(ge=0)
    timestamp: datetime
    environment_parameters: dict[str, float]
    metrics: EpisodeMetrics
    secondary_tags: tuple[str, ...] = ()
    replay_path: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.reason_code is ReasonCode.SUCCESS

    @property
    def family(self) -> FailureFamily | None:
        if self.succeeded:
            return None
        return FailureFamily(self.reason_code, self.task_stage)


class FailureEvent(Frozen):
    run_id: str
    episode_id: str
    seed: int
    controller_version: str
    reason_code: ReasonCode
    task_stage: TaskStage
    simulation_step: int = Field(ge=0)
    timestamp: datetime
    environment_parameters: dict[str, float]
    robot_state: tuple[float, ...]
    cable_state: tuple[float, ...]
    last_safe_checkpoint: CheckpointRef | None
    risk_metrics: dict[str, float]
    replay_path: str | None = None

    @field_validator("reason_code")
    @classmethod
    def reject_success(cls, value: ReasonCode) -> ReasonCode:
        if not value.is_failure:
            raise ValueError("FailureEvent requires a failure reason code, not SUCCESS")
        return value

    @property
    def family(self) -> FailureFamily:
        return FailureFamily(self.reason_code, self.task_stage)
