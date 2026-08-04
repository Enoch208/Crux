from __future__ import annotations

from datetime import UTC, datetime

from crux.failures.records import EpisodeMetrics, EpisodeRecord
from crux.failures.taxonomy import ReasonCode, TaskStage
from crux.qualification.progress import (
    compare_stage_reached,
    mean_progress,
    reached,
)
from crux.qualification.suites import SuiteName

PARAMS = {"cable_dx": 0.0, "cable_dy": 0.0}


def episode(
    seed: int,
    version: str,
    task_stage: TaskStage,
    reason_code: ReasonCode = ReasonCode.CABLE_SLIP,
) -> EpisodeRecord:
    return EpisodeRecord(
        run_id="test",
        episode_id=f"test-{seed}-{version}",
        seed=seed,
        controller_version=version,
        suite=SuiteName.HELDOUT,
        reason_code=reason_code,
        task_stage=task_stage,
        simulation_step=100,
        timestamp=datetime.now(UTC),
        environment_parameters=PARAMS,
        metrics=EpisodeMetrics(
            completion_steps=100,
            completion_seconds=0.5,
            max_cable_tension=1.0,
            max_collision_impulse=0.0,
        ),
    )


def test_reached_is_true_at_or_past_the_endpoint() -> None:
    assert reached(episode(1, "a", TaskStage.VERIFY_SEATED), TaskStage.VERIFY_SEATED)
    assert reached(episode(1, "a", TaskStage.INSERT_CONNECTOR), TaskStage.ALIGN_CONNECTOR)
    assert not reached(episode(1, "a", TaskStage.VERIFY_CLIP_1), TaskStage.ALIGN_CONNECTOR)


def test_success_counts_as_reaching_any_endpoint() -> None:
    seated = episode(1, "a", TaskStage.VERIFY_SEATED, ReasonCode.SUCCESS)
    assert reached(seated, TaskStage.VERIFY_SEATED)


def test_mean_progress_of_no_episodes_is_zero() -> None:
    assert mean_progress([]) == 0.0


def test_mean_progress_rises_with_deeper_stages() -> None:
    early = [episode(1, "a", TaskStage.OBSERVE)]
    late = [episode(1, "a", TaskStage.VERIFY_SEATED)]
    assert mean_progress(late) > mean_progress(early)


def test_stage_comparison_counts_discordant_pairs() -> None:
    baseline = [
        episode(1, "base", TaskStage.VERIFY_CLIP_1),
        episode(2, "base", TaskStage.VERIFY_SEATED),
        episode(3, "base", TaskStage.VERIFY_CLIP_2),
    ]
    repaired = [
        episode(1, "fix", TaskStage.VERIFY_SEATED),
        episode(2, "fix", TaskStage.VERIFY_SEATED),
        episode(3, "fix", TaskStage.ROUTE_CLIP_1),
    ]
    result = compare_stage_reached(baseline, repaired, TaskStage.VERIFY_SEATED)
    assert result.pairs == 3
    assert result.both == 1
    assert result.repaired_only == 1
    assert result.baseline_only == 0
    assert result.neither == 1
    assert result.delta_percentage_points > 0.0


def test_stage_comparison_reports_a_null_when_arms_agree() -> None:
    baseline = [episode(1, "base", TaskStage.VERIFY_CLIP_1)]
    repaired = [episode(1, "fix", TaskStage.VERIFY_CLIP_1)]
    result = compare_stage_reached(baseline, repaired, TaskStage.VERIFY_SEATED)
    assert result.delta_percentage_points == 0.0
    assert result.mcnemar_p_value == 1.0
