from __future__ import annotations

from dataclasses import dataclass, field
from math import atan2, sqrt

from crux.failures.taxonomy import ReasonCode, TaskStage
from crux.repair.knobs import ControllerKnobs
from crux.simulation.gate1 import to_rows
from crux.simulation.rig import TOOL_DOWN_QUAT, tool_down_yaw_quat
from crux.simulation.taskscene import TaskScene

CONVERGED_GAP_M = 0.0002
HOLD_RAMP_STEPS = 60
RELEASE_STEPS = 80
RETREAT_Z_M = 0.080


class StageError(Exception):
    def __init__(self, code: ReasonCode, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class EpisodeOutcome:
    reason_code: ReasonCode
    task_stage: TaskStage
    steps: int
    notes: tuple[str, ...]
    seat_lateral_m: float | None = None
    seat_depth_m: float | None = None


@dataclass(slots=True)
class BaselineController:
    scene: TaskScene
    knobs: ControllerKnobs
    stage: TaskStage = TaskStage.OBSERVE
    held_link: int | None = field(default=None, init=False)
    tool_quat: tuple[float, float, float, float] = field(default=TOOL_DOWN_QUAT, init=False)
    notes: list[str] = field(default_factory=list, init=False)

    @property
    def close_force_n(self) -> float:
        return self.knobs.close_force_n

    def grasp_index(self) -> int:
        return self.knobs.grasp_index(self.scene.config.cable.segments)

    def insert_index(self) -> int:
        return self.knobs.insert_index(self.scene.config.cable.segments)

    def mid_regrip_index(self) -> int:
        segments = self.scene.config.cable.segments
        index = self.grasp_index() + self.knobs.regrip_link_delta
        if index < 0 or index >= segments:
            raise StageError(
                ReasonCode.MISSED_GRASP,
                f"regrip link {index} out of range for {segments} segments",
            )
        return index

    def note(self, message: str) -> None:
        self.notes.append(f"{self.stage}: {message}")
        print(f"    [{self.stage}] {message}", flush=True)

    def hand_tip(self) -> list[float]:
        hand = to_rows(getattr(self.scene.hand, "get_pos")())[0]
        return [hand[0], hand[1], hand[2] - self.scene.config.control.hand_to_tip_m]

    def link_pos(self, index: int) -> list[float]:
        return list(self.scene.cable_rows()[index])

    def monitor(self, _elapsed: int) -> None:
        scene = self.scene
        thresholds = scene.config.thresholds
        if not scene.cable_is_finite():
            raise StageError(ReasonCode.UNSTABLE_SIMULATION, "non-finite cable state")
        tension = scene.cable_tension_proxy_n()
        if tension > thresholds.tension_n:
            raise StageError(
                ReasonCode.OVER_TENSION, f"cable contact {tension:.1f} N > {thresholds.tension_n}"
            )
        collision = scene.arm_collision_n()
        if collision > thresholds.arm_collision_n:
            raise StageError(
                ReasonCode.ROBOT_COLLISION,
                f"arm link contact {collision:.1f} N > {thresholds.arm_collision_n}",
            )
        if self.held_link is not None:
            tip = self.hand_tip()
            link = self.link_pos(self.held_link)
            distance = sqrt(sum((a - b) ** 2 for a, b in zip(link, tip, strict=True)))
            if distance > thresholds.slip_distance_m:
                raise StageError(
                    ReasonCode.CABLE_SLIP,
                    f"held link {self.held_link} is {distance * 1000:.0f} mm from the "
                    f"fingertips (gap {scene.pinch_gap_m() * 1000:.1f} mm)",
                )

    def check_timeout(self) -> None:
        if self.scene.steps_taken > self.knobs.timeout_steps:
            raise StageError(ReasonCode.TIMEOUT, f"exceeded {self.knobs.timeout_steps} steps")

    def travel_tip(self, x: float, y: float, tip_z: float, finger_force: float) -> None:
        scene = self.scene
        control = scene.config.control
        target = (x, y, tip_z + control.hand_to_tip_m)
        hand = to_rows(getattr(scene.hand, "get_pos")())[0]
        distance = sqrt(sum((a - b) ** 2 for a, b in zip(hand, target, strict=True)))
        steps = max(
            control.travel_steps,
            int(distance / (self.knobs.drag_speed_mps * scene.timestep_s)) + 1,
        )
        scene.arm.move_to(
            target, scene.hand, finger_force, steps, self.monitor, quat=self.tool_quat
        )
        scene.count_steps(steps)
        self.check_timeout()

    def local_yaw(self, index: int) -> float:
        rows = self.scene.cable_rows()
        low = max(0, index - 1)
        high = min(len(rows) - 1, index + 1)
        return atan2(rows[high][1] - rows[low][1], rows[high][0] - rows[low][0])

    def grasp_link(self, index: int) -> None:
        scene = self.scene
        control = scene.config.control
        thresholds = scene.config.thresholds
        self.tool_quat = tool_down_yaw_quat(self.local_yaw(index))
        target = self.link_pos(index)
        self.travel_tip(target[0], target[1], control.hover_z_m, control.open_force_n)
        if self.knobs.reaim_before_pinch:
            if self.knobs.hover_settle_steps:
                scene.arm.run(self.knobs.hover_settle_steps)
                scene.count_steps(self.knobs.hover_settle_steps)
            self.tool_quat = tool_down_yaw_quat(self.local_yaw(index))
            target = self.link_pos(index)
            self.travel_tip(target[0], target[1], control.hover_z_m, control.open_force_n)
        target = self.link_pos(index)
        self.travel_tip(target[0], target[1], scene.config.cable.radius_m, control.open_force_n)
        if self.knobs.reaim_before_pinch:
            target = self.link_pos(index)
            self.travel_tip(target[0], target[1], scene.config.cable.radius_m, control.open_force_n)

        scene.arm.command(scene.arm.joint_targets(scene.arm.get_qpos()), control.catch_force_n)
        previous = scene.pinch_gap_m()
        for _ in range(control.close_chunks_max):
            scene.arm.run(control.chunk_steps * 2, self.monitor)
            scene.count_steps(control.chunk_steps * 2)
            gap = scene.pinch_gap_m()
            if abs(previous - gap) < CONVERGED_GAP_M:
                break
            previous = gap
        gap = scene.pinch_gap_m()
        if not thresholds.pinch_min_m < gap < thresholds.pinch_max_m:
            raise StageError(
                ReasonCode.MISSED_GRASP,
                f"pinch gap {gap * 1000:.1f} mm on link {index} outside "
                f"[{thresholds.pinch_min_m * 1000:.0f}, {thresholds.pinch_max_m * 1000:.0f}] mm",
            )
        scene.arm.command(scene.arm.joint_targets(scene.arm.get_qpos()), self.close_force_n)
        scene.arm.run(HOLD_RAMP_STEPS, self.monitor)
        scene.count_steps(HOLD_RAMP_STEPS)
        self.held_link = index
        self.note(f"holding link {index} (gap {gap * 1000:.1f} mm)")
        self.check_timeout()

    def release(self) -> None:
        scene = self.scene
        control = scene.config.control
        self.held_link = None
        scene.arm.command(scene.arm.joint_targets(scene.arm.get_qpos()), control.open_force_n)
        scene.arm.run(RELEASE_STEPS)
        scene.count_steps(RELEASE_STEPS)
        tip = self.hand_tip()
        self.travel_tip(tip[0], tip[1], RETREAT_Z_M, control.open_force_n)

    def run_episode(self) -> EpisodeOutcome:
        try:
            self._observe()
            self._grasp_end()
            self._pull_through(TaskStage.ROUTE_CLIP_1, TaskStage.VERIFY_CLIP_1, 0)
            if not self.knobs.skip_mid_regrip:
                self._regrip(self.mid_regrip_index())
            self._pull_through(TaskStage.ROUTE_CLIP_2, TaskStage.VERIFY_CLIP_2, 1)
            self._regrip(self.insert_index())
            return self._insert()
        except StageError as failure:
            self.note(f"FAILED {failure.code}: {failure.detail}")
            lateral: float | None = None
            depth: float | None = None
            if self.stage is TaskStage.VERIFY_SEATED:
                _, lateral, depth = self.scene.connector_seated()
            return EpisodeOutcome(
                failure.code,
                self.stage,
                self.scene.steps_taken,
                tuple(self.notes),
                seat_lateral_m=lateral,
                seat_depth_m=depth,
            )

    def _observe(self) -> None:
        self.stage = TaskStage.OBSERVE
        grasp = self.link_pos(self.grasp_index())
        self.note(f"grasp link at ({grasp[0]:+.3f}, {grasp[1]:+.3f})")

    def _regrip(self, index: int) -> None:
        self.note(f"regripping on link {index} to reset contact creep")
        self.release()
        self.scene.arm.run(self.knobs.quiet_steps)
        self.scene.count_steps(self.knobs.quiet_steps)
        self.grasp_link(index)

    def _grasp_end(self) -> None:
        self.stage = TaskStage.APPROACH_CABLE
        self.stage = TaskStage.CLOSE_GRIPPER
        self.grasp_link(self.grasp_index())
        self.stage = TaskStage.VERIFY_GRASP
        self.note("grasp verified")

    def _pull_through(self, route: TaskStage, verify: TaskStage, clip_index: int) -> None:
        scene = self.scene
        centre = scene.config.layout.clip_centres()[clip_index]
        past = centre[1] + self.knobs.pull_past_m

        self.stage = route
        self.travel_tip(centre[0], past, self.knobs.route_z_m, self.close_force_n)
        self.travel_tip(centre[0], past, self.knobs.settle_tip_z_m, self.close_force_n)

        self.stage = verify
        in_gate = scene.links_in_gate(centre)
        if in_gate < 1:
            code = ReasonCode.CLIP_1_MISSED if clip_index == 0 else ReasonCode.CLIP_2_MISSED
            crossings = ", ".join(
                f"(x {x * 1000:+.1f}, z {z * 1000:.1f})" for x, z in scene.gate_crossings(centre)
            )
            cable = " ".join(
                f"({row[0] * 1000:.0f},{row[1] * 1000:.0f},{row[2] * 1000:.0f})"
                for row in scene.cable_rows()
            )
            raise StageError(
                code,
                f"no qualifying crossing at gate {centre}; plane crossings mm: "
                f"[{crossings or 'none'}]; cable links mm: {cable}",
            )
        self.note(f"{in_gate} crossing(s) in gate")

    def _insert(self) -> EpisodeOutcome:
        scene = self.scene
        layout = scene.config.layout
        cap = self.knobs.align_step_cap_m
        carry_z = self.knobs.insert_carry_z_m

        self.stage = TaskStage.ALIGN_CONNECTOR
        tip = self.hand_tip()
        self.travel_tip(tip[0], tip[1], carry_z, self.close_force_n)
        self.travel_tip(layout.socket_x, layout.socket_y, carry_z, self.close_force_n)
        for attempt in range(self.knobs.align_corrections):
            connector = scene.connector_pos()
            offset_x = max(-cap, min(cap, connector[0] - layout.socket_x))
            offset_y = max(-cap, min(cap, connector[1] - layout.socket_y))
            self.note(
                f"correction {attempt + 1}: connector offset "
                f"({offset_x * 1000:+.1f}, {offset_y * 1000:+.1f}) mm"
            )
            tip = self.hand_tip()
            self.travel_tip(tip[0] - offset_x, tip[1] - offset_y, carry_z, self.close_force_n)

        self.stage = TaskStage.INSERT_CONNECTOR
        tip = self.hand_tip()
        self.travel_tip(tip[0], tip[1], self.knobs.insert_z_m, self.close_force_n)
        self.release()

        self.stage = TaskStage.VERIFY_SEATED
        seated, lateral, depth = scene.connector_seated()
        self.note(f"connector lateral {lateral * 1000:.1f} mm, tip z {depth * 1000:.1f} mm")
        if seated:
            self.note("connector seated")
            return EpisodeOutcome(
                ReasonCode.SUCCESS,
                TaskStage.VERIFY_SEATED,
                scene.steps_taken,
                tuple(self.notes),
                seat_lateral_m=lateral,
                seat_depth_m=depth,
            )
        if lateral >= scene.config.thresholds.seat_lateral_m:
            raise StageError(
                ReasonCode.CONNECTOR_MISALIGNED,
                f"lateral offset {lateral * 1000:.1f} mm at socket",
            )
        raise StageError(
            ReasonCode.INCOMPLETE_INSERTION,
            f"connector tip z {depth * 1000:.1f} mm above seat depth",
        )
