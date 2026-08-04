from __future__ import annotations

from dataclasses import dataclass

from crux.failures.taxonomy import ReasonCode, TaskStage

Vector = tuple[float, float, float]
Quaternion = tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class Observation:
    cable_rows: tuple[Vector, ...]
    hand_pos: Vector
    pinch_gap_m: float
    cable_contact_n: float
    arm_contact_n: float
    held_link_contact_n: float
    steps_taken: int
    cable_is_finite: bool


@dataclass(frozen=True, slots=True)
class Reach:
    """Drive the tool to a Cartesian pose for one control chunk."""

    pos: Vector
    quat: Quaternion
    finger_force: float


@dataclass(frozen=True, slots=True)
class Settle:
    """Hold the current joint targets for one control chunk."""

    finger_force: float


@dataclass(frozen=True, slots=True)
class Finish:
    reason_code: ReasonCode
    task_stage: TaskStage
    notes: tuple[str, ...]
    seat_lateral_m: float | None = None
    seat_depth_m: float | None = None

    @property
    def succeeded(self) -> bool:
        return not self.reason_code.is_failure


Directive = Reach | Settle | Finish
