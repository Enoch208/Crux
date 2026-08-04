from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from math import ceil, sqrt
from statistics import NormalDist

from crux.errors import ErrorCode, QualificationError
from crux.failures.records import EpisodeRecord
from crux.failures.taxonomy import ReasonCode
from crux.qualification.suites import SuiteName


def z_for_confidence(confidence_level: float) -> float:
    if not 0.0 < confidence_level < 1.0:
        raise QualificationError(
            ErrorCode.SAMPLE_INVALID,
            f"confidence level must lie in (0, 1), got {confidence_level}",
        )
    return NormalDist().inv_cdf(1.0 - (1.0 - confidence_level) / 2.0)


@dataclass(frozen=True, slots=True)
class ConfidenceInterval:
    lower: float
    upper: float
    confidence_level: float


@dataclass(frozen=True, slots=True)
class Proportion:
    successes: int
    total: int

    def __post_init__(self) -> None:
        if self.total <= 0:
            raise QualificationError(
                ErrorCode.SAMPLE_EMPTY, "cannot form a proportion over zero episodes"
            )
        if not 0 <= self.successes <= self.total:
            raise QualificationError(
                ErrorCode.SAMPLE_INVALID,
                f"successes {self.successes} outside [0, {self.total}]",
            )

    @property
    def rate(self) -> float:
        return self.successes / self.total

    @property
    def percentage(self) -> float:
        return 100.0 * self.rate

    def wilson_interval(self, confidence_level: float) -> ConfidenceInterval:
        z = z_for_confidence(confidence_level)
        n = float(self.total)
        p = self.rate
        denominator = 1.0 + z * z / n
        center = (p + z * z / (2.0 * n)) / denominator
        margin = z * sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denominator
        return ConfidenceInterval(
            lower=max(0.0, center - margin),
            upper=min(1.0, center + margin),
            confidence_level=confidence_level,
        )


def percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        raise QualificationError(ErrorCode.SAMPLE_EMPTY, "percentile of an empty sample")
    if not 0.0 < quantile <= 1.0:
        raise QualificationError(
            ErrorCode.SAMPLE_INVALID, f"quantile must lie in (0, 1], got {quantile}"
        )
    ordered = sorted(values)
    rank = min(len(ordered), max(1, ceil(quantile * len(ordered))))
    return ordered[rank - 1]


@dataclass(frozen=True, slots=True)
class SuiteMetrics:
    suite: SuiteName
    controller_version: str
    success: Proportion
    reason_code_counts: dict[str, int]
    family_counts: dict[str, int]
    mean_completion_seconds: float
    p95_completion_seconds: float
    mean_max_cable_tension: float

    @property
    def over_tension_episodes(self) -> int:
        return self.reason_code_counts.get(ReasonCode.OVER_TENSION, 0)

    @property
    def prohibited_collision_episodes(self) -> int:
        return self.reason_code_counts.get(ReasonCode.ROBOT_COLLISION, 0)

    @property
    def timeout_episodes(self) -> int:
        return self.reason_code_counts.get(ReasonCode.TIMEOUT, 0)


def _assert_homogeneous(episodes: Sequence[EpisodeRecord]) -> None:
    seen_ids: set[str] = set()
    for episode in episodes:
        if episode.episode_id in seen_ids:
            raise QualificationError(
                ErrorCode.EPISODE_DUPLICATE, f"duplicate episode_id {episode.episode_id}"
            )
        seen_ids.add(episode.episode_id)
    suites = {episode.suite for episode in episodes}
    if len(suites) > 1:
        raise QualificationError(
            ErrorCode.EPISODE_SUITE_MIXED,
            f"episodes span multiple suites: {sorted(suites)}",
        )
    controllers = {episode.controller_version for episode in episodes}
    if len(controllers) > 1:
        raise QualificationError(
            ErrorCode.EPISODE_CONTROLLER_MIXED,
            f"episodes span multiple controller versions: {sorted(controllers)}",
        )


def aggregate_suite(episodes: Sequence[EpisodeRecord]) -> SuiteMetrics:
    if not episodes:
        raise QualificationError(ErrorCode.SAMPLE_EMPTY, "cannot aggregate zero episodes")
    _assert_homogeneous(episodes)
    reason_counts = Counter(str(episode.reason_code) for episode in episodes)
    family_counts = Counter(
        episode.family.key for episode in episodes if episode.family is not None
    )
    durations = [episode.metrics.completion_seconds for episode in episodes]
    tensions = [episode.metrics.max_cable_tension for episode in episodes]
    return SuiteMetrics(
        suite=episodes[0].suite,
        controller_version=episodes[0].controller_version,
        success=Proportion(sum(episode.succeeded for episode in episodes), len(episodes)),
        reason_code_counts=dict(reason_counts),
        family_counts=dict(family_counts),
        mean_completion_seconds=sum(durations) / len(durations),
        p95_completion_seconds=percentile(durations, 0.95),
        mean_max_cable_tension=sum(tensions) / len(tensions),
    )
