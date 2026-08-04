from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import genesis as gs
import torch

from crux.control.directives import Observation
from crux.errors import BackendError, ErrorCode
from crux.simulation.cable import build_cable_urdf
from crux.simulation.gate1 import TIMESTEP_S
from crux.simulation.recording import frame_interval, recording_step
from crux.simulation.rig import ARM_DOFS, ARM_IDX, FINGER_IDX, FINGER_LINK_NAMES, HOME_QPOS
from crux.simulation.taskconfig import TaskConfig
from crux.simulation.taskscene import FRANKA_MJCF, TASK_URDF_PATH, _add_clip, _add_socket

Rows = tuple[tuple[float, float, float], ...]


@dataclass(slots=True)
class BatchTaskScene:
    config: TaskConfig
    scene: object
    cable: object
    franka: object
    hand: object
    n_envs: int
    device: torch.device
    camera: object | None = None

    @property
    def timestep_s(self) -> float:
        return TIMESTEP_S

    def _tensor(self, values: list[list[float]]) -> torch.Tensor:
        return torch.tensor(values, dtype=torch.float32, device=self.device)

    def cable_positions(self) -> torch.Tensor:
        return getattr(self.cable, "get_links_pos")()

    def hand_positions(self) -> torch.Tensor:
        return getattr(self.hand, "get_pos")()

    def finger_gaps(self) -> torch.Tensor:
        left = getattr(self.franka, "get_link")(FINGER_LINK_NAMES[0]).get_pos()
        right = getattr(self.franka, "get_link")(FINGER_LINK_NAMES[1]).get_pos()
        return torch.linalg.vector_norm(left - right, dim=-1)

    def contact_magnitudes(self, entity: object) -> torch.Tensor:
        forces = getattr(entity, "get_links_net_contact_force")()
        return torch.linalg.vector_norm(forces, dim=-1)

    def observations(self, steps_taken: int, held: list[int | None]) -> list[Observation]:
        cable = self.cable_positions().detach().cpu()
        hands = self.hand_positions().detach().cpu()
        gaps = self.finger_gaps().detach().cpu()
        cable_contact = self.contact_magnitudes(self.cable).detach().cpu()
        arm_contact = self.contact_magnitudes(self.franka).detach().cpu()
        finite = torch.isfinite(cable).all(dim=-1).all(dim=-1)

        observations: list[Observation] = []
        for env in range(self.n_envs):
            rows = tuple(tuple(float(value) for value in row) for row in cable[env])
            link = held[env]
            observations.append(
                Observation(
                    cable_rows=rows,  # type: ignore[arg-type]
                    hand_pos=(
                        float(hands[env][0]),
                        float(hands[env][1]),
                        float(hands[env][2]),
                    ),
                    pinch_gap_m=float(gaps[env]),
                    cable_contact_n=float(cable_contact[env].max()),
                    arm_contact_n=float(arm_contact[env][1 : ARM_DOFS + 1].max()),
                    held_link_contact_n=float(cable_contact[env][link])
                    if link is not None
                    else 0.0,
                    steps_taken=steps_taken,
                    cable_is_finite=bool(finite[env]),
                )
            )
        return observations

    def arm_qpos(self) -> torch.Tensor:
        return getattr(self.franka, "get_qpos")()[:, :ARM_DOFS]

    def solve_ik(self, positions: list[list[float]], quats: list[list[float]]) -> torch.Tensor:
        solved = getattr(self.franka, "inverse_kinematics")(
            link=self.hand, pos=self._tensor(positions), quat=self._tensor(quats)
        )
        return solved[:, :ARM_DOFS]

    def command(
        self,
        arm_targets: torch.Tensor,
        finger_forces: list[float],
        hold_current: list[bool] | None = None,
    ) -> None:
        if hold_current is not None and any(hold_current):
            mask = torch.tensor(hold_current, dtype=torch.bool, device=self.device)
            arm_targets = torch.where(mask.unsqueeze(-1), self.arm_qpos(), arm_targets)
        getattr(self.franka, "control_dofs_position")(arm_targets, ARM_IDX)
        forces = self._tensor([[force, force] for force in finger_forces])
        getattr(self.franka, "control_dofs_force")(forces, FINGER_IDX)

    step_fn: object | None = None

    def step(self, times: int) -> None:
        runner = self.step_fn if callable(self.step_fn) else getattr(self.scene, "step")
        for _ in range(times):
            runner()

    def reset_all(self, offsets: list[tuple[float, float]]) -> None:
        getattr(self.scene, "reset")()
        base = self.config.layout.cable_base
        positions = [[base[0] + offset[0], base[1] + offset[1], base[2]] for offset in offsets]
        getattr(self.cable, "set_pos")(self._tensor(positions))
        home = self._tensor([list(HOME_QPOS) for _ in range(self.n_envs)])
        getattr(self.franka, "set_qpos")(home)
        self.command(home[:, :ARM_DOFS], [self.config.control.open_force_n] * self.n_envs)
        self.step(self.config.control.settle_steps)


def build_batch_scene(config: TaskConfig, n_envs: int, record: bool = False) -> BatchTaskScene:
    TASK_URDF_PATH.parent.mkdir(parents=True, exist_ok=True)
    Path(TASK_URDF_PATH).write_text(build_cable_urdf(config.cable), encoding="utf-8")

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
    camera = None
    if record:
        render = config.render
        camera = getattr(scene, "add_camera")(
            res=(render.width, render.height),
            pos=render.camera_pos,
            lookat=render.camera_lookat,
            fov=render.fov_deg,
        )
    scene.build(n_envs=n_envs)

    hand = getattr(franka, "get_link")("hand")
    device = getattr(cable, "get_links_pos")().device
    built = BatchTaskScene(
        config=config,
        scene=scene,
        cable=cable,
        franka=franka,
        hand=hand,
        n_envs=n_envs,
        device=device,
        camera=camera,
    )
    if camera is not None:
        raw_step = getattr(scene, "step")
        stepped = recording_step(
            raw_step, getattr(camera, "render"), frame_interval(config.render.fps, TIMESTEP_S)
        )
        built.step_fn = stepped
    return built
