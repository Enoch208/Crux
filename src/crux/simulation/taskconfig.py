from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import Field

from crux.schema import Frozen
from crux.simulation.cable import CableSpec

TASK_CONFIG_PATH = Path("configs/task.yaml")


class LayoutConfig(Frozen):
    cable_base: tuple[float, float, float]
    cable_yaw_deg: float
    clip1_x: float
    clip1_y: float
    clip2_x: float
    clip2_y: float
    clip_gap_m: float = Field(gt=0.0)
    clip_post_m: float = Field(gt=0.0)
    clip_height_m: float = Field(gt=0.0)
    socket_x: float
    socket_y: float
    socket_width_m: float = Field(gt=0.0)
    socket_depth_m: float = Field(gt=0.0)
    socket_wall_m: float = Field(gt=0.0)
    socket_height_m: float = Field(gt=0.0)
    socket_open_entry: bool

    def clip_centres(self) -> tuple[tuple[float, float], tuple[float, float]]:
        return ((self.clip1_x, self.clip1_y), (self.clip2_x, self.clip2_y))


class ControlConfig(Frozen):
    hand_to_tip_m: float = Field(gt=0.0)
    open_force_n: float = Field(gt=0.0)
    catch_force_n: float = Field(lt=0.0)
    close_force_n: float = Field(lt=0.0)
    hover_z_m: float = Field(gt=0.0)
    route_z_m: float = Field(gt=0.0)
    insert_z_m: float = Field(gt=0.0)
    grasp_link_from_end: int = Field(ge=1)
    drag_speed_mps: float = Field(gt=0.0)
    runway_m: float = Field(gt=0.0)
    gate_exit_m: float = Field(gt=0.0)
    press_y_m: float = Field(gt=0.0)
    press_z_m: float = Field(gt=0.0)
    travel_steps: int = Field(gt=0)
    settle_steps: int = Field(gt=0)
    close_chunks_max: int = Field(gt=0)
    chunk_steps: int = Field(gt=0)


class ThresholdConfig(Frozen):
    pinch_min_m: float = Field(gt=0.0)
    pinch_max_m: float = Field(gt=0.0)
    slip_distance_m: float = Field(gt=0.0)
    tension_n: float = Field(gt=0.0)
    arm_collision_n: float = Field(gt=0.0)
    gate_link_z_m: float = Field(gt=0.0)
    seat_lateral_m: float = Field(gt=0.0)
    seat_z_m: float = Field(gt=0.0)
    timeout_steps: int = Field(gt=0)


class RandomizationConfig(Frozen):
    cable_dx_m: float = Field(ge=0.0)
    cable_dy_m: float = Field(ge=0.0)
    close_force_jitter_n: float = Field(ge=0.0)
    route_z_jitter_m: float = Field(ge=0.0)


class RenderConfig(Frozen):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fov_deg: float = Field(gt=0.0)
    camera_pos: tuple[float, float, float]
    camera_lookat: tuple[float, float, float]
    fps: int = Field(gt=0)


class TaskConfig(Frozen):
    cable: CableSpec
    layout: LayoutConfig
    control: ControlConfig
    thresholds: ThresholdConfig
    randomization: RandomizationConfig
    render: RenderConfig

    def grasp_link_index(self) -> int:
        return self.cable.segments - 1 - self.control.grasp_link_from_end


def load_task_config(path: Path = TASK_CONFIG_PATH) -> TaskConfig:
    return TaskConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
