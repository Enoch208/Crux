from __future__ import annotations

from pathlib import Path

from crux.failures.taxonomy import FAILURE_CODES, STAGE_ORDER, ReasonCode
from crux.repair.knobs import ControllerKnobs
from crux.repair.operators import coverage, propose
from crux.simulation.taskconfig import load_task_config

CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "task.yaml"


def baseline() -> ControllerKnobs:
    return ControllerKnobs.baseline(load_task_config(CONFIG_PATH))


def test_every_failure_code_has_at_least_one_repair() -> None:
    assert set(coverage()) == set(FAILURE_CODES)
    assert all(count > 0 for count in coverage().values())


def test_success_proposes_nothing() -> None:
    assert propose(ReasonCode.SUCCESS, STAGE_ORDER[-1]) == ()


def test_every_failure_and_stage_pairing_proposes_candidates() -> None:
    for code in FAILURE_CODES:
        for task_stage in STAGE_ORDER:
            assert propose(code, task_stage), f"no repair for {code}@{task_stage}"


def test_candidates_are_unique_per_proposal() -> None:
    for code in FAILURE_CODES:
        for task_stage in STAGE_ORDER:
            names = [c.name for c in propose(code, task_stage)]
            assert len(names) == len(set(names))


def test_stage_specific_repairs_are_offered_first() -> None:
    from crux.failures.taxonomy import TaskStage

    ordered = propose(ReasonCode.CABLE_SLIP, TaskStage.ALIGN_CONNECTOR)
    assert ordered[0].name == "short-dangle-regrasp"


def test_every_candidate_applies_to_the_baseline() -> None:
    base = baseline()
    for code in FAILURE_CODES:
        for task_stage in STAGE_ORDER:
            for candidate in propose(code, task_stage):
                repaired = candidate.apply(base)
                assert repaired.changes_from(base), f"{candidate.name} changed nothing"


def test_the_align_slip_repair_shortens_the_dangle() -> None:
    from crux.failures.taxonomy import TaskStage

    base = baseline()
    repaired = propose(ReasonCode.CABLE_SLIP, TaskStage.ALIGN_CONNECTOR)[0].apply(base)
    segments = 16
    assert repaired.insert_index(segments) > base.insert_index(segments)
