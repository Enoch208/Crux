from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from crux.errors import CruxError, ErrorCode


@dataclass(frozen=True)
class TriageScore:
    """How well a risk ranking finds failures compared with testing at random."""

    budget: int
    failures_found: int
    failures_total: int
    random_expectation: float

    @property
    def lift(self) -> float:
        if self.random_expectation <= 0.0:
            return 0.0
        return self.failures_found / self.random_expectation


def roc_auc(labels: Sequence[int], scores: Sequence[float]) -> float:
    """Probability a random failure outranks a random success; 0.5 is chance."""
    if len(labels) != len(scores):
        raise CruxError(ErrorCode.SAMPLE_INVALID, "labels and scores differ in length")
    positives = [score for label, score in zip(labels, scores, strict=True) if label == 1]
    negatives = [score for label, score in zip(labels, scores, strict=True) if label == 0]
    if not positives or not negatives:
        raise CruxError(
            ErrorCode.SAMPLE_INVALID, "ROC AUC needs at least one failure and one success"
        )
    wins = 0.0
    for positive in positives:
        for negative in negatives:
            if positive > negative:
                wins += 1.0
            elif positive == negative:
                wins += 0.5
    return wins / (len(positives) * len(negatives))


def brier_score(labels: Sequence[int], probabilities: Sequence[float]) -> float:
    if len(labels) != len(probabilities):
        raise CruxError(ErrorCode.SAMPLE_INVALID, "labels and probabilities differ in length")
    if not labels:
        raise CruxError(ErrorCode.SAMPLE_EMPTY, "no rows to score")
    return sum(
        (probability - label) ** 2 for label, probability in zip(labels, probabilities, strict=True)
    ) / len(labels)


def accuracy(
    labels: Sequence[int], probabilities: Sequence[float], threshold: float = 0.5
) -> float:
    if not labels:
        raise CruxError(ErrorCode.SAMPLE_EMPTY, "no rows to score")
    correct = sum(
        1
        for label, probability in zip(labels, probabilities, strict=True)
        if (probability >= threshold) == bool(label)
    )
    return correct / len(labels)


def triage_at_budget(labels: Sequence[int], scores: Sequence[float], budget: int) -> TriageScore:
    """Failures caught when only `budget` of the riskiest conditions are run."""
    if budget <= 0 or budget > len(labels):
        raise CruxError(
            ErrorCode.SAMPLE_INVALID, f"budget {budget} outside 1..{len(labels)} episodes"
        )
    order = sorted(range(len(labels)), key=lambda i: scores[i], reverse=True)
    found = sum(labels[i] for i in order[:budget])
    total = sum(labels)
    return TriageScore(
        budget=budget,
        failures_found=found,
        failures_total=total,
        random_expectation=total * budget / len(labels),
    )
