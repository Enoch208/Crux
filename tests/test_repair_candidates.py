from __future__ import annotations

import json
from pathlib import Path

import pytest

from crux.errors import CruxError, ErrorCode
from crux.repair.candidates import (
    BASELINE_OVERRIDES,
    V2_OVERRIDES,
    V3_OVERRIDES,
    V4_OVERRIDES,
    V5_OVERRIDES,
    knobs_for,
    overrides_for,
)
from crux.repair.knobs import ControllerKnobs
from crux.simulation.taskconfig import load_task_config

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "task.yaml"
SHIPPED_SPEC_PATH = ROOT / "evidence" / "controller" / "repaired.json"


def knobs(version: str) -> ControllerKnobs:
    return knobs_for(version, load_task_config(CONFIG_PATH))


def test_each_candidate_extends_the_one_before_it() -> None:
    assert V2_OVERRIDES.items() <= V3_OVERRIDES.items()
    assert V3_OVERRIDES.items() <= V4_OVERRIDES.items()
    assert V4_OVERRIDES.items() <= V5_OVERRIDES.items()


def test_baseline_only_lifts_the_timeout() -> None:
    base = ControllerKnobs.baseline(load_task_config(CONFIG_PATH))
    assert knobs("baseline-v1").changes_from(base) == BASELINE_OVERRIDES


def test_v4_is_v3_plus_the_fingertip_nudge() -> None:
    assert knobs("candidate-v4").changes_from(knobs("candidate-v3")) == {
        "nudge_seat": 1,
        "nudge_stop_short_m": 0.001,
        "nudge_rounds": 2,
    }


def test_the_shipped_controller_carries_no_slip_guard() -> None:
    assert knobs("candidate-v4").slip_guard == 0


def test_v5_is_v4_plus_the_slip_guard() -> None:
    assert knobs("candidate-v5").changes_from(knobs("candidate-v4")) == {
        "slip_guard": 1,
        "slip_warn_ratio": 0.45,
        "slip_debounce_chunks": 2,
        "slip_grip_boost": 1.8,
    }


def test_overrides_are_copies_callers_cannot_mutate_the_frozen_definition() -> None:
    taken = overrides_for("candidate-v4")
    taken["nudge_rounds"] = 99
    assert V4_OVERRIDES["nudge_rounds"] == 2


def test_unknown_controller_fails_with_a_stable_code() -> None:
    with pytest.raises(CruxError) as error:
        overrides_for("candidate-v9")
    assert error.value.code is ErrorCode.CONTROLLER_UNKNOWN


def test_the_bundled_controller_spec_matches_the_code_that_produced_it() -> None:
    shipped = json.loads(SHIPPED_SPEC_PATH.read_text(encoding="utf-8"))
    assert shipped == json.loads(knobs("candidate-v4").model_dump_json())
