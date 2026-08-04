from __future__ import annotations

import pytest

from crux.errors import ErrorCode, QualificationError
from crux.failures.taxonomy import ReasonCode
from crux.qualification.metrics import Proportion, aggregate_suite, percentile, z_for_confidence
from crux.qualification.suites import SuiteName
from tests.factories import make_arm, make_episode


@pytest.mark.parametrize(("successes", "total"), [(45, 60), (1, 7), (119, 120), (30, 61)])
def test_wilson_bounds_satisfy_their_defining_equation(successes: int, total: int) -> None:
    proportion = Proportion(successes, total)
    interval = proportion.wilson_interval(0.95)
    z = z_for_confidence(0.95)
    for bound in (interval.lower, interval.upper):
        squared_distance = (proportion.rate - bound) ** 2
        expected = z * z * bound * (1.0 - bound) / total
        assert squared_distance == pytest.approx(expected, abs=1e-12)


def test_wilson_interval_matches_published_value() -> None:
    interval = Proportion(45, 60).wilson_interval(0.95)
    assert interval.lower == pytest.approx(0.6277, abs=1e-4)
    assert interval.upper == pytest.approx(0.8422, abs=1e-4)


def test_wilson_interval_clamps_at_zero_successes() -> None:
    interval = Proportion(0, 10).wilson_interval(0.95)
    assert interval.lower == 0.0
    assert interval.upper == pytest.approx(0.2775, abs=1e-4)


def test_wilson_interval_clamps_at_full_success() -> None:
    interval = Proportion(10, 10).wilson_interval(0.95)
    assert interval.upper == 1.0
    assert interval.lower < 1.0


def test_z_for_confidence_is_the_standard_95_percent_value() -> None:
    assert z_for_confidence(0.95) == pytest.approx(1.959964, abs=1e-6)


def test_proportion_rejects_empty_sample() -> None:
    with pytest.raises(QualificationError) as caught:
        Proportion(0, 0)
    assert caught.value.code is ErrorCode.SAMPLE_EMPTY


def test_proportion_rejects_successes_above_total() -> None:
    with pytest.raises(QualificationError) as caught:
        Proportion(11, 10)
    assert caught.value.code is ErrorCode.SAMPLE_INVALID


def test_percentile_uses_nearest_rank() -> None:
    values = [float(v) for v in range(1, 21)]
    assert percentile(values, 0.95) == 19.0
    assert percentile(values, 1.0) == 20.0
    assert percentile(values, 0.5) == 10.0


def test_aggregate_suite_counts_successes_and_families() -> None:
    episodes = make_arm(7, 3, controller_version="baseline-v1")
    metrics = aggregate_suite(episodes)
    assert metrics.success.successes == 7
    assert metrics.success.total == 10
    assert metrics.suite is SuiteName.STANDARD
    assert metrics.family_counts == {"CABLE_SNAG@ROUTE_CLIP_2": 3}
    assert metrics.reason_code_counts[ReasonCode.SUCCESS] == 7


def test_aggregate_suite_rejects_duplicate_episode_ids() -> None:
    episode = make_episode(1, succeeded=True)
    with pytest.raises(QualificationError) as caught:
        aggregate_suite([episode, episode])
    assert caught.value.code is ErrorCode.EPISODE_DUPLICATE


def test_aggregate_suite_rejects_mixed_suites() -> None:
    episodes = [
        make_episode(1, succeeded=True, suite=SuiteName.STANDARD),
        make_episode(2, succeeded=True, suite=SuiteName.HELDOUT),
    ]
    with pytest.raises(QualificationError) as caught:
        aggregate_suite(episodes)
    assert caught.value.code is ErrorCode.EPISODE_SUITE_MIXED


def test_aggregate_suite_rejects_mixed_controllers() -> None:
    episodes = [
        make_episode(1, succeeded=True, controller_version="baseline-v1"),
        make_episode(2, succeeded=True, controller_version="repair-v1"),
    ]
    with pytest.raises(QualificationError) as caught:
        aggregate_suite(episodes)
    assert caught.value.code is ErrorCode.EPISODE_CONTROLLER_MIXED
