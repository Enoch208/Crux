from __future__ import annotations

import pytest

from crux.errors import ErrorCode, QualificationError
from crux.qualification.compare import compare_matched, mcnemar_exact_p_value, pair_episodes
from crux.qualification.suites import SuiteName
from tests.factories import make_arm, make_episode


def test_pairing_requires_every_seed_to_have_a_counterpart() -> None:
    baseline = make_arm(2, 0, controller_version="baseline-v1", first_seed=1)
    repaired = make_arm(2, 0, controller_version="repair-v1", first_seed=2)
    with pytest.raises(QualificationError) as caught:
        pair_episodes(baseline, repaired)
    assert caught.value.code is ErrorCode.EPISODE_UNMATCHED


def test_pairing_rejects_divergent_environment_parameters() -> None:
    baseline = [make_episode(1, succeeded=True, environment_parameters={"friction": 0.5})]
    repaired = [
        make_episode(
            1,
            succeeded=True,
            controller_version="repair-v1",
            environment_parameters={"friction": 0.6},
        )
    ]
    with pytest.raises(QualificationError) as caught:
        pair_episodes(baseline, repaired)
    assert caught.value.code is ErrorCode.EPISODE_CONDITIONS_DIVERGED


def test_pairing_rejects_duplicate_seeds_within_an_arm() -> None:
    baseline = [make_episode(1, succeeded=True), make_episode(1, succeeded=False)]
    repaired = [make_episode(1, succeeded=True, controller_version="repair-v1")]
    with pytest.raises(QualificationError) as caught:
        pair_episodes(baseline, repaired)
    assert caught.value.code is ErrorCode.EPISODE_DUPLICATE


def test_comparison_partitions_pairs_into_the_four_cells() -> None:
    baseline = [
        make_episode(1, succeeded=True),
        make_episode(2, succeeded=True),
        make_episode(3, succeeded=False),
        make_episode(4, succeeded=False),
    ]
    repaired = [
        make_episode(1, succeeded=True, controller_version="repair-v1"),
        make_episode(2, succeeded=False, controller_version="repair-v1"),
        make_episode(3, succeeded=True, controller_version="repair-v1"),
        make_episode(4, succeeded=False, controller_version="repair-v1"),
    ]
    comparison = compare_matched(baseline, repaired)
    assert (comparison.both_succeed, comparison.baseline_only) == (1, 1)
    assert (comparison.repaired_only, comparison.both_fail) == (1, 1)
    assert comparison.pairs == 4
    assert comparison.baseline_success.successes == 2
    assert comparison.repaired_success.successes == 2
    assert comparison.delta_percentage_points == 0.0


def test_comparison_reports_improvement_in_percentage_points() -> None:
    baseline = make_arm(5, 5, controller_version="baseline-v1")
    repaired = make_arm(8, 2, controller_version="repair-v1")
    comparison = compare_matched(baseline, repaired)
    assert comparison.delta_percentage_points == pytest.approx(30.0)
    assert comparison.repaired_only == 3
    assert comparison.baseline_only == 0


def test_comparison_rejects_mixed_suites() -> None:
    baseline = [make_episode(1, succeeded=True, suite=SuiteName.STANDARD)]
    repaired = [
        make_episode(1, succeeded=True, controller_version="repair-v1", suite=SuiteName.HELDOUT)
    ]
    with pytest.raises(QualificationError) as caught:
        compare_matched(baseline, repaired)
    assert caught.value.code is ErrorCode.EPISODE_SUITE_MIXED


@pytest.mark.parametrize(
    ("baseline_only", "repaired_only", "expected"),
    [(0, 0, 1.0), (0, 5, 0.0625), (1, 9, 0.021484375), (3, 3, 1.0)],
)
def test_mcnemar_exact_p_value(baseline_only: int, repaired_only: int, expected: float) -> None:
    assert mcnemar_exact_p_value(baseline_only, repaired_only) == pytest.approx(expected)


def test_mcnemar_is_symmetric() -> None:
    assert mcnemar_exact_p_value(2, 8) == mcnemar_exact_p_value(8, 2)
