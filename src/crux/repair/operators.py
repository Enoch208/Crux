from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crux.failures.taxonomy import FAILURE_CODES, ReasonCode, TaskStage
from crux.repair.knobs import ControllerKnobs


@dataclass(frozen=True, slots=True)
class RepairCandidate:
    name: str
    rationale: str
    overrides: tuple[tuple[str, float], ...]

    def apply(self, knobs: ControllerKnobs) -> ControllerKnobs:
        return knobs.with_overrides(dict(self.overrides))

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "rationale": self.rationale, **dict(self.overrides)}


SHORT_DANGLE_REGRASP = RepairCandidate(
    name="short-dangle-regrasp",
    rationale=(
        "hold one link from the connector before inserting so an alignment correction "
        "moves a 25 mm tail instead of dragging 75 mm of threaded cable"
    ),
    overrides=(("insert_link_from_end", 1),),
)
GENTLE_ALIGN = RepairCandidate(
    name="gentle-align",
    rationale="halve each alignment step and take more of them, spreading the load over time",
    overrides=(("align_step_cap_m", 0.012), ("align_corrections", 5)),
)
FIRMER_CARRY = RepairCandidate(
    name="firmer-carry",
    rationale="raise pinch force to resist contact creep under sustained load",
    overrides=(("close_force_n", -34.0),),
)
SLOWER_TRANSPORT = RepairCandidate(
    name="slower-transport",
    rationale="halve travel speed so the cable is dragged rather than jerked",
    overrides=(("drag_speed_mps", 0.03),),
)
LONGER_QUIET = RepairCandidate(
    name="longer-quiet",
    rationale="wait longer after release so the cable is fully at rest before regrasping",
    overrides=(("quiet_steps", 400),),
)
SHALLOWER_SETTLE = RepairCandidate(
    name="shallower-settle",
    rationale="stop the settling descent higher so the fingertips do not shove the strand aside",
    overrides=(("settle_tip_z_m", 0.030),),
)
DEEPER_SETTLE = RepairCandidate(
    name="deeper-settle",
    rationale="press the strand further into the gate before verifying the crossing",
    overrides=(("settle_tip_z_m", 0.012),),
)
LOWER_ROUTE = RepairCandidate(
    name="lower-route",
    rationale="carry the strand closer to the gate floor through the posts",
    overrides=(("route_z_m", 0.030),),
)
LONGER_PULL = RepairCandidate(
    name="longer-pull",
    rationale="pull further past the gate so the crossing clears the post plane",
    overrides=(("pull_past_m", 0.075),),
)
SHORTER_PULL = RepairCandidate(
    name="shorter-pull",
    rationale="pull less far past the gate so the cable is not stretched taut",
    overrides=(("pull_past_m", 0.040),),
)
DEEPER_INSERT = RepairCandidate(
    name="deeper-insert",
    rationale="lower the connector further into the socket before releasing",
    overrides=(("insert_z_m", 0.008),),
)
FEWER_CORRECTIONS = RepairCandidate(
    name="fewer-corrections",
    rationale="drop alignment retries to buy back step budget",
    overrides=(("align_corrections", 1),),
)
MORE_BUDGET = RepairCandidate(
    name="more-budget",
    rationale=(
        "raise the step ceiling so a late-stage insertion that already burned its "
        "routing budget can finish the seating descent"
    ),
    overrides=(("timeout_steps", 14000),),
)
FASTER_LATE_STAGE = RepairCandidate(
    name="faster-late-stage",
    rationale="raise travel speed so alignment and insertion consume fewer steps",
    overrides=(("drag_speed_mps", 0.09),),
)


_BY_STAGE: dict[tuple[ReasonCode, TaskStage], tuple[RepairCandidate, ...]] = {
    (ReasonCode.CABLE_SLIP, TaskStage.ALIGN_CONNECTOR): (
        SHORT_DANGLE_REGRASP,
        GENTLE_ALIGN,
        FIRMER_CARRY,
    ),
    (ReasonCode.CABLE_SLIP, TaskStage.INSERT_CONNECTOR): (
        SHORT_DANGLE_REGRASP,
        FIRMER_CARRY,
    ),
    (ReasonCode.MISSED_GRASP, TaskStage.VERIFY_CLIP_1): (
        LONGER_QUIET,
        SHALLOWER_SETTLE,
    ),
    (ReasonCode.MISSED_GRASP, TaskStage.VERIFY_CLIP_2): (
        LONGER_QUIET,
        SHALLOWER_SETTLE,
    ),
    (ReasonCode.TIMEOUT, TaskStage.INSERT_CONNECTOR): (
        MORE_BUDGET,
        FEWER_CORRECTIONS,
        FASTER_LATE_STAGE,
        DEEPER_INSERT,
    ),
    (ReasonCode.TIMEOUT, TaskStage.ALIGN_CONNECTOR): (
        MORE_BUDGET,
        FEWER_CORRECTIONS,
        FASTER_LATE_STAGE,
    ),
    (ReasonCode.OVER_TENSION, TaskStage.ROUTE_CLIP_2): (
        SHORTER_PULL,
        SLOWER_TRANSPORT,
        LOWER_ROUTE,
    ),
    (ReasonCode.INCOMPLETE_INSERTION, TaskStage.VERIFY_SEATED): (
        DEEPER_INSERT,
        SHORT_DANGLE_REGRASP,
        MORE_BUDGET,
    ),
    (ReasonCode.CONNECTOR_MISALIGNED, TaskStage.VERIFY_SEATED): (
        SHORT_DANGLE_REGRASP,
        GENTLE_ALIGN,
        DEEPER_INSERT,
    ),
}

_BY_CODE: dict[ReasonCode, tuple[RepairCandidate, ...]] = {
    ReasonCode.MISSED_GRASP: (SHALLOWER_SETTLE, LONGER_QUIET),
    ReasonCode.CABLE_SLIP: (FIRMER_CARRY, SLOWER_TRANSPORT, GENTLE_ALIGN),
    ReasonCode.CLIP_1_MISSED: (DEEPER_SETTLE, LOWER_ROUTE, LONGER_PULL),
    ReasonCode.CLIP_2_MISSED: (DEEPER_SETTLE, LOWER_ROUTE, LONGER_PULL),
    ReasonCode.CABLE_SNAG: (SLOWER_TRANSPORT, SHORTER_PULL, LOWER_ROUTE),
    ReasonCode.OVER_TENSION: (SHORTER_PULL, SLOWER_TRANSPORT, GENTLE_ALIGN),
    ReasonCode.ROBOT_COLLISION: (SLOWER_TRANSPORT, SHALLOWER_SETTLE),
    ReasonCode.CONNECTOR_MISALIGNED: (SHORT_DANGLE_REGRASP, GENTLE_ALIGN),
    ReasonCode.INCOMPLETE_INSERTION: (SHORT_DANGLE_REGRASP, DEEPER_INSERT),
    ReasonCode.TIMEOUT: (MORE_BUDGET, FEWER_CORRECTIONS, FASTER_LATE_STAGE),
    ReasonCode.UNSTABLE_SIMULATION: (SLOWER_TRANSPORT, FIRMER_CARRY),
}


def propose(reason_code: ReasonCode, task_stage: TaskStage) -> tuple[RepairCandidate, ...]:
    if not reason_code.is_failure:
        return ()
    staged = _BY_STAGE.get((reason_code, task_stage), ())
    generic = tuple(c for c in _BY_CODE[reason_code] if c not in staged)
    return staged + generic


def coverage() -> dict[ReasonCode, int]:
    return {code: len(_BY_CODE[code]) for code in FAILURE_CODES}
