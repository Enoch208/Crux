from __future__ import annotations

from math import hypot
from pathlib import Path

from crux.simulation.taskconfig import load_task_config

CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "task.yaml"


def test_shipped_task_config_is_valid() -> None:
    config = load_task_config(CONFIG_PATH)
    assert config.cable.segments >= 2
    assert config.grasp_link_index() < config.cable.segments - 1


def test_clip_gates_admit_the_cable() -> None:
    config = load_task_config(CONFIG_PATH)
    assert config.layout.clip_gap_m > 2.0 * config.cable.radius_m + 0.004


def test_socket_interior_admits_the_connector() -> None:
    config = load_task_config(CONFIG_PATH)
    assert config.layout.socket_width_m > 2.0 * config.cable.radius_m + 0.004
    assert config.layout.socket_depth_m > 2.0 * config.cable.radius_m + 0.004
    assert config.thresholds.seat_z_m < config.layout.socket_height_m


def test_route_targets_are_within_franka_reach() -> None:
    config = load_task_config(CONFIG_PATH)
    layout = config.layout
    points = [
        (layout.cable_base[0], layout.cable_base[1]),
        (layout.cable_base[0], layout.cable_base[1] + config.cable.total_length_m),
        (layout.clip1_x, layout.clip1_y),
        (layout.clip2_x, layout.clip2_y),
        (layout.socket_x, layout.socket_y),
    ]
    for x, y in points:
        assert hypot(x, y) < 0.70, f"({x}, {y}) is outside comfortable reach"


FINGER_PAD_HALF_SPAN_M = 0.010
IK_ERROR_MARGIN_M = 0.004


def test_gripper_fits_through_the_clip_gate() -> None:
    config = load_task_config(CONFIG_PATH)
    half_gap = config.layout.clip_gap_m / 2.0
    assert half_gap > FINGER_PAD_HALF_SPAN_M + IK_ERROR_MARGIN_M


def test_gate_check_height_stays_below_the_post_tops() -> None:
    config = load_task_config(CONFIG_PATH)
    assert config.thresholds.gate_link_z_m < config.layout.clip_height_m


def test_pinch_band_brackets_the_cable_diameter() -> None:
    config = load_task_config(CONFIG_PATH)
    diameter = 2.0 * config.cable.radius_m
    assert config.thresholds.pinch_min_m < diameter < config.thresholds.pinch_max_m


def test_terminal_fixture_is_open_along_the_approach_direction() -> None:
    config = load_task_config(CONFIG_PATH)
    assert config.layout.socket_open_entry
    assert config.layout.socket_y > config.layout.clip2_y


def test_slide_insert_keeps_hold_of_the_cable() -> None:
    from crux.repair.knobs import ControllerKnobs
    from crux.repair.operators import SLIDE_INSERT

    base = ControllerKnobs.baseline(load_task_config(CONFIG_PATH))
    assert base.skip_insert_regrip == 0
    repaired = SLIDE_INSERT.apply(base)
    assert repaired.skip_insert_regrip == 1
    assert repaired.insert_carry_z_m < base.insert_carry_z_m
