from __future__ import annotations

from dataclasses import dataclass

from crux.control.directives import Directive, Finish, Observation, Reach, Settle
from crux.control.policy import EpisodePolicy, Plan
from crux.control.tooling import TOOL_DOWN_QUAT

Vector = tuple[float, float, float]
Quaternion = tuple[float, float, float, float]


@dataclass(slots=True)
class EnvironmentTrack:
    """Drives one policy generator and remembers its latest control target."""

    policy: EpisodePolicy
    plan: Plan
    target_pos: Vector
    target_quat: Quaternion = TOOL_DOWN_QUAT
    finger_force: float = 0.0
    outcome: Finish | None = None
    needs_ik: bool = False
    settling: bool = False

    @property
    def active(self) -> bool:
        return self.outcome is None

    @property
    def held_link(self) -> int | None:
        return self.policy.held_link

    def accept(self, directive: Directive) -> None:
        if isinstance(directive, Finish):
            self.outcome = directive
            self.needs_ik = False
            return
        if isinstance(directive, Reach):
            self.needs_ik = (directive.pos, directive.quat) != (self.target_pos, self.target_quat)
            self.target_pos = directive.pos
            self.target_quat = directive.quat
            self.settling = False
        else:
            self.needs_ik = False
            self.settling = True
        self.finger_force = directive.finger_force

    def resume(self, observation: Observation) -> bool:
        """Advance one chunk; returns True when this chunk ended the episode."""
        if self.outcome is not None:
            return False
        self.accept(self.plan.send(observation))
        return self.outcome is not None


def start_track(policy: EpisodePolicy, observation: Observation, home: Vector) -> EnvironmentTrack:
    plan = policy.run(observation)
    track = EnvironmentTrack(policy=policy, plan=plan, target_pos=home)
    track.accept(next(plan))
    return track


def active_tracks(tracks: list[EnvironmentTrack]) -> int:
    return sum(1 for track in tracks if track.active)


def ik_is_stale(tracks: list[EnvironmentTrack]) -> bool:
    return any(track.needs_ik for track in tracks if track.active)


def finger_forces(tracks: list[EnvironmentTrack], idle_force: float) -> list[float]:
    return [track.finger_force if track.active else idle_force for track in tracks]


def held_links(tracks: list[EnvironmentTrack]) -> list[int | None]:
    return [track.held_link for track in tracks]


def settling_mask(tracks: list[EnvironmentTrack]) -> list[bool]:
    """A settling environment must hold its current pose, not chase a stale reach target."""
    return [track.settling or not track.active for track in tracks]


def targets(tracks: list[EnvironmentTrack]) -> tuple[list[list[float]], list[list[float]]]:
    return (
        [list(track.target_pos) for track in tracks],
        [list(track.target_quat) for track in tracks],
    )


def outcomes(tracks: list[EnvironmentTrack]) -> list[Finish]:
    missing = [index for index, track in enumerate(tracks) if track.outcome is None]
    if missing:
        raise ValueError(f"environments {missing} never finished")
    return [track.outcome for track in tracks if track.outcome is not None]


__all__ = [
    "EnvironmentTrack",
    "Settle",
    "active_tracks",
    "finger_forces",
    "held_links",
    "ik_is_stale",
    "outcomes",
    "settling_mask",
    "start_track",
    "targets",
]
