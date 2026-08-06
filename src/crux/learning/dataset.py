from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from crux.errors import CruxError, ErrorCode
from crux.failures.records import EpisodeRecord
from crux.failures.taxonomy import ReasonCode

FEATURE_NAMES: tuple[str, ...] = ("cable_dx", "cable_dy", "close_force_n", "route_z_m")
CONTROLLER_FEATURE = "controller_is_repaired"
BASELINE_VERSION = "baseline-v1"


@dataclass(frozen=True)
class Standardiser:
    """Per-feature mean and scale, fitted on training rows only."""

    means: tuple[float, ...]
    scales: tuple[float, ...]

    def apply(self, rows: Sequence[Sequence[float]]) -> list[list[float]]:
        return [
            [
                (value - mean) / scale
                for value, mean, scale in zip(row, self.means, self.scales, strict=True)
            ]
            for row in rows
        ]


@dataclass(frozen=True)
class Dataset:
    rows: tuple[tuple[float, ...], ...]
    labels: tuple[int, ...]
    seeds: tuple[int, ...]
    versions: tuple[str, ...]

    def __len__(self) -> int:
        return len(self.rows)

    @property
    def failure_rate(self) -> float:
        return sum(self.labels) / len(self.labels) if self.labels else 0.0


def feature_names() -> tuple[str, ...]:
    return (*FEATURE_NAMES, CONTROLLER_FEATURE)


def row_for(record: EpisodeRecord) -> tuple[float, ...]:
    missing = [name for name in FEATURE_NAMES if name not in record.environment_parameters]
    if missing:
        raise CruxError(
            ErrorCode.SAMPLE_INVALID,
            f"episode {record.episode_id} lacks environment parameters {missing}",
        )
    values = [float(record.environment_parameters[name]) for name in FEATURE_NAMES]
    values.append(0.0 if record.controller_version == BASELINE_VERSION else 1.0)
    return tuple(values)


def build_dataset(records: Sequence[EpisodeRecord]) -> Dataset:
    if not records:
        raise CruxError(ErrorCode.SAMPLE_EMPTY, "no episodes to build a dataset from")
    rows = tuple(row_for(record) for record in records)
    labels = tuple(0 if record.reason_code is ReasonCode.SUCCESS else 1 for record in records)
    seeds = tuple(record.seed for record in records)
    versions = tuple(record.controller_version for record in records)
    return Dataset(rows=rows, labels=labels, seeds=seeds, versions=versions)


def split_by_seed(dataset: Dataset, holdout_seeds: Sequence[int]) -> tuple[Dataset, Dataset]:
    holdout = set(holdout_seeds)
    train_index = [i for i, seed in enumerate(dataset.seeds) if seed not in holdout]
    test_index = [i for i, seed in enumerate(dataset.seeds) if seed in holdout]
    if not train_index or not test_index:
        raise CruxError(
            ErrorCode.SAMPLE_INVALID,
            f"seed split leaves {len(train_index)} train and {len(test_index)} test episodes",
        )
    return _subset(dataset, train_index), _subset(dataset, test_index)


def fit_rows(rows: Sequence[Sequence[float]]) -> Standardiser:
    width = len(rows[0])
    means: list[float] = []
    scales: list[float] = []
    for column in range(width):
        values = [row[column] for row in rows]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        means.append(mean)
        scales.append(variance**0.5 or 1.0)
    return Standardiser(means=tuple(means), scales=tuple(scales))


def fit_standardiser(dataset: Dataset) -> Standardiser:
    return fit_rows(dataset.rows)


def _subset(dataset: Dataset, index: Sequence[int]) -> Dataset:
    return Dataset(
        rows=tuple(dataset.rows[i] for i in index),
        labels=tuple(dataset.labels[i] for i in index),
        seeds=tuple(dataset.seeds[i] for i in index),
        versions=tuple(dataset.versions[i] for i in index),
    )
