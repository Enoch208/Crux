from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import comb

from crux.errors import ErrorCode, QualificationError
from crux.evidence.hashing import conditions_key
from crux.failures.records import EpisodeRecord
from crux.qualification.metrics import Proportion
from crux.qualification.suites import SuiteName


@dataclass(frozen=True, slots=True)
class MatchedPair:
    seed: int
    conditions_sha256: str
    baseline_succeeded: bool
    repaired_succeeded: bool


def _index_by_seed(episodes: Sequence[EpisodeRecord], role: str) -> dict[int, EpisodeRecord]:
    indexed: dict[int, EpisodeRecord] = {}
    for episode in episodes:
        if episode.seed in indexed:
            raise QualificationError(
                ErrorCode.EPISODE_DUPLICATE,
                f"{role} suite contains seed {episode.seed} more than once",
            )
        indexed[episode.seed] = episode
    return indexed


def pair_records(
    baseline: Sequence[EpisodeRecord],
    repaired: Sequence[EpisodeRecord],
) -> list[tuple[int, EpisodeRecord, EpisodeRecord]]:
    baseline_by_seed = _index_by_seed(baseline, "baseline")
    repaired_by_seed = _index_by_seed(repaired, "repaired")
    unmatched = sorted(set(baseline_by_seed) ^ set(repaired_by_seed))
    if unmatched:
        raise QualificationError(
            ErrorCode.EPISODE_UNMATCHED,
            f"{len(unmatched)} seed(s) lack a counterpart, so the comparison is not matched: "
            f"{unmatched[:10]}",
        )
    matched: list[tuple[int, EpisodeRecord, EpisodeRecord]] = []
    for seed in sorted(baseline_by_seed):
        baseline_episode = baseline_by_seed[seed]
        repaired_episode = repaired_by_seed[seed]
        baseline_key = conditions_key(seed, baseline_episode.environment_parameters)
        repaired_key = conditions_key(seed, repaired_episode.environment_parameters)
        if baseline_key != repaired_key:
            raise QualificationError(
                ErrorCode.EPISODE_CONDITIONS_DIVERGED,
                f"seed {seed} ran under different environment parameters for baseline and "
                f"repaired controllers",
            )
        matched.append((seed, baseline_episode, repaired_episode))
    return matched


def pair_episodes(
    baseline: Sequence[EpisodeRecord],
    repaired: Sequence[EpisodeRecord],
) -> list[MatchedPair]:
    return [
        MatchedPair(
            seed=seed,
            conditions_sha256=conditions_key(seed, baseline_episode.environment_parameters),
            baseline_succeeded=baseline_episode.succeeded,
            repaired_succeeded=repaired_episode.succeeded,
        )
        for seed, baseline_episode, repaired_episode in pair_records(baseline, repaired)
    ]


def mcnemar_exact_p_value(baseline_only: int, repaired_only: int) -> float:
    discordant = baseline_only + repaired_only
    if discordant == 0:
        return 1.0
    smaller = min(baseline_only, repaired_only)
    tail = sum(comb(discordant, i) for i in range(smaller + 1)) * 0.5**discordant
    return min(1.0, 2.0 * tail)


@dataclass(frozen=True, slots=True)
class MatchedComparison:
    suite: SuiteName
    baseline_version: str
    repaired_version: str
    both_succeed: int
    baseline_only: int
    repaired_only: int
    both_fail: int

    @property
    def pairs(self) -> int:
        return self.both_succeed + self.baseline_only + self.repaired_only + self.both_fail

    @property
    def baseline_success(self) -> Proportion:
        return Proportion(self.both_succeed + self.baseline_only, self.pairs)

    @property
    def repaired_success(self) -> Proportion:
        return Proportion(self.both_succeed + self.repaired_only, self.pairs)

    @property
    def delta_percentage_points(self) -> float:
        return self.repaired_success.percentage - self.baseline_success.percentage

    @property
    def regression_percentage_points(self) -> float:
        return self.baseline_success.percentage - self.repaired_success.percentage

    @property
    def mcnemar_p_value(self) -> float:
        return mcnemar_exact_p_value(self.baseline_only, self.repaired_only)


def compare_matched(
    baseline: Sequence[EpisodeRecord],
    repaired: Sequence[EpisodeRecord],
) -> MatchedComparison:
    if not baseline or not repaired:
        raise QualificationError(ErrorCode.SAMPLE_EMPTY, "matched comparison needs both arms")
    suites = {episode.suite for episode in (*baseline, *repaired)}
    if len(suites) > 1:
        raise QualificationError(
            ErrorCode.EPISODE_SUITE_MIXED,
            f"matched comparison spans multiple suites: {sorted(suites)}",
        )
    pairs = pair_episodes(baseline, repaired)
    return MatchedComparison(
        suite=baseline[0].suite,
        baseline_version=baseline[0].controller_version,
        repaired_version=repaired[0].controller_version,
        both_succeed=sum(p.baseline_succeeded and p.repaired_succeeded for p in pairs),
        baseline_only=sum(p.baseline_succeeded and not p.repaired_succeeded for p in pairs),
        repaired_only=sum(not p.baseline_succeeded and p.repaired_succeeded for p in pairs),
        both_fail=sum(not p.baseline_succeeded and not p.repaired_succeeded for p in pairs),
    )
