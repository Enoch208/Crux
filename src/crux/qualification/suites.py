from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import StrEnum

from crux.errors import ErrorCode, QualificationError


class SuiteName(StrEnum):
    STANDARD = "standard"
    PRIMARY = "primary"
    ADVERSARIAL = "adversarial"
    HELDOUT = "heldout"
    RECOVERY = "recovery"


REGRESSION_SUITE = SuiteName.STANDARD
GENERALIZATION_SUITE = SuiteName.HELDOUT


def assert_heldout_uncontaminated(
    heldout_seeds: Iterable[int],
    repair_seeds: Iterable[int],
) -> None:
    overlap = sorted(set(heldout_seeds) & set(repair_seeds))
    if overlap:
        raise QualificationError(
            ErrorCode.SUITE_CONTAMINATED,
            f"{len(overlap)} seed(s) appear in both the held-out suite and repair generation: "
            f"{overlap[:10]}",
        )


def assert_suites_disjoint(seeds_by_suite: Mapping[SuiteName, Iterable[int]]) -> None:
    materialized = {suite: set(seeds) for suite, seeds in seeds_by_suite.items()}
    names = sorted(materialized, key=str)
    for left_index, left in enumerate(names):
        for right in names[left_index + 1 :]:
            overlap = sorted(materialized[left] & materialized[right])
            if overlap:
                raise QualificationError(
                    ErrorCode.SUITE_CONTAMINATED,
                    f"suites {left} and {right} share {len(overlap)} seed(s): {overlap[:10]}",
                )
