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
OPEN_GAP_M = 0.080
FINGER_RATE_M = 0.002
MAX_CHUNKS = 20000
ROOMY_STEPS = 40000


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

    def __init__(
        self, task: TaskConfig, gap: float = ON_CABLE_GAP_M, error_floor_m: float = 0.0
    ) -> None:
        self.task = task
        self.closed_gap_m = gap
        self.gap = OPEN_GAP_M
        self.error_floor_m = error_floor_m
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
            self.move_fingers(directive.finger_force)
            return
        self.apply_target(directive.pos, directive.finger_force)

    def move_fingers(self, force: float) -> None:
        if force < 0.0:
            self.gap = max(self.closed_gap_m, self.gap - FINGER_RATE_M)
        else:
            self.gap = min(OPEN_GAP_M, self.gap + FINGER_RATE_M)

    def apply_target(self, target: tuple[float, float, float], force: float) -> None:
        self.steps += self.task.control.chunk_steps
        self.move_fingers(force)
        moved = []
        for current, goal in zip(self.hand, target, strict=True):
            delta = goal - current
            if abs(delta) <= self.error_floor_m:
                moved.append(current)
                continue
            reachable = delta - self.error_floor_m * (1.0 if delta > 0 else -1.0)
            moved.append(current + max(-STEP_M, min(STEP_M, reachable)))
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
    outcome = drive(EpisodePolicy(task, knobs(timeout_steps=ROOMY_STEPS)), FakeWorld(task))
    assert outcome.reason_code is ReasonCode.SUCCESS
    assert outcome.task_stage is TaskStage.VERIFY_SEATED


def test_every_stage_is_narrated_on_the_way_through() -> None:
    task = config()
    outcome = drive(EpisodePolicy(task, knobs(timeout_steps=ROOMY_STEPS)), FakeWorld(task))
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
    outcome = drive(
        EpisodePolicy(task, knobs(skip_insert_regrip=1, timeout_steps=ROOMY_STEPS)),
        FakeWorld(task),
    )
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
    outcome = drive(
        EpisodePolicy(task, knobs(withdraw_sideways_m=0.06, timeout_steps=ROOMY_STEPS)),
        FakeWorld(task),
    )
    assert outcome.reason_code is ReasonCode.SUCCESS


def test_the_baseline_lifts_straight_up() -> None:
    assert knobs().withdraw_sideways_m == 0.0


def test_an_arm_with_steady_state_error_still_completes_the_task() -> None:
    task = config()
    world = FakeWorld(task, error_floor_m=0.006)
    outcome = drive(EpisodePolicy(task, knobs(timeout_steps=ROOMY_STEPS)), world)
    assert outcome.reason_code is ReasonCode.SUCCESS


def test_a_large_steady_state_error_terminates_instead_of_spinning() -> None:
    task = config()
    precise = FakeWorld(task)
    sloppy = FakeWorld(task, error_floor_m=0.20)
    drive(EpisodePolicy(task, knobs(timeout_steps=ROOMY_STEPS)), precise)
    drive(EpisodePolicy(task, knobs(timeout_steps=ROOMY_STEPS)), sloppy)
    assert sloppy.steps < precise.steps * 3


def test_the_fingers_are_given_enough_chunks_to_close_from_fully_open() -> None:
    task = config()
    travel_m = OPEN_GAP_M - ON_CABLE_GAP_M
    chunks_needed = travel_m / FINGER_RATE_M
    assert task.control.close_chunks_max >= chunks_needed


def test_a_grasp_starting_from_a_fully_open_gripper_succeeds() -> None:
    task = config()
    world = FakeWorld(task)
    assert world.gap == OPEN_GAP_M
    outcome = drive(EpisodePolicy(task, knobs(timeout_steps=ROOMY_STEPS)), world)
    assert outcome.reason_code is ReasonCode.SUCCESS


def test_reach_waypoints_advance_no_faster_than_the_drag_speed() -> None:
    from crux.control.directives import Reach

    task = config()
    world = FakeWorld(task)
    policy = EpisodePolicy(task, knobs(timeout_steps=ROOMY_STEPS))
    step_budget = knobs().drag_speed_mps * task.control.chunk_steps * policy.timestep_s
    assert policy.chunk_steps == task.control.chunk_steps
    plan = policy.run(world.observation())
    directive = next(plan)
    previous = None
    jumps: list[float] = []
    for _ in range(MAX_CHUNKS):
        if isinstance(directive, Finish):
            break
        if isinstance(directive, Reach):
            if previous is not None:
                jumps.append(
                    sum((a - b) ** 2 for a, b in zip(directive.pos, previous, strict=True)) ** 0.5
                )
            previous = directive.pos
        else:
            previous = None
        world.held_index = policy.held_link
        world.apply(directive)
        directive = plan.send(world.observation())
    assert jumps
    assert max(jumps) <= step_budget + 1e-9


def test_transport_lifts_to_height_before_translating() -> None:
    from crux.control.directives import Reach

    task = config()
    world = FakeWorld(task)
    policy = EpisodePolicy(task, knobs(timeout_steps=ROOMY_STEPS))
    plan = policy.run(world.observation())
    directive = next(plan)
    low_lateral_move = 0.0
    prev_tip = None
    for _ in range(MAX_CHUNKS):
        if isinstance(directive, Finish):
            break
        if (
            isinstance(directive, Reach)
            and policy.stage.name.startswith("ROUTE")
            and policy.held_link is not None
        ):
            tip_z = directive.pos[2] - task.control.hand_to_tip_m
            if prev_tip is not None and tip_z < task.thresholds.gate_link_z_m:
                lateral = abs(directive.pos[1] - prev_tip[1])
                low_lateral_move = max(low_lateral_move, lateral)
            prev_tip = directive.pos
        else:
            prev_tip = None
        world.held_index = policy.held_link
        world.apply(directive)
        directive = plan.send(world.observation())
    assert low_lateral_move < 0.002


def test_mouth_entry_still_runs_the_full_task_to_success() -> None:
    task = config()
    outcome = drive(
        EpisodePolicy(task, knobs(mouth_entry_m=0.045, timeout_steps=ROOMY_STEPS)),
        FakeWorld(task),
    )
    assert outcome.reason_code is ReasonCode.SUCCESS


def test_the_nudge_seat_sequence_completes_and_narrates() -> None:
    task = config()
    outcome = drive(
        EpisodePolicy(
            task,
            knobs(
                nudge_seat=1,
                mouth_entry_m=0.045,
                skip_mid_regrip=1,
                skip_insert_regrip=1,
                timeout_steps=ROOMY_STEPS,
            ),
        ),
        FakeWorld(task),
    )
    assert outcome.reason_code is ReasonCode.SUCCESS
    assert any("nudge: head at" in note for note in outcome.notes)
