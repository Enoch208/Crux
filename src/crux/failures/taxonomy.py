from __future__ import annotations

from enum import StrEnum
from typing import NamedTuple


class TaskStage(StrEnum):
    OBSERVE = "OBSERVE"
    APPROACH_CABLE = "APPROACH_CABLE"
    CLOSE_GRIPPER = "CLOSE_GRIPPER"
    VERIFY_GRASP = "VERIFY_GRASP"
    ROUTE_CLIP_1 = "ROUTE_CLIP_1"
    VERIFY_CLIP_1 = "VERIFY_CLIP_1"
    ROUTE_CLIP_2 = "ROUTE_CLIP_2"
    VERIFY_CLIP_2 = "VERIFY_CLIP_2"
    ALIGN_CONNECTOR = "ALIGN_CONNECTOR"
    INSERT_CONNECTOR = "INSERT_CONNECTOR"
    VERIFY_SEATED = "VERIFY_SEATED"


STAGE_ORDER: tuple[TaskStage, ...] = (
    TaskStage.OBSERVE,
    TaskStage.APPROACH_CABLE,
    TaskStage.CLOSE_GRIPPER,
    TaskStage.VERIFY_GRASP,
    TaskStage.ROUTE_CLIP_1,
    TaskStage.VERIFY_CLIP_1,
    TaskStage.ROUTE_CLIP_2,
    TaskStage.VERIFY_CLIP_2,
    TaskStage.ALIGN_CONNECTOR,
    TaskStage.INSERT_CONNECTOR,
    TaskStage.VERIFY_SEATED,
)


def stage_index(stage: TaskStage) -> int:
    return STAGE_ORDER.index(stage)


def stage_progress(stage: TaskStage) -> float:
    return stage_index(stage) / (len(STAGE_ORDER) - 1)


class ReasonCode(StrEnum):
    MISSED_GRASP = "MISSED_GRASP"
    CABLE_SLIP = "CABLE_SLIP"
    CLIP_1_MISSED = "CLIP_1_MISSED"
    CLIP_2_MISSED = "CLIP_2_MISSED"
    CABLE_SNAG = "CABLE_SNAG"
    OVER_TENSION = "OVER_TENSION"
    ROBOT_COLLISION = "ROBOT_COLLISION"
    CONNECTOR_MISALIGNED = "CONNECTOR_MISALIGNED"
    INCOMPLETE_INSERTION = "INCOMPLETE_INSERTION"
    TIMEOUT = "TIMEOUT"
    UNSTABLE_SIMULATION = "UNSTABLE_SIMULATION"
    SUCCESS = "SUCCESS"

    @property
    def is_failure(self) -> bool:
        return self is not ReasonCode.SUCCESS


FAILURE_CODES: tuple[ReasonCode, ...] = tuple(c for c in ReasonCode if c.is_failure)


class FailureFamily(NamedTuple):
    reason_code: ReasonCode
    task_stage: TaskStage

    @property
    def key(self) -> str:
        return f"{self.reason_code}@{self.task_stage}"

    @classmethod
    def parse(cls, key: str) -> FailureFamily:
        reason, _, stage = key.partition("@")
        return cls(ReasonCode(reason), TaskStage(stage))
