from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass, field
from itertools import pairwise
from math import atan2, sqrt

from crux.control.directives import (
    Directive,
    Finish,
    Observation,
    Quaternion,
    Reach,
    Settle,
    Vector,
)
from crux.control.tooling import TOOL_DOWN_QUAT, tool_down_yaw_quat
from crux.failures.taxonomy import ReasonCode, TaskStage
from crux.repair.knobs import ControllerKnobs
from crux.simulation.taskconfig import TaskConfig

CONVERGED_GAP_M = 0.0002
HOLD_RAMP_CHUNKS = 3
RELEASE_CHUNKS = 4
RETREAT_Z_M = 0.080
SEAT_SETTLE_CHUNKS = 12
SEAT_PUSH_CAP_M = 0.030
SEAT_PUSH_ROUNDS = 3
SEAT_PUSH_DONE_M = 0.004
NUDGE_BEHIND_M = 0.025
NUDGE_HOVER_Z_M = 0.055
NUDGE_STOP_SHORT_M = 0.006
REACH_TOLERANCE_M = 0.004
REACH_PROGRESS_M = 0.0005
REACH_STALL_CHUNKS = 3
MAX_CHUNKS_PER_REACH = 400

Plan = Generator[Directive, Observation, None]


class PolicyAbortError(Exception):
    def __init__(self, code: ReasonCode, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def distance(left: Vector, right: Vector) -> float:
    return sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def step_toward(current: Vector, target: Vector, step_m: float) -> Vector:
    remaining = distance(current, target)
    if remaining <= step_m:
        return target
    scale = step_m / remaining
    return (
        current[0] + (target[0] - current[0]) * scale,
        current[1] + (target[1] - current[1]) * scale,
        current[2] + (target[2] - current[2]) * scale,
    )


@dataclass(slots=True)
class EpisodePolicy:
    config: TaskConfig
    knobs: ControllerKnobs
    stage: TaskStage = TaskStage.OBSERVE
    held_link: int | None = field(default=None, init=False)
    tool_quat: Quaternion = field(default=TOOL_DOWN_QUAT, init=False)
    notes: list[str] = field(default_factory=list, init=False)
    timestep_s: float = 0.005
    chunk_steps: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.chunk_steps = self.config.control.chunk_steps

    def note(self, message: str) -> None:
        self.notes.append(f"{self.stage}: {message}")

    def grasp_index(self) -> int:
        return self.knobs.grasp_index(self.config.cable.segments)

    def insert_index(self) -> int:
        return self.knobs.insert_index(self.config.cable.segments)

    def mid_regrip_index(self) -> int:
        segments = self.config.cable.segments
        index = self.grasp_index() + self.knobs.regrip_link_delta
        if not 0 <= index < segments:
            raise PolicyAbortError(ReasonCode.MISSED_GRASP, f"regrip link {index} out of range")
        return index

    def tip_of(self, observation: Observation) -> Vector:
        hand = observation.hand_pos
        return (hand[0], hand[1], hand[2] - self.config.control.hand_to_tip_m)

    def local_yaw(self, observation: Observation, index: int) -> float:
        rows = observation.cable_rows
        low = rows[max(0, index - 1)]
        high = rows[min(len(rows) - 1, index + 1)]
        return atan2(high[1] - low[1], high[0] - low[0])

    def pinch_height(self, observation: Observation, index: int) -> float:
        floor = self.config.cable.radius_m
        if not self.knobs.grasp_at_link_height:
            return floor
        return max(floor, observation.cable_rows[index][2])

    def guard(self, observation: Observation) -> None:
        thresholds = self.config.thresholds
        if not observation.cable_is_finite:
            raise PolicyAbortError(ReasonCode.UNSTABLE_SIMULATION, "non-finite cable state")
        if observation.cable_contact_n > thresholds.tension_n:
            raise PolicyAbortError(
                ReasonCode.OVER_TENSION,
                f"cable contact {observation.cable_contact_n:.1f} N > {thresholds.tension_n}",
            )
        if observation.arm_contact_n > thresholds.arm_collision_n:
            raise PolicyAbortError(
                ReasonCode.ROBOT_COLLISION,
                f"arm link contact {observation.arm_contact_n:.1f} N",
            )
        if observation.steps_taken > self.knobs.timeout_steps:
            raise PolicyAbortError(ReasonCode.TIMEOUT, f"exceeded {self.knobs.timeout_steps} steps")
        if self.held_link is not None:
            gap = distance(observation.cable_rows[self.held_link], self.tip_of(observation))
            if gap > thresholds.slip_distance_m:
                raise PolicyAbortError(
                    ReasonCode.CABLE_SLIP,
                    f"held link {self.held_link} is {gap * 1000:.0f} mm from the fingertips",
                )

    def reach(self, observation: Observation, target: Vector, force: float) -> Plan:
        """Drive to a pose along rate-limited waypoints, stopping on arrival or stall.

        Commanding a distant target directly makes the position controller snap at full
        speed and fling a held cable, so the commanded waypoint advances at the configured
        drag speed. A position-controlled arm also holds a steady-state offset under
        gravity, so once the waypoint has arrived, stalling counts as arrival.
        """
        hand_target = (target[0], target[1], target[2] + self.config.control.hand_to_tip_m)
        step_m = self.knobs.drag_speed_mps * self.chunk_steps * self.timestep_s
        carrot = observation.hand_pos
        previous = distance(observation.hand_pos, hand_target)
        stalled = 0
        for _ in range(MAX_CHUNKS_PER_REACH):
            self.guard(observation)
            gap = distance(observation.hand_pos, hand_target)
            if gap <= REACH_TOLERANCE_M:
                return
            if carrot == hand_target:
                if previous - gap < REACH_PROGRESS_M:
                    stalled += 1
                    if stalled >= REACH_STALL_CHUNKS:
                        return
                else:
                    stalled = 0
            previous = gap
            carrot = step_toward(carrot, hand_target, step_m)
            observation = yield Reach(carrot, self.tool_quat, force)
        raise PolicyAbortError(ReasonCode.TIMEOUT, f"never reached {hand_target}")

    def hold(self, observation: Observation, force: float, chunks: int) -> Plan:
        for _ in range(chunks):
            self.guard(observation)
            observation = yield Settle(force)

    def grasp(self, observation: Observation, index: int) -> Plan:
        control = self.config.control
        thresholds = self.config.thresholds
        self.tool_quat = tool_down_yaw_quat(self.local_yaw(observation, index))

        row = observation.cable_rows[index]
        yield from self.reach(
            observation, (row[0], row[1], control.hover_z_m), control.open_force_n
        )
        observation = yield Settle(control.open_force_n)

        row = observation.cable_rows[index]
        pinch_z = self.pinch_height(observation, index)
        yield from self.reach(observation, (row[0], row[1], pinch_z), control.open_force_n)
        observation = yield Settle(control.open_force_n)

        previous = observation.pinch_gap_m
        for _ in range(control.close_chunks_max):
            self.guard(observation)
            observation = yield Settle(control.catch_force_n)
            if abs(previous - observation.pinch_gap_m) < CONVERGED_GAP_M:
                break
            previous = observation.pinch_gap_m

        gap = observation.pinch_gap_m
        if not thresholds.pinch_min_m < gap < thresholds.pinch_max_m:
            raise PolicyAbortError(
                ReasonCode.MISSED_GRASP,
                f"pinch gap {gap * 1000:.1f} mm on link {index} outside "
                f"[{thresholds.pinch_min_m * 1000:.0f}, {thresholds.pinch_max_m * 1000:.0f}] mm "
                f"(link contact {observation.held_link_contact_n:.2f} N)",
            )
        yield from self.hold(observation, self.knobs.close_force_n, HOLD_RAMP_CHUNKS)
        self.held_link = index
        self.note(f"holding link {index} (gap {gap * 1000:.1f} mm)")

    def release(self, observation: Observation, terminal: bool = False) -> Plan:
        open_force = self.config.control.open_force_n
        self.held_link = None
        yield from self.hold(observation, open_force, RELEASE_CHUNKS)
        observation = yield Settle(open_force)
        if terminal and self.knobs.withdraw_sideways_m > 0.0:
            tip = self.tip_of(observation)
            aside = (tip[0] - self.knobs.withdraw_sideways_m, tip[1], tip[2])
            yield from self.reach(observation, aside, open_force)
            observation = yield Settle(open_force)
        tip = self.tip_of(observation)
        yield from self.reach(observation, (tip[0], tip[1], RETREAT_Z_M), open_force)

    def regrip(self, observation: Observation, index: int) -> Plan:
        self.note(f"regripping on link {index}")
        yield from self.release(observation)
        observation = yield Settle(self.config.control.open_force_n)
        quiet_chunks = max(1, self.knobs.quiet_steps // self.chunk_steps)
        yield from self.hold(observation, self.config.control.open_force_n, quiet_chunks)
        observation = yield Settle(self.config.control.open_force_n)
        yield from self.grasp(observation, index)

    def transport(self, observation: Observation, target: Vector, force: float) -> Plan:
        """Carry the held cable by lifting to the transport height before translating.

        A straight diagonal from a floor-level grasp passes through the clip gate below
        the post tops and wedges the trailing strand; the working motion has always been
        lift first, then sweep across at height.
        """
        tip = self.tip_of(observation)
        if target[2] > tip[2]:
            yield from self.reach(observation, (tip[0], tip[1], target[2]), force)
            observation = yield Settle(force)
        yield from self.reach(observation, target, force)

    def pull_through(self, observation: Observation, clip_index: int) -> Plan:
        centre = self.config.layout.clip_centres()[clip_index]
        past = centre[1] + self.knobs.pull_past_m
        force = self.knobs.close_force_n

        self.stage = TaskStage.ROUTE_CLIP_1 if clip_index == 0 else TaskStage.ROUTE_CLIP_2
        yield from self.transport(observation, (centre[0], past, self.knobs.route_z_m), force)
        observation = yield Settle(force)
        yield from self.reach(observation, (centre[0], past, self.knobs.settle_tip_z_m), force)
        observation = yield Settle(force)

        self.stage = TaskStage.VERIFY_CLIP_1 if clip_index == 0 else TaskStage.VERIFY_CLIP_2
        crossings = self.crossings_in_gate(observation, centre)
        if crossings < 1:
            code = ReasonCode.CLIP_1_MISSED if clip_index == 0 else ReasonCode.CLIP_2_MISSED
            raise PolicyAbortError(code, f"no qualifying crossing at gate {centre}")
        self.note(f"{crossings} crossing(s) in gate")

    def crossings_in_gate(self, observation: Observation, centre: tuple[float, float]) -> int:
        layout = self.config.layout
        half_gap = layout.clip_gap_m / 2.0 - self.config.cable.radius_m
        max_z = self.config.thresholds.gate_link_z_m
        found = 0
        rows = observation.cable_rows
        for near, far in pairwise(rows):
            if (near[1] - centre[1]) * (far[1] - centre[1]) > 0.0:
                continue
            span = far[1] - near[1]
            t = 0.5 if abs(span) < 1e-9 else (centre[1] - near[1]) / span
            x_at = near[0] + t * (far[0] - near[0])
            z_at = near[2] + t * (far[2] - near[2])
            if abs(x_at - centre[0]) < half_gap and z_at < max_z:
                found += 1
        return found

    def insert(self, observation: Observation) -> Plan:
        layout = self.config.layout
        force = self.knobs.close_force_n
        cap = self.knobs.align_step_cap_m

        self.stage = TaskStage.ALIGN_CONNECTOR
        approach_y = layout.socket_y - self.knobs.mouth_entry_m
        yield from self.transport(
            observation, (layout.socket_x, approach_y, self.knobs.insert_carry_z_m), force
        )
        observation = yield Settle(force)

        for attempt in range(self.knobs.align_corrections):
            connector = observation.cable_rows[-1]
            offset_x = max(-cap, min(cap, connector[0] - layout.socket_x))
            offset_y = max(-cap, min(cap, connector[1] - approach_y))
            self.note(
                f"correction {attempt + 1}: offset "
                f"({offset_x * 1000:+.1f}, {offset_y * 1000:+.1f}) mm"
            )
            tip = self.tip_of(observation)
            yield from self.reach(
                observation,
                (tip[0] - offset_x, tip[1] - offset_y, self.knobs.insert_carry_z_m),
                force,
            )
            observation = yield Settle(force)

        connector = observation.cable_rows[-1]
        self.note(
            f"pre-plunge connector offset "
            f"({(connector[0] - layout.socket_x) * 1000:+.1f}, "
            f"{(connector[1] - layout.socket_y) * 1000:+.1f}) mm at z {connector[2] * 1000:.1f}"
        )
        self.stage = TaskStage.INSERT_CONNECTOR
        tip = self.tip_of(observation)
        yield from self.reach(observation, (tip[0], tip[1], self.knobs.insert_z_m), force)
        observation = yield Settle(force)
        connector = observation.cable_rows[-1]
        self.note(
            f"post-plunge connector offset "
            f"({(connector[0] - layout.socket_x) * 1000:+.1f}, "
            f"{(connector[1] - layout.socket_y) * 1000:+.1f}) mm at z {connector[2] * 1000:.1f}"
        )
        for _ in range(SEAT_PUSH_ROUNDS):
            connector = observation.cable_rows[-1]
            push_x = max(-SEAT_PUSH_CAP_M, min(SEAT_PUSH_CAP_M, connector[0] - layout.socket_x))
            push_y = max(-SEAT_PUSH_CAP_M, min(SEAT_PUSH_CAP_M, connector[1] - layout.socket_y))
            if abs(push_x) <= SEAT_PUSH_DONE_M and abs(push_y) <= SEAT_PUSH_DONE_M:
                break
            self.note(f"seat push ({-push_x * 1000:+.1f}, {-push_y * 1000:+.1f}) mm in-channel")
            tip = self.tip_of(observation)
            yield from self.reach(
                observation, (tip[0] - push_x, tip[1] - push_y, self.knobs.insert_z_m), force
            )
            observation = yield Settle(force)
        yield from self.release(observation, terminal=True)
        observation = yield Settle(self.config.control.open_force_n)
        connector = observation.cable_rows[-1]
        self.note(
            f"post-release connector offset "
            f"({(connector[0] - layout.socket_x) * 1000:+.1f}, "
            f"{(connector[1] - layout.socket_y) * 1000:+.1f}) mm at z {connector[2] * 1000:.1f}"
        )
        if self.knobs.nudge_seat:
            observation = yield from self.nudge_home(observation)

        self.stage = TaskStage.VERIFY_SEATED
        yield from self.hold(observation, self.config.control.open_force_n, SEAT_SETTLE_CHUNKS)
        observation = yield Settle(self.config.control.open_force_n)
        self.finish_seated(observation)

    def nudge_home(
        self, observation: Observation
    ) -> Generator[Directive, Observation, Observation]:
        """Seat the free connector by pushing it along the channel with closed fingertips.

        The open gripper is wider than the channel and stalls on the wall front, but the
        closed fingers fit; a plug is seated the way a person does it, with a fingertip.
        """
        layout = self.config.layout
        catch = self.config.control.catch_force_n
        head = observation.cable_rows[-1]
        self.note(f"nudge: head at ({head[0]:+.3f},{head[1]:+.3f},{head[2] * 1000:.0f}mm)")
        behind = (head[0], head[1] - NUDGE_BEHIND_M, NUDGE_HOVER_Z_M)
        yield from self.reach(observation, behind, catch)
        observation = yield Settle(catch)
        yield from self.reach(observation, (behind[0], behind[1], self.knobs.insert_z_m), catch)
        observation = yield Settle(catch)
        target_y = layout.socket_y - NUDGE_STOP_SHORT_M
        yield from self.reach(
            observation, (layout.socket_x, target_y, self.knobs.insert_z_m), catch
        )
        observation = yield Settle(catch)
        tip = self.tip_of(observation)
        yield from self.reach(observation, (tip[0], tip[1], RETREAT_Z_M), catch)
        observation = yield Settle(self.config.control.open_force_n)
        return observation

    def seat_metrics(self, observation: Observation) -> tuple[bool, float, float]:
        layout = self.config.layout
        thresholds = self.config.thresholds
        connector = observation.cable_rows[-1]
        lateral = max(abs(connector[0] - layout.socket_x), abs(connector[1] - layout.socket_y))
        depth = connector[2]
        seated = lateral < thresholds.seat_lateral_m and depth < thresholds.seat_z_m
        return seated, lateral, depth

    def finish_seated(self, observation: Observation) -> None:
        seated, lateral, depth = self.seat_metrics(observation)
        self.note(f"connector lateral {lateral * 1000:.1f} mm, tip z {depth * 1000:.1f} mm")
        if seated:
            return
        code = (
            ReasonCode.CONNECTOR_MISALIGNED
            if lateral >= self.config.thresholds.seat_lateral_m
            else ReasonCode.INCOMPLETE_INSERTION
        )
        raise PolicyAbortError(
            code, f"lateral {lateral * 1000:.1f} mm, tip z {depth * 1000:.1f} mm"
        )

    def run(self, observation: Observation) -> Plan:
        seat_lateral: float | None = None
        seat_depth: float | None = None
        try:
            self.stage = TaskStage.OBSERVE
            grasp = observation.cable_rows[self.grasp_index()]
            self.note(f"grasp link at ({grasp[0]:+.3f}, {grasp[1]:+.3f})")

            self.stage = TaskStage.CLOSE_GRIPPER
            yield from self.grasp(observation, self.grasp_index())
            self.stage = TaskStage.VERIFY_GRASP
            self.note("grasp verified")

            observation = yield Settle(self.knobs.close_force_n)
            yield from self.pull_through(observation, 0)
            observation = yield Settle(self.knobs.close_force_n)
            if not self.knobs.skip_mid_regrip:
                yield from self.regrip(observation, self.mid_regrip_index())
                observation = yield Settle(self.knobs.close_force_n)
            yield from self.pull_through(observation, 1)
            observation = yield Settle(self.knobs.close_force_n)
            if not self.knobs.skip_insert_regrip:
                yield from self.regrip(observation, self.insert_index())
                observation = yield Settle(self.knobs.close_force_n)
            yield from self.insert(observation)
        except PolicyAbortError as abort:
            self.note(f"FAILED {abort.code}: {abort.detail}")
            if self.stage is TaskStage.VERIFY_SEATED:
                _, seat_lateral, seat_depth = self.seat_metrics(observation)
            yield Finish(abort.code, self.stage, tuple(self.notes), seat_lateral, seat_depth)
            return
        _, seat_lateral, seat_depth = self.seat_metrics(observation)
        yield Finish(
            ReasonCode.SUCCESS, TaskStage.VERIFY_SEATED, tuple(self.notes), seat_lateral, seat_depth
        )
