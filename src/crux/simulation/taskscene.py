from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path

import genesis as gs

from crux.errors import BackendError, ErrorCode
from crux.simulation.cable import build_cable_urdf
from crux.simulation.gate1 import TIMESTEP_S, Rows, read_link_positions
from crux.simulation.rig import (
    ARM_DOFS,
    Arm,
    build_rig_arm,
    contact_peak,
    find_hand_link,
    finger_gap_m,
    per_link_contact,
    rows_are_finite,
)
from crux.simulation.taskconfig import LayoutConfig, TaskConfig

FRANKA_MJCF = "xml/franka_emika_panda/panda.xml"
TASK_URDF_PATH = Path("build/task_cable.urdf")


@dataclass(slots=True)
class TaskScene:
    config: TaskConfig
    scene: object
    cable: object
    franka: object
    hand: object
    arm: Arm
    peak_tension_n: float = 0.0
    peak_arm_contact_n: float = 0.0
    _step_count: int = field(default=0, init=False)

    @property
    def timestep_s(self) -> float:
        return TIMESTEP_S

    @property
    def steps_taken(self) -> int:
        return self._step_count

    def count_steps(self, steps: int) -> None:
        self._step_count += steps

    def cable_rows(self) -> Rows:
        return read_link_positions(self.cable)

    def connector_pos(self) -> list[float]:
        return list(self.cable_rows()[-1])

    def grasp_link_pos(self) -> list[float]:
        return list(self.cable_rows()[self.config.grasp_link_index()])

    def pinch_gap_m(self) -> float:
        return finger_gap_m(self.franka)

    def link_contact_n(self, index: int) -> float:
        return per_link_contact(self.cable)[index]

    def cable_tension_proxy_n(self) -> float:
        value = contact_peak(self.cable)
        self.peak_tension_n = max(self.peak_tension_n, value)
        return value

    def arm_collision_n(self) -> float:
        forces = per_link_contact(self.franka)
        value = max(forces[1 : ARM_DOFS + 1])
        self.peak_arm_contact_n = max(self.peak_arm_contact_n, value)
        return value

    def cable_is_finite(self) -> bool:
        return rows_are_finite(self.cable_rows())

    def gate_crossings(self, centre: tuple[float, float]) -> list[tuple[float, float]]:
        rows = self.cable_rows()
        crossings: list[tuple[float, float]] = []
        for near, far in pairwise(rows):
            dy_near = near[1] - centre[1]
            dy_far = far[1] - centre[1]
            if dy_near * dy_far > 0.0:
                continue
            span = dy_far - dy_near
            t = 0.5 if abs(span) < 1e-9 else -dy_near / span
            x_at = near[0] + t * (far[0] - near[0])
            z_at = near[2] + t * (far[2] - near[2])
            crossings.append((x_at, z_at))
        return crossings

    def links_in_gate(self, centre: tuple[float, float]) -> int:
        layout = self.config.layout
        half_gap = layout.clip_gap_m / 2.0 - self.config.cable.radius_m
        max_z = self.config.thresholds.gate_link_z_m
        return sum(
            1
            for x_at, z_at in self.gate_crossings(centre)
            if abs(x_at - centre[0]) < half_gap and z_at < max_z
        )

    def connector_seated(self) -> tuple[bool, float, float]:
        layout = self.config.layout
        thresholds = self.config.thresholds
        connector = self.connector_pos()
        lateral = max(abs(connector[0] - layout.socket_x), abs(connector[1] - layout.socket_y))
        depth = connector[2]
        seated = lateral < thresholds.seat_lateral_m and depth < thresholds.seat_z_m
        return seated, lateral, depth

    def reset(self, cable_offset: tuple[float, float]) -> None:
        getattr(self.scene, "reset")()
        base = self.config.layout.cable_base
        getattr(self.cable, "set_pos")(
            [base[0] + cable_offset[0], base[1] + cable_offset[1], base[2]]
        )
        self.arm.home(self.config.control.open_force_n)
        self.arm.run(self.config.control.settle_steps)
        self.peak_tension_n = 0.0
        self.peak_arm_contact_n = 0.0
        self._step_count = 0


def _add_box(
    scene: object, pos: tuple[float, float, float], size: tuple[float, float, float]
) -> object:
    return getattr(scene, "add_entity")(gs.morphs.Box(pos=pos, size=size, fixed=True))


def _add_clip(scene: object, layout: LayoutConfig, centre: tuple[float, float]) -> None:
    half = layout.clip_gap_m / 2.0 + layout.clip_post_m / 2.0
    size = (layout.clip_post_m, layout.clip_post_m, layout.clip_height_m)
    for side in (-1.0, 1.0):
        _add_box(
            scene,
            (centre[0] + side * half, centre[1], layout.clip_height_m / 2.0),
            size,
        )


def _add_socket(scene: object, layout: LayoutConfig) -> None:
    x, y = layout.socket_x, layout.socket_y
    width, depth = layout.socket_width_m, layout.socket_depth_m
    wall, height = layout.socket_wall_m, layout.socket_height_m
    half_h = height / 2.0
    outer_x = width + 2.0 * wall
    for side in (-1.0, 1.0):
        _add_box(
            scene,
            (x + side * (width / 2.0 + wall / 2.0), y, half_h),
            (wall, depth, height),
        )
        _add_box(
            scene,
            (x, y + side * (depth / 2.0 + wall / 2.0), half_h),
            (outer_x, wall, height),
        )


def build_task_scene(config: TaskConfig) -> TaskScene:
    TASK_URDF_PATH.parent.mkdir(parents=True, exist_ok=True)
    TASK_URDF_PATH.write_text(build_cable_urdf(config.cable), encoding="utf-8")

    gs.init(backend=gs.amdgpu)
    if gs.backend != gs.amdgpu:
        raise BackendError(
            ErrorCode.BACKEND_NOT_RADEON, f"Genesis resolved to {gs.backend!r}, not gs.amdgpu"
        )
    scene = gs.Scene(sim_options=gs.options.SimOptions(dt=TIMESTEP_S), show_viewer=False)
    scene.add_entity(gs.morphs.Plane())
    cable = scene.add_entity(
        gs.morphs.URDF(
            file=str(TASK_URDF_PATH.resolve()),
            pos=config.layout.cable_base,
            euler=(0.0, 0.0, config.layout.cable_yaw_deg),
        )
    )
    for centre in config.layout.clip_centres():
        _add_clip(scene, config.layout, centre)
    _add_socket(scene, config.layout)
    franka = scene.add_entity(gs.morphs.MJCF(file=FRANKA_MJCF))
    scene.build()

    arm = build_rig_arm(scene, franka, config.control.chunk_steps)
    hand = find_hand_link(franka)
    return TaskScene(config=config, scene=scene, cable=cable, franka=franka, hand=hand, arm=arm)
