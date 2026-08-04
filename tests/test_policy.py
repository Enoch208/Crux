from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from crux.control.directives import Finish, Observation, Reach, Settle
from crux.control.policy import EpisodePolicy
from crux.failures.taxonomy import ReasonCode, TaskStage
from crux.repair.knobs import ControllerKnobs
from crux.simulation.taskconfig import TaskConfig, load_task_config

CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "task.yaml"
STEP_M = 0.02
ON_CABLE_GAP_M = 0.0059
ON_AIR_GAP_M = 0.0015
MAX_CHUNKS = 20000


def config() -> TaskConfig:
    return load_task_config(CONFIG_PATH)


def seated_rows(
    task: TaskConfig, held: tuple[float, float, float], held_index: int | None
) -> tuple[tuple[float, float, float], ...]:
    layout = task.layout
    rows = [(0.46, -0.30 + 0.02 * index, 0.004) for index in range(task.cable.segments)]
    rows[-1] = (layout.socket_x, layout.socket_y, 0.010)
    for index, centre in enumerate(layout.clip_centres()):
        rows[index * 2 + 1] = (centre[0], centre[1] - 0.01, 0.010)
        rows[index * 2 + 2] = (centre[0], centre[1] + 0.01, 0.010)
    if held_index is not None:
        rows[held_index] = held
    return tuple(rows)


class FakeWorld:
    """A cooperative world: the tool converges on targets and the cable behaves."""

    def __init__(self, task: TaskConfig, gap: float = ON_CABLE_GAP_M) -> None:
        self.task = task
        self.gap = gap
        self.hand = (0.30, -0.30, 0.40)
        self.held_index: int | None = None
        self.steps = 0
        self.cable_contact_n = 1.0
        self.arm_contact_n = 0.0

    def observation(self) -> Observation:
        tip = (self.hand[0], self.hand[1], self.hand[2] - self.task.control.hand_to_tip_m)
        return Observation(
            cable_rows=seated_rows(self.task, tip, self.held_index),
            hand_pos=self.hand,
            pinch_gap_m=self.gap,
            cable_contact_n=self.cable_contact_n,
            arm_contact_n=self.arm_contact_n,
            held_link_contact_n=2.0,
            steps_taken=self.steps,
            cable_is_finite=True,
        )

    def apply(self, directive: Reach | Settle) -> None:
        if isinstance(directive, Settle):
            self.steps += self.task.control.chunk_steps
            return
        self.apply_target(directive.pos, directive.finger_force)

    def apply_target(self, target: tuple[float, float, float], _force: float) -> None:
        self.steps += self.task.control.chunk_steps
        moved = []
        for current, goal in zip(self.hand, target, strict=True):
            delta = goal - current
            moved.append(current + max(-STEP_M, min(STEP_M, delta)))
        self.hand = (moved[0], moved[1], moved[2])


def drive(policy: EpisodePolicy, world: FakeWorld) -> Finish:
    plan = policy.run(world.observation())
    directive = next(plan)
    for _ in range(MAX_CHUNKS):
        if isinstance(directive, Finish):
            return directive
        world.apply(directive)
        world.held_index = policy.held_link
        directive = plan.send(world.observation())
    raise AssertionError("policy never finished")


def knobs(**overrides: object) -> ControllerKnobs:
    base = ControllerKnobs.baseline(config())
    return base.with_overrides(dict(overrides)) if overrides else base


def test_a_cooperative_world_runs_the_whole_task_to_success() -> None:
    task = config()
    outcome = drive(EpisodePolicy(task, knobs()), FakeWorld(task))
    assert outcome.reason_code is ReasonCode.SUCCESS
    assert outcome.task_stage is TaskStage.VERIFY_SEATED


def test_every_stage_is_narrated_on_the_way_through() -> None:
    task = config()
    outcome = drive(EpisodePolicy(task, knobs()), FakeWorld(task))
    narrated = " ".join(outcome.notes)
    assert "grasp verified" in narrated
    assert narrated.count("crossing(s) in gate") == 2
    assert "connector lateral" in narrated


def test_closing_on_air_is_reported_as_a_missed_grasp() -> None:
    task = config()
    outcome = drive(EpisodePolicy(task, knobs()), FakeWorld(task, gap=ON_AIR_GAP_M))
    assert outcome.reason_code is ReasonCode.MISSED_GRASP
    assert "link contact" in outcome.notes[-1]


def test_excess_cable_tension_aborts_the_episode() -> None:
    task = config()
    world = FakeWorld(task)
    world.cable_contact_n = task.thresholds.tension_n + 1.0
    outcome = drive(EpisodePolicy(task, knobs()), world)
    assert outcome.reason_code is ReasonCode.OVER_TENSION


def test_arm_collision_aborts_the_episode() -> None:
    task = config()
    world = FakeWorld(task)
    world.arm_contact_n = task.thresholds.arm_collision_n + 1.0
    outcome = drive(EpisodePolicy(task, knobs()), world)
    assert outcome.reason_code is ReasonCode.ROBOT_COLLISION


def test_the_step_budget_is_enforced() -> None:
    task = config()
    outcome = drive(EpisodePolicy(task, knobs(timeout_steps=400)), FakeWorld(task))
    assert outcome.reason_code is ReasonCode.TIMEOUT


def test_skipping_the_insert_regrip_still_completes() -> None:
    task = config()
    outcome = drive(EpisodePolicy(task, knobs(skip_insert_regrip=1)), FakeWorld(task))
    assert outcome.reason_code is ReasonCode.SUCCESS
    assert not any("regripping on link 15" in note for note in outcome.notes)


def test_a_misaligned_connector_is_distinguished_from_a_shallow_one() -> None:
    task = config()
    world = FakeWorld(task)
    policy = EpisodePolicy(task, knobs())
    observed = world.observation()
    far = replace(observed, cable_rows=(*observed.cable_rows[:-1], (0.60, 0.40, 0.010)))
    seated, lateral, _ = policy.seat_metrics(far)
    assert not seated
    assert lateral > task.thresholds.seat_lateral_m


def test_withdrawing_sideways_adds_a_lateral_step_before_lifting() -> None:
    task = config()
    outcome = drive(EpisodePolicy(task, knobs(withdraw_sideways_m=0.06)), FakeWorld(task))
    assert outcome.reason_code is ReasonCode.SUCCESS


def test_the_baseline_lifts_straight_up() -> None:
    assert knobs().withdraw_sideways_m == 0.0
