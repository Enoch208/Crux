from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import cos, pi, sin

from crux.errors import CruxError, ErrorCode


@dataclass(frozen=True)
class Candidate:
    """One alternative action to try from a restored state."""

    index: int
    offset_x_m: float
    offset_y_m: float

    @property
    def label(self) -> str:
        return f"({self.offset_x_m * 1000:+.1f}, {self.offset_y_m * 1000:+.1f}) mm"


@dataclass(frozen=True)
class SearchOutcome:
    candidate: Candidate
    seated: bool
    lateral_m: float
    depth_m: float


def fan(count: int, radius_m: float, rings: int = 2) -> tuple[Candidate, ...]:
    """Lay `count` candidate offsets over concentric rings around the nominal action.

    The nominal action is always candidate 0, so a search can never score worse than
    doing nothing: the policy's own choice is one of the futures being compared.
    """
    if count < 1:
        raise CruxError(ErrorCode.SAMPLE_INVALID, f"need at least one candidate, got {count}")
    if radius_m <= 0.0:
        raise CruxError(ErrorCode.SAMPLE_INVALID, f"radius must be positive, got {radius_m}")
    if rings < 1:
        raise CruxError(ErrorCode.SAMPLE_INVALID, f"need at least one ring, got {rings}")
    candidates = [Candidate(index=0, offset_x_m=0.0, offset_y_m=0.0)]
    remaining = count - 1
    if remaining <= 0:
        return tuple(candidates)
    per_ring = [remaining // rings] * rings
    for extra in range(remaining % rings):
        per_ring[extra] += 1
    index = 1
    for ring, points in enumerate(per_ring, start=1):
        scale = radius_m * ring / rings
        for point in range(points):
            angle = 2.0 * pi * point / points
            candidates.append(
                Candidate(
                    index=index,
                    offset_x_m=scale * cos(angle),
                    offset_y_m=scale * sin(angle),
                )
            )
            index += 1
    return tuple(candidates)


def best(outcomes: Sequence[SearchOutcome]) -> SearchOutcome:
    """The seated outcome closest to the socket, or the closest one if none seated."""
    if not outcomes:
        raise CruxError(ErrorCode.SAMPLE_EMPTY, "no counterfactual outcomes to choose from")
    seated = [outcome for outcome in outcomes if outcome.seated]
    pool = seated or list(outcomes)
    return min(pool, key=lambda outcome: (outcome.lateral_m, outcome.candidate.index))


def improvement(outcomes: Sequence[SearchOutcome]) -> tuple[bool, bool]:
    """Whether the nominal action seated, and whether the chosen one did."""
    nominal = next((o for o in outcomes if o.candidate.index == 0), None)
    if nominal is None:
        raise CruxError(ErrorCode.SAMPLE_INVALID, "candidate 0 (the nominal action) is missing")
    return nominal.seated, best(outcomes).seated
