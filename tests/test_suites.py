from __future__ import annotations

import pytest

from crux.errors import ErrorCode, QualificationError
from crux.qualification.suites import (
    SuiteName,
    assert_heldout_uncontaminated,
    assert_suites_disjoint,
)


def test_disjoint_heldout_and_repair_seeds_are_accepted() -> None:
    assert_heldout_uncontaminated([1, 2, 3], [4, 5, 6])


def test_heldout_contamination_is_rejected() -> None:
    with pytest.raises(QualificationError) as caught:
        assert_heldout_uncontaminated([1, 2, 3], [3, 4, 5])
    assert caught.value.code is ErrorCode.SUITE_CONTAMINATED
    assert "[3]" in caught.value.message


def test_suites_may_not_share_seeds() -> None:
    with pytest.raises(QualificationError) as caught:
        assert_suites_disjoint(
            {
                SuiteName.STANDARD: [1, 2],
                SuiteName.HELDOUT: [2, 3],
            }
        )
    assert caught.value.code is ErrorCode.SUITE_CONTAMINATED


def test_fully_disjoint_suites_are_accepted() -> None:
    assert_suites_disjoint(
        {
            SuiteName.STANDARD: [1, 2],
            SuiteName.PRIMARY: [3, 4],
            SuiteName.ADVERSARIAL: [5, 6],
            SuiteName.HELDOUT: [7, 8],
            SuiteName.RECOVERY: [9],
        }
    )
