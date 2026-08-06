from __future__ import annotations

from crux.errors import CruxError, ErrorCode
from crux.repair.knobs import ControllerKnobs
from crux.simulation.taskconfig import TaskConfig

BASELINE_OVERRIDES: dict[str, float] = {"timeout_steps": 20000}
V2_OVERRIDES: dict[str, float] = {
    "drag_speed_mps": 0.30,
    "insert_carry_z_m": 0.035,
    "grasp_at_link_height": 1,
    "align_step_cap_m": 0.008,
    "align_corrections": 6,
    "insert_link_from_end": 0,
    "close_force_n": -56.0,
    "timeout_steps": 20000,
}
V3_OVERRIDES: dict[str, float] = {**V2_OVERRIDES, "grasp_attempts": 3}
V4_OVERRIDES: dict[str, float] = {
    **V3_OVERRIDES,
    "nudge_seat": 1,
    "nudge_stop_short_m": 0.001,
    "nudge_rounds": 2,
}
V5_OVERRIDES: dict[str, float] = {
    **V4_OVERRIDES,
    "slip_guard": 1,
    "slip_warn_ratio": 0.45,
    "slip_debounce_chunks": 2,
    "slip_grip_boost": 1.8,
}

CANDIDATES: dict[str, dict[str, float]] = {
    "baseline-v1": BASELINE_OVERRIDES,
    "candidate-v2": V2_OVERRIDES,
    "candidate-v3": V3_OVERRIDES,
    "candidate-v4": V4_OVERRIDES,
    "candidate-v5": V5_OVERRIDES,
}


def overrides_for(version: str) -> dict[str, float]:
    """Return the knob overrides that define a named controller version."""
    if version not in CANDIDATES:
        raise CruxError(
            ErrorCode.CONTROLLER_UNKNOWN,
            f"unknown controller {version!r}; known: {sorted(CANDIDATES)}",
        )
    return dict(CANDIDATES[version])


def knobs_for(version: str, config: TaskConfig) -> ControllerKnobs:
    """Rebuild a named controller from the task defaults and its recorded overrides."""
    return ControllerKnobs.baseline(config).with_overrides(overrides_for(version))
