from __future__ import annotations

from collections.abc import Sequence
from math import pi
from pathlib import Path

import pytest

from crux.control.batch_driver import ControlPolicy
from crux.control.directives import Finish, Observation, Reach, Settle
from crux.control.learned import LearnedEpisodePolicy
from crux.control.policy import EpisodePolicy
from crux.control.seating import seat_metrics
from crux.control.tooling import tool_down_yaw_quat, yaw_of_tool_quat
from crux.failures.taxonomy import ReasonCode, TaskStage
from crux.learning.trace import (
    ActionLimits,
    chunk_features,
    clamp_target,
    decode_action,
    encode_action,
)
from crux.repair.knobs import ControllerKnobs
from crux.simulation.taskconfig import TaskConfig, load_task_config

CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "task.yaml"


def config() -> TaskConfig:
    return load_task_config(CONFIG_PATH)


def limits(task: TaskConfig) -> ActionLimits:
    return ActionLimits(
        max_step_m=0.03,
        min_force_n=-70.0,
        max_force_n=task.control.open_force_n,
        workspace_low=(-0.5, -0.5, 0.008),
        workspace_high=(0.9, 0.9, 0.4),
    )


def observation(
    steps: int = 0,
    tension: float = 1.0,
    contact: float = 0.0,
    finite: bool = True,
    rows: tuple[tuple[float, float, float], ...] | None = None,
) -> Observation:
    task = config()
    if rows is None:
        rows = tuple((0.46, -0.30 + 0.02 * index, 0.004) for index in range(task.cable.segments))
    return Observation(
        cable_rows=rows,
        hand_pos=(0.30, -0.30, 0.40),
        pinch_gap_m=0.08,
        cable_contact_n=tension,
        arm_contact_n=contact,
        held_link_contact_n=0.0,
        steps_taken=steps,
        cable_is_finite=finite,
    )


def still_predictor(features: Sequence[float]) -> Sequence[float]:
    return (0.0, 0.0, 0.0, 0.0, 1.0, 5.0, 0.0)


def policy(predictor: object = still_predictor, budget: int = 500) -> LearnedEpisodePolicy:
    task = config()
    return LearnedEpisodePolicy(
        config=task,
        predictor=predictor,  # type: ignore[arg-type]
        limits=limits(task),
        budget_steps=budget,
    )


def test_the_learned_policy_satisfies_the_driver_protocol() -> None:
    task = config()
    assert isinstance(policy(), ControlPolicy)
    assert isinstance(EpisodePolicy(task, ControllerKnobs.baseline(task)), ControlPolicy)


def test_each_chunk_yields_a_bounded_reach_from_the_predictor() -> None:
    seen: list[Sequence[float]] = []

    def predictor(features: Sequence[float]) -> Sequence[float]:
        seen.append(features)
        return (0.5, -0.5, 0.5, 0.0, 1.0, -40.0, 0.0)

    plan = policy(predictor).run(observation())
    directive = next(plan)
    assert isinstance(directive, Reach)
    assert directive.pos == pytest.approx((0.33, -0.33, 0.4))
    assert directive.finger_force == -40.0
    assert len(seen) == 1
    assert seen[0] == chunk_features(observation())


def test_a_settle_logit_holds_the_pose_instead_of_reaching() -> None:
    def predictor(features: Sequence[float]) -> Sequence[float]:
        return (0.5, 0.5, 0.5, 0.0, 1.0, -40.0, 0.9)

    plan = policy(predictor).run(observation())
    assert isinstance(next(plan), Settle)


def test_the_budget_ends_the_episode_with_the_harness_verdict() -> None:
    plan = policy(budget=500).run(observation())
    directive = next(plan)
    steps = 0
    while not isinstance(directive, Finish):
        steps += 25
        directive = plan.send(observation(steps=steps))
    assert directive.reason_code in (
        ReasonCode.CONNECTOR_MISALIGNED,
        ReasonCode.INCOMPLETE_INSERTION,
    )
    assert directive.task_stage is TaskStage.VERIFY_SEATED
    assert directive.seat_lateral_m is not None


def test_over_tension_aborts_through_the_shared_safety_envelope() -> None:
    plan = policy().run(observation())
    next(plan)
    directive = plan.send(observation(steps=25, tension=99.0))
    assert isinstance(directive, Finish)
    assert directive.reason_code is ReasonCode.OVER_TENSION


def test_a_seated_final_state_is_judged_success_by_the_shared_ruler() -> None:
    task = config()
    layout = task.layout
    segment = task.cable.total_length_m / task.cable.segments
    rows = [(0.46, -0.30 + 0.02 * index, 0.004) for index in range(task.cable.segments)]
    rows[-2] = (layout.socket_x, layout.socket_y - 1.5 * segment, 0.010)
    rows[-1] = (layout.socket_x, layout.socket_y - 0.5 * segment, 0.010)
    seated_view = observation(rows=tuple(rows))
    assert seat_metrics(task, seated_view)[0]

    plan = policy(budget=100).run(seated_view)
    directive = next(plan)
    while not isinstance(directive, Finish):
        directive = plan.send(observation(steps=seated_view.steps_taken + 101, rows=tuple(rows)))
    assert directive.reason_code is ReasonCode.SUCCESS


def test_action_encoding_round_trips_through_decoding() -> None:
    task = config()
    view = observation()
    reach = Reach((0.32, -0.31, 0.39), tool_down_yaw_quat(0.7), -56.0)
    encoded, yaw = encode_action(view, reach, last_yaw=0.0)
    assert yaw == 0.7
    action = decode_action(encoded, limits(task))
    assert action.delta == pytest.approx((0.02, -0.01, -0.01))
    assert action.yaw_rad == pytest.approx(0.7)
    assert action.finger_force_n == -56.0
    assert not action.settle
    assert clamp_target(view.hand_pos, action, limits(task)) == pytest.approx((0.32, -0.31, 0.39))


def test_yaw_recovery_inverts_the_tool_quat() -> None:
    for yaw in (-pi / 2, -0.3, 0.0, 0.3, pi / 2):
        assert abs(yaw_of_tool_quat(tool_down_yaw_quat(yaw)) - yaw) < 1e-12


def test_decoded_actions_are_clamped_to_the_safety_box() -> None:
    task = config()
    action = decode_action((9.0, -9.0, 9.0, 0.0, 1.0, -999.0, 0.0), limits(task))
    assert action.delta == (0.03, -0.03, 0.03)
    assert action.finger_force_n == -70.0
    target = clamp_target((0.89, -0.49, 0.39), action, limits(task))
    assert target == (0.9, -0.5, 0.4)
