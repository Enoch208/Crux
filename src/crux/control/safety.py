from __future__ import annotations

from crux.control.directives import Observation
from crux.failures.taxonomy import ReasonCode
from crux.simulation.taskconfig import ThresholdConfig


def abort_reason(
    observation: Observation,
    thresholds: ThresholdConfig,
    budget_steps: int,
) -> tuple[ReasonCode, str] | None:
    """The harness-owned safety envelope, identical for every policy it drives."""
    if not observation.cable_is_finite:
        return ReasonCode.UNSTABLE_SIMULATION, "non-finite cable state"
    if observation.cable_contact_n > thresholds.tension_n:
        return (
            ReasonCode.OVER_TENSION,
            f"cable contact {observation.cable_contact_n:.1f} N > {thresholds.tension_n}",
        )
    if observation.arm_contact_n > thresholds.arm_collision_n:
        return ReasonCode.ROBOT_COLLISION, f"arm link contact {observation.arm_contact_n:.1f} N"
    if observation.steps_taken > budget_steps:
        return ReasonCode.TIMEOUT, f"exceeded {budget_steps} steps"
    return None
