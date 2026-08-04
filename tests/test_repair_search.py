from __future__ import annotations

from crux.failures.taxonomy import ReasonCode, TaskStage
from crux.repair.search import Attempt, advances, best_of


def attempt(
    name: str,
    task_stage: TaskStage,
    steps: int = 1000,
    reason_code: ReasonCode = ReasonCode.CABLE_SLIP,
) -> Attempt:
    return Attempt(candidate_name=name, reason_code=reason_code, task_stage=task_stage, steps=steps)


def test_best_of_returns_none_without_attempts() -> None:
    assert best_of(()) is None


def test_success_outranks_any_failure() -> None:
    seated = attempt("a", TaskStage.VERIFY_SEATED, 9000, ReasonCode.SUCCESS)
    deep_failure = attempt("b", TaskStage.INSERT_CONNECTOR, 10)
    assert best_of((deep_failure, seated)) is seated


def test_a_later_failure_stage_outranks_an_earlier_one() -> None:
    early = attempt("a", TaskStage.VERIFY_CLIP_1)
    late = attempt("b", TaskStage.VERIFY_CLIP_2)
    assert best_of((early, late)) is late


def test_fewer_steps_breaks_a_stage_tie() -> None:
    slow = attempt("a", TaskStage.VERIFY_CLIP_2, steps=8000)
    quick = attempt("b", TaskStage.VERIFY_CLIP_2, steps=4000)
    assert best_of((slow, quick)) is quick


def test_advancing_requires_a_strictly_later_stage() -> None:
    assert advances(attempt("a", TaskStage.VERIFY_CLIP_2), TaskStage.VERIFY_CLIP_1)
    assert not advances(attempt("a", TaskStage.VERIFY_CLIP_1), TaskStage.VERIFY_CLIP_1)
    assert not advances(attempt("a", TaskStage.ROUTE_CLIP_1), TaskStage.VERIFY_CLIP_1)


def test_success_always_advances() -> None:
    seated = attempt("a", TaskStage.VERIFY_SEATED, reason_code=ReasonCode.SUCCESS)
    assert advances(seated, TaskStage.VERIFY_SEATED)


def test_the_observed_seed_103_repair_counts_as_progress() -> None:
    shallower_settle = attempt("shallower-settle", TaskStage.VERIFY_CLIP_2, steps=6627)
    assert advances(shallower_settle, TaskStage.VERIFY_CLIP_1)
