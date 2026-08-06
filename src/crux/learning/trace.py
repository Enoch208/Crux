from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from math import atan2, cos, sin
from pathlib import Path

from pydantic import Field

from crux.control.directives import Observation, Reach, Settle
from crux.control.tooling import yaw_of_tool_quat
from crux.schema import Frozen

STEPS_SCALE = 20000.0
ACTION_WIDTH = 7


class TraceStep(Frozen):
    seed: int
    features: tuple[float, ...]
    action: tuple[float, float, float, float, float, float, float]


class LearnedAction(Frozen):
    delta: tuple[float, float, float]
    yaw_rad: float
    finger_force_n: float
    settle: bool


def chunk_features(observation: Observation) -> tuple[float, ...]:
    """Flatten one observation into the feature row both training and inference use."""
    values: list[float] = []
    for row in observation.cable_rows:
        values.extend(row)
    values.extend(observation.hand_pos)
    values.append(observation.pinch_gap_m)
    values.append(observation.cable_contact_n)
    values.append(observation.arm_contact_n)
    values.append(observation.steps_taken / STEPS_SCALE)
    return tuple(values)


def encode_action(
    observation: Observation, directive: Reach | Settle, last_yaw: float
) -> tuple[tuple[float, float, float, float, float, float, float], float]:
    if isinstance(directive, Settle):
        return (
            (0.0, 0.0, 0.0, sin(last_yaw), cos(last_yaw), directive.finger_force, 1.0),
            last_yaw,
        )
    yaw = yaw_of_tool_quat(directive.quat)
    hand = observation.hand_pos
    delta = (
        directive.pos[0] - hand[0],
        directive.pos[1] - hand[1],
        directive.pos[2] - hand[2],
    )
    return (
        (delta[0], delta[1], delta[2], sin(yaw), cos(yaw), directive.finger_force, 0.0),
        yaw,
    )


class ActionLimits(Frozen):
    max_step_m: float = Field(gt=0.0)
    min_force_n: float
    max_force_n: float
    workspace_low: tuple[float, float, float]
    workspace_high: tuple[float, float, float]


def decode_action(raw: Sequence[float], limits: ActionLimits) -> LearnedAction:
    """Clamp a raw network output into an executable, safety-bounded action."""
    if len(raw) != ACTION_WIDTH:
        raise ValueError(f"expected {ACTION_WIDTH} action values, got {len(raw)}")
    step = limits.max_step_m
    delta = (
        max(-step, min(step, raw[0])),
        max(-step, min(step, raw[1])),
        max(-step, min(step, raw[2])),
    )
    force = max(limits.min_force_n, min(limits.max_force_n, raw[5]))
    return LearnedAction(
        delta=delta,
        yaw_rad=atan2(raw[3], raw[4]),
        finger_force_n=force,
        settle=raw[6] > 0.5,
    )


def clamp_target(
    hand: tuple[float, float, float],
    action: LearnedAction,
    limits: ActionLimits,
) -> tuple[float, float, float]:
    low = limits.workspace_low
    high = limits.workspace_high
    return (
        max(low[0], min(high[0], hand[0] + action.delta[0])),
        max(low[1], min(high[1], hand[1] + action.delta[1])),
        max(low[2], min(high[2], hand[2] + action.delta[2])),
    )


def write_trace(path: Path, steps: Sequence[TraceStep]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for step in steps:
            handle.write(step.model_dump_json() + "\n")


def read_trace(path: Path) -> Iterator[TraceStep]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            yield TraceStep.model_validate(json.loads(line))
