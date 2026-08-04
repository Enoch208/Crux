from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt

from crux.failures.taxonomy import ReasonCode, TaskStage
from crux.simulation.gate1 import to_rows
from crux.simulation.taskscene import TaskScene

ALIGN_CORRECTIONS = 2
ALIGN_DESCENT_Z_M = 0.030
CONVERGED_GAP_M = 0.0002


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


@dataclass(slots=True)
class BaselineController:
    scene: TaskScene
    close_force_n: float
    route_z_m: float
    stage: TaskStage = TaskStage.OBSERVE
    grasp_engaged: bool = field(default=False, init=False)
    notes: list[str] = field(default_factory=list, init=False)

    def note(self, message: str) -> None:
        self.notes.append(f"{self.stage}: {message}")
        print(f"    [{self.stage}] {message}", flush=True)

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
        if self.grasp_engaged:
            hand_now = to_rows(getattr(scene.hand, "get_pos")())[0]
            tip = (
                hand_now[0],
                hand_now[1],
                hand_now[2] - scene.config.control.hand_to_tip_m,
            )
            link = scene.grasp_link_pos()
            distance = sqrt(sum((a - b) ** 2 for a, b in zip(link, tip, strict=True)))
            if distance > thresholds.slip_distance_m:
                raise StageError(
                    ReasonCode.CABLE_SLIP,
                    f"grasp link {distance * 1000:.0f} mm from the fingertips "
                    f"(gap {scene.pinch_gap_m() * 1000:.1f} mm)",
                )

    def check_timeout(self) -> None:
        if self.scene.steps_taken > self.scene.config.thresholds.timeout_steps:
            raise StageError(
                ReasonCode.TIMEOUT, f"exceeded {self.scene.config.thresholds.timeout_steps} steps"
            )

    def travel_tip(self, x: float, y: float, tip_z: float, finger_force: float, steps: int) -> None:
        scene = self.scene
        control = scene.config.control
        target = (x, y, tip_z + control.hand_to_tip_m)
        hand_now = to_rows(getattr(scene.hand, "get_pos")())[0]
        distance = sqrt(sum((a - b) ** 2 for a, b in zip(hand_now, target, strict=True)))
        paced = max(steps, int(distance / (control.drag_speed_mps * scene.timestep_s)) + 1)
        scene.arm.move_to(target, scene.hand, finger_force, paced, self.monitor)
        scene.count_steps(paced)
        self.check_timeout()

    def close_until_pinch(self) -> float:
        scene = self.scene
        control = scene.config.control
        scene.arm.command(scene.arm.joint_targets(scene.arm.get_qpos()), self.close_force_n)
        previous = scene.pinch_gap_m()
        for _ in range(control.close_chunks_max):
            scene.arm.run(control.chunk_steps * 2, self.monitor)
            scene.count_steps(control.chunk_steps * 2)
            gap = scene.pinch_gap_m()
            if abs(previous - gap) < CONVERGED_GAP_M:
                break
            previous = gap
        self.check_timeout()
        return scene.pinch_gap_m()

    def run_episode(self) -> EpisodeOutcome:
        try:
            self._observe()
            self._approach_and_grasp()
            self._route_clip(TaskStage.ROUTE_CLIP_1, TaskStage.VERIFY_CLIP_1, 0)
            self._route_clip(TaskStage.ROUTE_CLIP_2, TaskStage.VERIFY_CLIP_2, 1)
            self._align_connector()
            self._insert_connector()
            self._verify_seated()
        except StageError as failure:
            self.note(f"FAILED {failure.code}: {failure.detail}")
            return EpisodeOutcome(
                failure.code, self.stage, self.scene.steps_taken, tuple(self.notes)
            )
        return EpisodeOutcome(
            ReasonCode.SUCCESS, TaskStage.VERIFY_SEATED, self.scene.steps_taken, tuple(self.notes)
        )

    def _observe(self) -> None:
        self.stage = TaskStage.OBSERVE
        grasp = self.scene.grasp_link_pos()
        self.note(f"grasp link at ({grasp[0]:+.3f}, {grasp[1]:+.3f}, {grasp[2]:+.3f})")

    def _approach_and_grasp(self) -> None:
        scene = self.scene
        control = scene.config.control
        thresholds = scene.config.thresholds
        grasp = scene.grasp_link_pos()

        self.stage = TaskStage.APPROACH_CABLE
        self.travel_tip(
            grasp[0], grasp[1], control.hover_z_m, control.open_force_n, control.travel_steps
        )
        self.travel_tip(
            grasp[0],
            grasp[1],
            scene.config.cable.radius_m,
            control.open_force_n,
            control.travel_steps,
        )

        self.stage = TaskStage.CLOSE_GRIPPER
        gap = self.close_until_pinch()
        self.note(f"pinch gap {gap * 1000:.1f} mm")

        self.stage = TaskStage.VERIFY_GRASP
        if not thresholds.pinch_min_m < gap < thresholds.pinch_max_m:
            raise StageError(
                ReasonCode.MISSED_GRASP,
                f"pinch gap {gap * 1000:.1f} mm outside "
                f"[{thresholds.pinch_min_m * 1000:.0f}, {thresholds.pinch_max_m * 1000:.0f}] mm",
            )
        self.grasp_engaged = True
        self.note("grasp verified")

    def _route_clip(self, route: TaskStage, verify: TaskStage, clip_index: int) -> None:
        scene = self.scene
        control = scene.config.control
        centre = scene.config.layout.clip_centres()[clip_index]

        self.stage = route
        grasp = scene.grasp_link_pos()
        self.travel_tip(
            grasp[0], grasp[1], self.route_z_m, self.close_force_n, control.travel_steps
        )
        self.travel_tip(
            centre[0],
            centre[1] - control.runway_m,
            self.route_z_m,
            self.close_force_n,
            control.travel_steps,
        )
        self.travel_tip(
            centre[0],
            centre[1] + control.gate_exit_m,
            self.route_z_m,
            self.close_force_n,
            control.travel_steps,
        )
        self.travel_tip(
            centre[0],
            centre[1] + control.press_y_m,
            control.press_z_m,
            self.close_force_n,
            control.travel_steps,
        )

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
        self.travel_tip(
            centre[0],
            centre[1] + control.press_y_m,
            self.route_z_m,
            self.close_force_n,
            control.travel_steps,
        )

    def _align_connector(self) -> None:
        scene = self.scene
        control = scene.config.control
        layout = scene.config.layout

        self.stage = TaskStage.ALIGN_CONNECTOR
        self.travel_tip(
            layout.socket_x,
            layout.socket_y,
            self.route_z_m,
            self.close_force_n,
            control.travel_steps,
        )
        for attempt in range(ALIGN_CORRECTIONS):
            connector = scene.connector_pos()
            offset_x = connector[0] - layout.socket_x
            offset_y = connector[1] - layout.socket_y
            self.note(
                f"correction {attempt + 1}: connector offset "
                f"({offset_x * 1000:+.1f}, {offset_y * 1000:+.1f}) mm"
            )
            grasp = scene.grasp_link_pos()
            self.travel_tip(
                grasp[0] - offset_x,
                grasp[1] - offset_y,
                self.route_z_m,
                self.close_force_n,
                control.travel_steps // 2,
            )

    def _insert_connector(self) -> None:
        scene = self.scene
        control = scene.config.control

        self.stage = TaskStage.INSERT_CONNECTOR
        grasp = scene.grasp_link_pos()
        self.travel_tip(
            grasp[0], grasp[1], ALIGN_DESCENT_Z_M, self.close_force_n, control.travel_steps
        )
        grasp = scene.grasp_link_pos()
        self.travel_tip(
            grasp[0], grasp[1], control.insert_z_m, self.close_force_n, control.travel_steps * 2
        )

    def _verify_seated(self) -> None:
        scene = self.scene
        self.stage = TaskStage.VERIFY_SEATED
        seated, lateral, depth = scene.connector_seated()
        self.note(f"connector lateral {lateral * 1000:.1f} mm, tip z {depth * 1000:.1f} mm")
        if seated:
            self.note("connector seated")
            return
        if lateral >= scene.config.thresholds.seat_lateral_m:
            raise StageError(
                ReasonCode.CONNECTOR_MISALIGNED,
                f"lateral offset {lateral * 1000:.1f} mm at socket",
            )
        raise StageError(
            ReasonCode.INCOMPLETE_INSERTION,
            f"connector tip z {depth * 1000:.1f} mm above seat depth",
        )
