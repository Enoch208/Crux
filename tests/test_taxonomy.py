from __future__ import annotations

import pytest

from crux.failures.taxonomy import (
    FAILURE_CODES,
    STAGE_ORDER,
    FailureFamily,
    ReasonCode,
    TaskStage,
    stage_index,
    stage_progress,
)


def test_success_is_the_only_non_failure_code() -> None:
    assert ReasonCode.SUCCESS not in FAILURE_CODES
    assert len(FAILURE_CODES) == len(ReasonCode) - 1
    assert all(code.is_failure for code in FAILURE_CODES)


def test_every_prd_reason_code_is_present() -> None:
    expected = {
        "MISSED_GRASP",
        "CABLE_SLIP",
        "CLIP_1_MISSED",
        "CLIP_2_MISSED",
        "CABLE_SNAG",
        "OVER_TENSION",
        "ROBOT_COLLISION",
        "CONNECTOR_MISALIGNED",
        "INCOMPLETE_INSERTION",
        "TIMEOUT",
        "UNSTABLE_SIMULATION",
        "SUCCESS",
    }
    assert {str(code) for code in ReasonCode} == expected


def test_stage_order_covers_every_stage_exactly_once() -> None:
    assert len(STAGE_ORDER) == len(TaskStage)
    assert len(set(STAGE_ORDER)) == len(STAGE_ORDER)


def test_stage_progress_runs_from_zero_to_one() -> None:
    assert stage_progress(TaskStage.OBSERVE) == 0.0
    assert stage_progress(TaskStage.VERIFY_SEATED) == 1.0
    assert stage_index(TaskStage.ROUTE_CLIP_2) > stage_index(TaskStage.ROUTE_CLIP_1)


def test_failure_family_key_round_trips() -> None:
    family = FailureFamily(ReasonCode.CABLE_SNAG, TaskStage.ROUTE_CLIP_2)
    assert family.key == "CABLE_SNAG@ROUTE_CLIP_2"
    assert FailureFamily.parse(family.key) == family


def test_failure_family_parse_rejects_unknown_code() -> None:
    with pytest.raises(ValueError, match="NOT_A_CODE"):
        FailureFamily.parse("NOT_A_CODE@OBSERVE")
