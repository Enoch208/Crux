from __future__ import annotations

from datetime import UTC, datetime

import pytest

from crux.errors import CruxError
from crux.failures.records import EpisodeMetrics, EpisodeRecord
from crux.failures.taxonomy import ReasonCode, TaskStage
from crux.learning.dataset import (
    build_dataset,
    feature_names,
    fit_standardiser,
    row_for,
    split_by_seed,
)
from crux.learning.metrics import accuracy, brier_score, roc_auc, triage_at_budget
from crux.qualification.suites import SuiteName


def episode(seed: int, version: str, code: ReasonCode, dx: float = 0.0) -> EpisodeRecord:
    return EpisodeRecord(
        run_id="test",
        episode_id=f"test-{seed}-{version}",
        seed=seed,
        controller_version=version,
        suite=SuiteName.HELDOUT,
        reason_code=code,
        task_stage=TaskStage.VERIFY_SEATED,
        simulation_step=100,
        timestamp=datetime.now(UTC),
        environment_parameters={
            "cable_dx": dx,
            "cable_dy": 0.01,
            "close_force_n": -56.0,
            "route_z_m": 0.048,
        },
        metrics=EpisodeMetrics(
            completion_steps=100,
            completion_seconds=0.5,
            max_cable_tension=1.0,
            max_collision_impulse=0.0,
        ),
    )


def test_features_encode_conditions_and_controller_identity() -> None:
    baseline = row_for(episode(1, "baseline-v1", ReasonCode.MISSED_GRASP))
    repaired = row_for(episode(1, "candidate-v4", ReasonCode.SUCCESS))
    assert len(baseline) == len(feature_names())
    assert baseline[-1] == 0.0
    assert repaired[-1] == 1.0


def test_missing_environment_parameters_fail_loudly() -> None:
    record = episode(1, "candidate-v4", ReasonCode.SUCCESS)
    broken = record.model_copy(update={"environment_parameters": {"cable_dx": 0.0}})
    with pytest.raises(CruxError):
        row_for(broken)


def test_labels_mark_every_non_success_as_failure() -> None:
    dataset = build_dataset(
        [
            episode(1, "candidate-v4", ReasonCode.SUCCESS),
            episode(2, "candidate-v4", ReasonCode.CABLE_SLIP),
            episode(3, "baseline-v1", ReasonCode.MISSED_GRASP),
        ]
    )
    assert dataset.labels == (0, 1, 1)
    assert dataset.failure_rate == pytest.approx(2 / 3)


def test_split_by_seed_keeps_holdout_seeds_out_of_training() -> None:
    dataset = build_dataset(
        [episode(seed, "candidate-v4", ReasonCode.SUCCESS) for seed in (1, 2, 9)]
    )
    train, test = split_by_seed(dataset, [9])
    assert set(train.seeds) == {1, 2}
    assert set(test.seeds) == {9}


def test_split_refuses_when_a_side_would_be_empty() -> None:
    dataset = build_dataset([episode(1, "candidate-v4", ReasonCode.SUCCESS)])
    with pytest.raises(CruxError):
        split_by_seed(dataset, [1])


def test_standardiser_is_fitted_on_training_rows_only() -> None:
    dataset = build_dataset(
        [
            episode(1, "candidate-v4", ReasonCode.SUCCESS, dx=0.0),
            episode(2, "candidate-v4", ReasonCode.SUCCESS, dx=2.0),
        ]
    )
    standardiser = fit_standardiser(dataset)
    assert standardiser.means[0] == pytest.approx(1.0)
    assert standardiser.scales[0] == pytest.approx(1.0)
    scaled = standardiser.apply(dataset.rows)
    assert scaled[0][0] == pytest.approx(-1.0)
    assert scaled[1][0] == pytest.approx(1.0)


def test_a_constant_feature_never_divides_by_zero() -> None:
    dataset = build_dataset([episode(seed, "candidate-v4", ReasonCode.SUCCESS) for seed in (1, 2)])
    standardiser = fit_standardiser(dataset)
    assert all(scale > 0.0 for scale in standardiser.scales)


def test_roc_auc_is_one_for_a_perfect_ranking_and_half_for_chance() -> None:
    assert roc_auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == pytest.approx(1.0)
    assert roc_auc([0, 1], [0.5, 0.5]) == pytest.approx(0.5)
    assert roc_auc([1, 1, 0, 0], [0.1, 0.2, 0.8, 0.9]) == pytest.approx(0.0)


def test_roc_auc_refuses_a_single_class() -> None:
    with pytest.raises(CruxError):
        roc_auc([1, 1], [0.4, 0.6])


def test_brier_and_accuracy_reward_calibrated_confidence() -> None:
    assert brier_score([1, 0], [1.0, 0.0]) == pytest.approx(0.0)
    assert brier_score([1, 0], [0.0, 1.0]) == pytest.approx(1.0)
    assert accuracy([1, 0, 1], [0.9, 0.1, 0.8]) == pytest.approx(1.0)


def test_triage_measures_lift_over_testing_at_random() -> None:
    labels = [1, 1, 0, 0, 0, 0, 0, 0]
    perfect = [0.9, 0.8, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]
    score = triage_at_budget(labels, perfect, budget=2)
    assert score.failures_found == 2
    assert score.random_expectation == pytest.approx(0.5)
    assert score.lift == pytest.approx(4.0)


def test_triage_rejects_a_budget_outside_the_suite() -> None:
    with pytest.raises(CruxError):
        triage_at_budget([1, 0], [0.9, 0.1], budget=5)
