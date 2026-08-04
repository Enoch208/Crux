from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from crux.failures.records import EpisodeRecord
from crux.failures.taxonomy import TaskStage, stage_index, stage_progress
from crux.qualification.compare import mcnemar_exact_p_value, pair_records
from crux.qualification.metrics import Proportion


def reached(episode: EpisodeRecord, endpoint: TaskStage) -> bool:
    if episode.succeeded:
        return True
    return stage_index(episode.task_stage) >= stage_index(endpoint)


def mean_progress(episodes: Sequence[EpisodeRecord]) -> float:
    if not episodes:
        return 0.0
    return sum(stage_progress(episode.task_stage) for episode in episodes) / len(episodes)


@dataclass(frozen=True, slots=True)
class StageComparison:
    endpoint: TaskStage
    baseline_version: str
    repaired_version: str
    both: int
    baseline_only: int
    repaired_only: int
    neither: int
    baseline_mean_progress: float
    repaired_mean_progress: float

    @property
    def pairs(self) -> int:
        return self.both + self.baseline_only + self.repaired_only + self.neither

    @property
    def baseline_reached(self) -> Proportion:
        return Proportion(self.both + self.baseline_only, self.pairs)

    @property
    def repaired_reached(self) -> Proportion:
        return Proportion(self.both + self.repaired_only, self.pairs)

    @property
    def delta_percentage_points(self) -> float:
        return self.repaired_reached.percentage - self.baseline_reached.percentage

    @property
    def mcnemar_p_value(self) -> float:
        return mcnemar_exact_p_value(self.baseline_only, self.repaired_only)


def compare_stage_reached(
    baseline: Sequence[EpisodeRecord],
    repaired: Sequence[EpisodeRecord],
    endpoint: TaskStage,
) -> StageComparison:
    matched = pair_records(baseline, repaired)
    flags = [
        (reached(baseline_episode, endpoint), reached(repaired_episode, endpoint))
        for _, baseline_episode, repaired_episode in matched
    ]
    return StageComparison(
        endpoint=endpoint,
        baseline_version=baseline[0].controller_version,
        repaired_version=repaired[0].controller_version,
        both=sum(b and r for b, r in flags),
        baseline_only=sum(b and not r for b, r in flags),
        repaired_only=sum(r and not b for b, r in flags),
        neither=sum(not b and not r for b, r in flags),
        baseline_mean_progress=mean_progress([episode for _, episode, _ in matched]),
        repaired_mean_progress=mean_progress([episode for _, _, episode in matched]),
    )
