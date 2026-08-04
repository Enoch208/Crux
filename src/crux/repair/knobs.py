from __future__ import annotations

from typing import Any

from pydantic import Field

from crux.schema import Frozen
from crux.simulation.taskconfig import TaskConfig

BASELINE_SETTLE_TIP_Z_M = 0.020
BASELINE_PULL_PAST_M = 0.055
BASELINE_ALIGN_STEP_CAP_M = 0.025
BASELINE_ALIGN_CORRECTIONS = 3
BASELINE_QUIET_STEPS = 150
BASELINE_INSERT_CARRY_Z_M = 0.055
BASELINE_HOVER_SETTLE_STEPS = 0


class ControllerKnobs(Frozen):
    grasp_link_from_end: int = Field(ge=1)
    insert_link_from_end: int = Field(ge=0)
    close_force_n: float = Field(lt=0.0)
    route_z_m: float = Field(gt=0.0)
    insert_z_m: float = Field(gt=0.0)
    insert_carry_z_m: float = Field(gt=0.0)
    settle_tip_z_m: float = Field(gt=0.0)
    pull_past_m: float = Field(gt=0.0)
    align_step_cap_m: float = Field(gt=0.0)
    align_corrections: int = Field(ge=1)
    quiet_steps: int = Field(ge=0)
    drag_speed_mps: float = Field(gt=0.0)
    timeout_steps: int = Field(gt=0)
    hover_settle_steps: int = Field(ge=0)
    reaim_before_pinch: int = Field(ge=0, le=1)
    skip_mid_regrip: int = Field(ge=0, le=1)
    regrip_link_delta: int = Field(ge=-2, le=2)
    grasp_at_link_height: int = Field(ge=0, le=1)
    skip_insert_regrip: int = Field(ge=0, le=1)
    withdraw_sideways_m: float = Field(ge=0.0)
    mouth_entry_m: float = Field(ge=0.0)
    nudge_seat: int = Field(ge=0, le=1)

    @classmethod
    def baseline(cls, config: TaskConfig) -> ControllerKnobs:
        control = config.control
        return cls(
            grasp_link_from_end=control.grasp_link_from_end,
            insert_link_from_end=control.grasp_link_from_end,
            close_force_n=control.close_force_n,
            route_z_m=control.route_z_m,
            insert_z_m=control.insert_z_m,
            insert_carry_z_m=BASELINE_INSERT_CARRY_Z_M,
            settle_tip_z_m=BASELINE_SETTLE_TIP_Z_M,
            pull_past_m=BASELINE_PULL_PAST_M,
            align_step_cap_m=BASELINE_ALIGN_STEP_CAP_M,
            align_corrections=BASELINE_ALIGN_CORRECTIONS,
            quiet_steps=BASELINE_QUIET_STEPS,
            drag_speed_mps=control.drag_speed_mps,
            timeout_steps=config.thresholds.timeout_steps,
            hover_settle_steps=BASELINE_HOVER_SETTLE_STEPS,
            reaim_before_pinch=0,
            skip_mid_regrip=0,
            regrip_link_delta=0,
            grasp_at_link_height=0,
            skip_insert_regrip=0,
            withdraw_sideways_m=0.0,
            mouth_entry_m=0.0,
            nudge_seat=0,
        )

    def with_overrides(self, overrides: dict[str, Any]) -> ControllerKnobs:
        unknown = set(overrides) - set(type(self).model_fields)
        if unknown:
            raise ValueError(f"unknown knobs: {sorted(unknown)}")
        return type(self).model_validate({**self.model_dump(), **overrides})

    def changes_from(self, base: ControllerKnobs) -> dict[str, Any]:
        mine = self.model_dump()
        theirs = base.model_dump()
        return {key: value for key, value in mine.items() if theirs[key] != value}

    def grasp_index(self, segments: int) -> int:
        return self._index(segments, self.grasp_link_from_end)

    def insert_index(self, segments: int) -> int:
        return self._index(segments, self.insert_link_from_end)

    @staticmethod
    def _index(segments: int, from_end: int) -> int:
        index = segments - 1 - from_end
        if index < 0:
            raise ValueError(f"link {from_end} from the end does not exist in {segments} segments")
        return index
