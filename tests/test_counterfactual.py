from __future__ import annotations

import pytest

from crux.errors import CruxError
from crux.repair.counterfactual import Candidate, SearchOutcome, best, fan, improvement


def outcome(index: int, seated: bool, lateral_m: float) -> SearchOutcome:
    return SearchOutcome(
        candidate=Candidate(index=index, offset_x_m=0.0, offset_y_m=0.0),
        seated=seated,
        lateral_m=lateral_m,
        depth_m=0.004,
    )


def test_the_nominal_action_is_always_candidate_zero() -> None:
    candidates = fan(count=8, radius_m=0.01)
    assert candidates[0] == Candidate(index=0, offset_x_m=0.0, offset_y_m=0.0)
    assert len(candidates) == 8
    assert [candidate.index for candidate in candidates] == list(range(8))


def test_candidates_stay_inside_the_requested_radius() -> None:
    radius = 0.012
    for candidate in fan(count=16, radius_m=radius, rings=3):
        assert (candidate.offset_x_m**2 + candidate.offset_y_m**2) ** 0.5 <= radius + 1e-9


def test_rings_spread_candidates_at_more_than_one_distance() -> None:
    distances = {
        round((candidate.offset_x_m**2 + candidate.offset_y_m**2) ** 0.5, 6)
        for candidate in fan(count=12, radius_m=0.01, rings=2)
    }
    assert len(distances) == 3


def test_a_single_candidate_search_is_just_the_nominal_action() -> None:
    assert fan(count=1, radius_m=0.01) == (Candidate(index=0, offset_x_m=0.0, offset_y_m=0.0),)


@pytest.mark.parametrize(("count", "radius", "rings"), [(0, 0.01, 2), (8, 0.0, 2), (8, 0.01, 0)])
def test_invalid_search_shapes_fail_loudly(count: int, radius: float, rings: int) -> None:
    with pytest.raises(CruxError):
        fan(count=count, radius_m=radius, rings=rings)


def test_a_seated_future_always_beats_a_closer_unseated_one() -> None:
    chosen = best([outcome(0, False, 0.001), outcome(3, True, 0.009)])
    assert chosen.candidate.index == 3


def test_the_closest_seated_future_wins() -> None:
    chosen = best([outcome(1, True, 0.008), outcome(2, True, 0.003), outcome(3, True, 0.006)])
    assert chosen.candidate.index == 2


def test_ties_resolve_to_the_earlier_candidate() -> None:
    assert best([outcome(5, True, 0.004), outcome(2, True, 0.004)]).candidate.index == 2


def test_with_nothing_seated_the_closest_future_is_still_reported() -> None:
    chosen = best([outcome(0, False, 0.02), outcome(1, False, 0.011)])
    assert chosen.candidate.index == 1
    assert not chosen.seated


def test_improvement_reports_the_nominal_and_the_chosen_outcome() -> None:
    assert improvement([outcome(0, False, 0.02), outcome(1, True, 0.005)]) == (False, True)
    assert improvement([outcome(0, True, 0.004), outcome(1, False, 0.02)]) == (True, True)


def test_a_search_without_the_nominal_action_is_rejected() -> None:
    with pytest.raises(CruxError):
        improvement([outcome(1, True, 0.004)])


def test_choosing_from_nothing_fails_loudly() -> None:
    with pytest.raises(CruxError):
        best([])
