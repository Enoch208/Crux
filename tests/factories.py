from __future__ import annotations

from datetime import UTC, datetime

from crux.failures.records import EpisodeMetrics, EpisodeRecord
from crux.failures.taxonomy import ReasonCode, TaskStage
from crux.qualification.suites import SuiteName

FIXED_TIME = datetime(2026, 8, 4, 12, 0, 0, tzinfo=UTC)

DEFAULT_METRICS = EpisodeMetrics(
    completion_steps=1200,
    completion_seconds=24.0,
    max_cable_tension=8.5,
    max_collision_impulse=0.0,
    insertion_position_error_m=0.002,
    insertion_orientation_error_rad=0.01,
)


def make_episode(
    seed: int,
    *,
    succeeded: bool,
    controller_version: str = "baseline-v1",
    suite: SuiteName = SuiteName.STANDARD,
    reason_code: ReasonCode | None = None,
    task_stage: TaskStage = TaskStage.ROUTE_CLIP_2,
    run_id: str = "run-1",
    environment_parameters: dict[str, float] | None = None,
    metrics: EpisodeMetrics = DEFAULT_METRICS,
) -> EpisodeRecord:
    if reason_code is None:
        reason_code = ReasonCode.SUCCESS if succeeded else ReasonCode.CABLE_SNAG
    return EpisodeRecord(
        run_id=run_id,
        episode_id=f"{controller_version}-{suite}-{seed}",
        seed=seed,
        controller_version=controller_version,
        suite=suite,
        reason_code=reason_code,
        task_stage=TaskStage.VERIFY_SEATED if succeeded else task_stage,
        simulation_step=1200,
        timestamp=FIXED_TIME,
        environment_parameters=environment_parameters or {"cable_stiffness": 0.4 + seed * 0.01},
        metrics=metrics,
    )


def make_arm(
    successes: int,
    failures: int,
    *,
    controller_version: str,
    suite: SuiteName = SuiteName.STANDARD,
    first_seed: int = 1,
) -> list[EpisodeRecord]:
    episodes: list[EpisodeRecord] = []
    for offset in range(successes + failures):
        episodes.append(
            make_episode(
                first_seed + offset,
                succeeded=offset < successes,
                controller_version=controller_version,
                suite=suite,
            )
        )
    return episodes
