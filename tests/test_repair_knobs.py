from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from crux.repair.knobs import ControllerKnobs
from crux.simulation.taskconfig import load_task_config

CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "task.yaml"


def baseline() -> ControllerKnobs:
    return ControllerKnobs.baseline(load_task_config(CONFIG_PATH))


def test_baseline_knobs_mirror_the_shipped_config() -> None:
    config = load_task_config(CONFIG_PATH)
    knobs = ControllerKnobs.baseline(config)
    assert knobs.close_force_n == config.control.close_force_n
    assert knobs.route_z_m == config.control.route_z_m
    assert knobs.insert_z_m == config.control.insert_z_m
    assert knobs.drag_speed_mps == config.control.drag_speed_mps
    assert knobs.timeout_steps == config.thresholds.timeout_steps


def test_baseline_inserts_from_the_same_link_it_routes_with() -> None:
    knobs = baseline()
    assert knobs.insert_link_from_end == knobs.grasp_link_from_end


def test_link_indices_count_back_from_the_connector() -> None:
    knobs = baseline().with_overrides({"grasp_link_from_end": 3, "insert_link_from_end": 1})
    assert knobs.grasp_index(16) == 12
    assert knobs.insert_index(16) == 14


def test_tip_hold_targets_the_connector_link() -> None:
    knobs = baseline().with_overrides({"insert_link_from_end": 0})
    assert knobs.insert_index(16) == 15


def test_link_index_rejects_a_cable_that_is_too_short() -> None:
    knobs = baseline().with_overrides({"grasp_link_from_end": 9})
    with pytest.raises(ValueError, match="does not exist"):
        knobs.grasp_index(4)


def test_overrides_reject_unknown_knobs() -> None:
    with pytest.raises(ValueError, match="unknown knobs"):
        baseline().with_overrides({"grip_strength": 1.0})


def test_overrides_are_validated() -> None:
    with pytest.raises(ValidationError):
        baseline().with_overrides({"close_force_n": 5.0})


def test_changes_from_reports_only_what_moved() -> None:
    base = baseline()
    changed = base.with_overrides({"insert_link_from_end": 1})
    assert changed.changes_from(base) == {"insert_link_from_end": 1}
    assert base.changes_from(base) == {}
