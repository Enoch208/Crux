from __future__ import annotations

from datetime import UTC, datetime

from crux.config import QualificationConfig, ReleaseGateConfig
from crux.failures.records import EpisodeMetrics, EpisodeRecord
from crux.failures.taxonomy import ReasonCode, TaskStage
from crux.qualification.release_gate import GateDecision, GateReason
from crux.qualification.suites import SuiteName
from crux.report.qualification_report import (
    build_report,
    group_by_controller,
    render_markdown,
)

PARAMS = {"cable_dx": 0.0}


def episode(
    seed: int,
    version: str,
    suite: SuiteName,
    task_stage: TaskStage = TaskStage.ROUTE_CLIP_1,
    reason_code: ReasonCode = ReasonCode.CABLE_SLIP,
) -> EpisodeRecord:
    return EpisodeRecord(
        run_id="test",
        episode_id=f"test-{suite}-{seed}-{version}",
        seed=seed,
        controller_version=version,
        suite=suite,
        reason_code=reason_code,
        task_stage=task_stage,
        simulation_step=10,
        timestamp=datetime.now(UTC),
        environment_parameters=PARAMS,
        metrics=EpisodeMetrics(
            completion_steps=10,
            completion_seconds=0.1,
            max_cable_tension=2.0,
            max_collision_impulse=0.0,
        ),
    )


def config() -> QualificationConfig:
    return QualificationConfig(
        confidence_level=0.95,
        release_gate=ReleaseGateConfig(
            max_regression_pp=2.0,
            max_additional_failures=0,
            small_sample_episodes=30,
            require_improvement=True,
        ),
    )


def arms(suite: SuiteName) -> tuple[list[EpisodeRecord], list[EpisodeRecord]]:
    seeds = (1, 2, 3)
    baseline = [episode(seed, "baseline-v1", suite) for seed in seeds]
    repaired = [episode(seed, "repaired-v1", suite) for seed in seeds]
    return baseline, repaired


def test_group_by_controller_splits_arms() -> None:
    baseline, repaired = arms(SuiteName.STANDARD)
    grouped = group_by_controller([*baseline, *repaired])
    assert sorted(grouped) == ["baseline-v1", "repaired-v1"]
    assert len(grouped["baseline-v1"]) == 3


def test_a_repair_with_no_improvement_is_rejected() -> None:
    standard_baseline, standard_repaired = arms(SuiteName.STANDARD)
    heldout_baseline, heldout_repaired = arms(SuiteName.HELDOUT)
    report = build_report(
        standard_baseline, standard_repaired, heldout_baseline, heldout_repaired, config()
    )
    assert report.gate.decision is GateDecision.REJECTED
    assert GateReason.NO_IMPROVEMENT_DEMONSTRATED in report.gate.reason_codes


def test_a_repair_that_wins_on_heldout_is_approved() -> None:
    standard_baseline, standard_repaired = arms(SuiteName.STANDARD)
    heldout_baseline = [episode(seed, "baseline-v1", SuiteName.HELDOUT) for seed in (1, 2, 3)]
    heldout_repaired = [
        episode(1, "repaired-v1", SuiteName.HELDOUT, TaskStage.VERIFY_SEATED, ReasonCode.SUCCESS),
        episode(2, "repaired-v1", SuiteName.HELDOUT),
        episode(3, "repaired-v1", SuiteName.HELDOUT),
    ]
    report = build_report(
        standard_baseline, standard_repaired, heldout_baseline, heldout_repaired, config()
    )
    assert report.gate.decision is GateDecision.APPROVED
    assert report.heldout_success.repaired_only == 1


def test_markdown_reports_the_decision_and_every_arm() -> None:
    standard_baseline, standard_repaired = arms(SuiteName.STANDARD)
    heldout_baseline, heldout_repaired = arms(SuiteName.HELDOUT)
    document = render_markdown(
        build_report(
            standard_baseline, standard_repaired, heldout_baseline, heldout_repaired, config()
        )
    )
    assert "REJECTED" in document
    assert "NO_IMPROVEMENT_DEMONSTRATED" in document
    assert document.count("`baseline-v1`") >= 2
    assert document.count("`repaired-v1`") >= 2
    assert "McNemar p" in document
