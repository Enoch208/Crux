from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

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
    segment = task.cable.total_length_m / task.cable.segments
    rows = [(0.46, -0.30 + 0.02 * index, 0.004) for index in range(task.cable.segments)]
    rows[-2] = (layout.socket_x, layout.socket_y - 1.5 * segment, 0.010)
    rows[-1] = (layout.socket_x, layout.socket_y - 0.5 * segment, 0.010)
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


class FlakyGraspWorld(FakeWorld):
    def __init__(self, task: TaskConfig, misses: int) -> None:
        super().__init__(task)
        self.misses = misses
        self.missed_close = False

    def move_fingers(self, force: float) -> None:
        if force < 0.0:
            floor = ON_AIR_GAP_M if self.misses > 0 else self.closed_gap_m
            self.gap = max(floor, self.gap - FINGER_RATE_M)
            if self.misses > 0 and self.gap <= ON_AIR_GAP_M + 1e-9:
                self.missed_close = True
        else:
            self.gap = min(OPEN_GAP_M, self.gap + FINGER_RATE_M)
            if self.missed_close and self.gap >= OPEN_GAP_M - 1e-9:
                self.misses -= 1
                self.missed_close = False


def test_closing_on_air_is_reported_as_a_missed_grasp() -> None:
    task = config()
    outcome = drive(EpisodePolicy(task, knobs()), FakeWorld(task, gap=ON_AIR_GAP_M))
    assert outcome.reason_code is ReasonCode.MISSED_GRASP
    assert "after 1 attempt" in outcome.notes[-1]


def test_a_retry_recovers_a_transient_missed_grasp() -> None:
    task = config()
    world = FlakyGraspWorld(task, misses=1)
    outcome = drive(EpisodePolicy(task, knobs(grasp_attempts=2, timeout_steps=ROOMY_STEPS)), world)
    assert outcome.reason_code is ReasonCode.SUCCESS
    narrated = " ".join(outcome.notes)
    assert "reopening for attempt 2" in narrated


def test_a_single_attempt_still_fails_on_a_transient_miss() -> None:
    task = config()
    outcome = drive(EpisodePolicy(task, knobs()), FlakyGraspWorld(task, misses=1))
    assert outcome.reason_code is ReasonCode.MISSED_GRASP
    assert outcome.task_stage is TaskStage.CLOSE_GRIPPER


def test_tip_pinch_bias_shifts_the_end_link_target_outward() -> None:
    task = config()
    observation = FakeWorld(task).observation()
    policy = EpisodePolicy(task, knobs(tip_pinch_bias_m=0.012))
    tip = len(observation.cable_rows) - 1
    row = observation.cable_rows[tip]
    inner = observation.cable_rows[tip - 1]
    biased = policy.pinch_point(observation, tip)
    dx, dy = biased[0] - row[0], biased[1] - row[1]
    assert dx * (row[0] - inner[0]) + dy * (row[1] - inner[1]) > 0.0
    assert 0.0 < (dx**2 + dy**2) ** 0.5 <= 0.012 + 1e-9
    mid_row = observation.cable_rows[5]
    assert policy.pinch_point(observation, 5) == (mid_row[0], mid_row[1])


def test_tip_pinch_bias_defaults_off_and_leaves_targets_alone() -> None:
    task = config()
    observation = FakeWorld(task).observation()
    policy = EpisodePolicy(task, knobs())
    tip = len(observation.cable_rows) - 1
    row = observation.cable_rows[tip]
    assert policy.pinch_point(observation, tip) == (row[0], row[1])


def test_the_biased_pinch_still_completes_the_cooperative_run() -> None:
    task = config()
    outcome = drive(
        EpisodePolicy(task, knobs(tip_pinch_bias_m=0.012, timeout_steps=ROOMY_STEPS)),
        FakeWorld(task),
    )
    assert outcome.reason_code is ReasonCode.SUCCESS


def test_retries_exhaust_against_a_persistent_miss() -> None:
    task = config()
    world = FlakyGraspWorld(task, misses=10)
    outcome = drive(EpisodePolicy(task, knobs(grasp_attempts=3, timeout_steps=ROOMY_STEPS)), world)
    assert outcome.reason_code is ReasonCode.MISSED_GRASP
    assert "after 3 attempt(s)" in outcome.notes[-1]


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
    assert any("nudge 1: head at" in note for note in outcome.notes)


def test_the_cross_grip_fast_nudge_still_completes_and_narrates() -> None:
    task = config()
    outcome = drive(
        EpisodePolicy(
            task,
            knobs(
                nudge_seat=1,
                nudge_cross_grip=1,
                nudge_speed_mps=0.6,
                mouth_entry_m=0.045,
                skip_mid_regrip=1,
                skip_insert_regrip=1,
                timeout_steps=ROOMY_STEPS,
            ),
        ),
        FakeWorld(task),
    )
    assert outcome.reason_code is ReasonCode.SUCCESS
    assert any("cross-grip nudge" in note for note in outcome.notes)


def test_the_origin_seat_metric_was_geometrically_unsatisfiable() -> None:
    task = config()
    segment = task.cable.total_length_m / task.cable.segments
    back_wall_inner_y = task.layout.socket_y + task.layout.socket_depth_m / 2.0
    fully_seated_origin_y = back_wall_inner_y - segment
    origin_floor = task.layout.socket_y - fully_seated_origin_y
    assert origin_floor > task.thresholds.seat_lateral_m
    assert abs(origin_floor - 0.013) < 1e-9


def test_seat_metrics_measure_the_connector_body_not_the_joint() -> None:
    task = config()
    policy = EpisodePolicy(task, knobs())
    observation = FakeWorld(task).observation()
    seated, lateral, _ = policy.seat_metrics(observation)
    assert seated
    assert lateral < 0.001
    rows = list(observation.cable_rows)
    rows[-1] = (rows[-1][0], rows[-1][1] - 0.020, rows[-1][2])
    rows[-2] = (rows[-2][0], rows[-2][1] - 0.020, rows[-2][2])
    moved = replace(observation, cable_rows=tuple(rows))
    seated_after, lateral_after, _ = policy.seat_metrics(moved)
    assert not seated_after
    assert lateral_after > 0.015


class DriftingGraspWorld(FakeWorld):
    """A world where the held link creeps away from the fingertips every chunk."""

    def __init__(self, task: TaskConfig, drift_per_chunk_m: float, cap_m: float) -> None:
        super().__init__(task)
        self.drift_per_chunk_m = drift_per_chunk_m
        self.cap_m = cap_m
        self.drift_m = 0.0

    def observation(self) -> Observation:
        base = super().observation()
        if self.held_index is None:
            return base
        rows = list(base.cable_rows)
        x, y, z = rows[self.held_index]
        rows[self.held_index] = (x, y - self.drift_m, z)
        return replace(base, cable_rows=tuple(rows))

    def apply(self, directive: Reach | Settle) -> None:
        super().apply(directive)
        if self.held_index is not None:
            self.drift_m = min(self.cap_m, self.drift_m + self.drift_per_chunk_m)


def slip_knobs(**overrides: object) -> ControllerKnobs:
    settings: dict[str, object] = {
        "slip_guard": 1,
        "slip_warn_ratio": 0.6,
        "slip_debounce_chunks": 3,
        "slip_grip_boost": 1.5,
        "timeout_steps": ROOMY_STEPS,
    }
    settings.update(overrides)
    return knobs(**settings)


def test_the_slip_guard_is_off_unless_asked_for() -> None:
    task = config()
    policy = EpisodePolicy(task, knobs(timeout_steps=ROOMY_STEPS))
    drive(policy, DriftingGraspWorld(task, 0.004, 0.030))
    assert policy.slip_boosts == 0
    assert policy.grip_force_n == task.control.close_force_n


def test_a_drifting_grip_is_tightened_before_the_cable_is_lost() -> None:
    task = config()
    policy = EpisodePolicy(task, slip_knobs())
    outcome = drive(policy, DriftingGraspWorld(task, 0.004, 0.030))
    assert policy.slip_boosts >= 1
    assert any("slip warning" in note for note in outcome.notes)


def test_the_tightened_force_is_what_gets_commanded() -> None:
    task = config()
    policy = EpisodePolicy(task, slip_knobs(slip_debounce_chunks=2))
    policy.held_link = 5
    world = FakeWorld(task)
    world.held_index = 5
    drifted = world.observation()
    rows = list(drifted.cable_rows)
    rows[5] = (rows[5][0], rows[5][1] - 0.030, rows[5][2])
    drifting = replace(drifted, cable_rows=tuple(rows))
    for _ in range(6):
        policy.watch_for_slip(drifting)
    assert policy.slip_boosts == 1
    assert policy.grip_force_n == pytest.approx(task.control.close_force_n * 1.5)


def test_a_steady_grip_never_triggers_the_guard() -> None:
    task = config()
    policy = EpisodePolicy(task, slip_knobs())
    drive(policy, FakeWorld(task))
    assert policy.slip_boosts == 0
    assert policy.grip_force_n == task.control.close_force_n


def test_the_filter_absorbs_a_single_chunk_spike() -> None:
    task = config()
    policy = EpisodePolicy(task, slip_knobs())
    policy.held_link = 5
    world = FakeWorld(task)
    world.held_index = 5
    spike = world.observation()
    rows = list(spike.cable_rows)
    rows[5] = (rows[5][0], rows[5][1] - 0.034, rows[5][2])
    policy.watch_for_slip(replace(spike, cable_rows=tuple(rows)))
    policy.watch_for_slip(world.observation())
    assert policy.slip_boosts == 0


def test_the_guard_tightens_once_per_grasp_not_once_per_chunk() -> None:
    task = config()
    policy = EpisodePolicy(task, slip_knobs(slip_debounce_chunks=1))
    policy.held_link = 5
    world = FakeWorld(task)
    world.held_index = 5
    drifted = world.observation()
    rows = list(drifted.cable_rows)
    rows[5] = (rows[5][0], rows[5][1] - 0.030, rows[5][2])
    drifting = replace(drifted, cable_rows=tuple(rows))
    for _ in range(10):
        policy.watch_for_slip(drifting)
    assert policy.slip_boosts == 1

    policy.arm_slip_guard()
    for _ in range(10):
        policy.watch_for_slip(drifting)
    assert policy.slip_boosts == 2


def test_a_fresh_grasp_rearms_the_guard() -> None:
    task = config()
    policy = EpisodePolicy(task, slip_knobs())
    policy.grip_force_n = -99.0
    policy.slip_chunks = 7
    policy.slip_margin_m = 0.03
    policy.arm_slip_guard()
    assert policy.grip_force_n == task.control.close_force_n
    assert policy.slip_chunks == 0
    assert policy.slip_margin_m is None


def test_safety_maxima_are_tracked_across_the_episode() -> None:
    task = config()
    world = FakeWorld(task)
    world.cable_contact_n = 4.25
    world.arm_contact_n = 1.5
    policy = EpisodePolicy(task, knobs(timeout_steps=ROOMY_STEPS))
    outcome = drive(policy, world)
    assert outcome.reason_code is ReasonCode.SUCCESS
    assert policy.max_cable_tension_n == 4.25
    assert policy.max_arm_contact_n == 1.5


def test_safety_maxima_capture_a_transient_spike() -> None:
    task = config()
    world = FakeWorld(task)
    policy = EpisodePolicy(task, knobs(timeout_steps=ROOMY_STEPS))
    plan = policy.run(world.observation())
    directive = next(plan)
    for step in range(40):
        if isinstance(directive, Finish):
            break
        world.apply(directive)
        world.cable_contact_n = 6.0 if step == 10 else 0.5
        world.held_index = policy.held_link
        directive = plan.send(world.observation())
    assert policy.max_cable_tension_n == 6.0


def test_reported_seat_metrics_agree_with_the_verdict() -> None:
    task = config()
    outcome = drive(EpisodePolicy(task, knobs(timeout_steps=ROOMY_STEPS)), FakeWorld(task))
    assert outcome.reason_code is ReasonCode.SUCCESS
    assert outcome.seat_lateral_m is not None
    assert outcome.seat_depth_m is not None
    assert outcome.seat_lateral_m < task.thresholds.seat_lateral_m
    assert outcome.seat_depth_m < task.thresholds.seat_z_m
    narrated = next(n for n in outcome.notes if "connector lateral" in n)
    assert f"{outcome.seat_lateral_m * 1000:.1f} mm" in narrated


def test_the_tow_insert_completes_and_narrates() -> None:
    task = config()
    outcome = drive(
        EpisodePolicy(
            task,
            knobs(tow_insert=1, timeout_steps=ROOMY_STEPS),
        ),
        FakeWorld(task),
    )
    assert outcome.reason_code is ReasonCode.SUCCESS
    assert any("tow from link 13" in note for note in outcome.notes)


def test_nudge_rounds_stop_once_seated() -> None:
    task = config()
    outcome = drive(
        EpisodePolicy(
            task,
            knobs(
                nudge_seat=1,
                nudge_rounds=3,
                nudge_stop_short_m=0.001,
                mouth_entry_m=0.045,
                skip_mid_regrip=1,
                skip_insert_regrip=1,
                timeout_steps=ROOMY_STEPS,
            ),
        ),
        FakeWorld(task),
    )
    assert outcome.reason_code is ReasonCode.SUCCESS
    narrated = " ".join(outcome.notes)
    assert "nudge 1: head at" in narrated
    assert "nudge 3: head at" not in narrated
