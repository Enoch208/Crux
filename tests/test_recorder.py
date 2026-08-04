from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from crux.errors import ErrorCode, EvidenceError
from crux.failures.recorder import append_failure, read_episodes, read_failures, write_episodes
from crux.failures.records import CheckpointRef, FailureEvent
from crux.failures.taxonomy import ReasonCode, TaskStage
from tests.factories import FIXED_TIME, make_arm, make_episode


def test_episodes_round_trip_through_jsonl(tmp_path: Path) -> None:
    episodes = make_arm(3, 2, controller_version="baseline-v1")
    path = tmp_path / "raw" / "baseline_episodes.jsonl"
    write_episodes(path, episodes)
    assert read_episodes(path) == episodes


def test_reading_a_missing_episode_file_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(EvidenceError) as caught:
        read_episodes(tmp_path / "absent.jsonl")
    assert caught.value.code is ErrorCode.EVIDENCE_FILE_MISSING


def test_a_corrupt_line_is_reported_with_its_line_number(tmp_path: Path) -> None:
    path = tmp_path / "episodes.jsonl"
    write_episodes(path, [make_episode(1, succeeded=True)])
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"run_id": "run-1"}\n')
    with pytest.raises(EvidenceError) as caught:
        read_episodes(path)
    assert caught.value.code is ErrorCode.EVIDENCE_SCHEMA_INVALID
    assert ":2" in caught.value.message


def test_blank_lines_are_skipped(tmp_path: Path) -> None:
    path = tmp_path / "episodes.jsonl"
    write_episodes(path, [make_episode(1, succeeded=True)])
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n\n")
    assert len(read_episodes(path)) == 1


def make_failure_event(reason_code: ReasonCode = ReasonCode.CABLE_SNAG) -> FailureEvent:
    return FailureEvent(
        run_id="run-1",
        episode_id="baseline-v1-standard-1",
        seed=1,
        controller_version="baseline-v1",
        reason_code=reason_code,
        task_stage=TaskStage.ROUTE_CLIP_2,
        simulation_step=843,
        timestamp=FIXED_TIME,
        environment_parameters={"cable_stiffness": 0.41},
        robot_state=(0.0, -0.3, 0.0, -2.1, 0.0, 1.8, 0.79),
        cable_state=(0.1, 0.2, 0.3),
        last_safe_checkpoint=CheckpointRef(
            checkpoint_id="ckpt-1",
            task_stage=TaskStage.VERIFY_CLIP_1,
            simulation_step=620,
            path="checkpoints/ckpt-1.npz",
        ),
        risk_metrics={"max_tension": 14.2},
    )


def test_failure_events_round_trip(tmp_path: Path) -> None:
    event = make_failure_event()
    path = tmp_path / "failures.jsonl"
    append_failure(path, event)
    assert read_failures(path) == [event]


def test_a_failure_event_cannot_claim_success() -> None:
    with pytest.raises(ValidationError, match="not SUCCESS"):
        make_failure_event(ReasonCode.SUCCESS)


def test_failure_event_exposes_its_family() -> None:
    assert make_failure_event().family.key == "CABLE_SNAG@ROUTE_CLIP_2"
