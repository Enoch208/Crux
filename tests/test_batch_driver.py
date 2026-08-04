from __future__ import annotations

import pytest

from crux.control.batch_driver import (
    EnvironmentTrack,
    active_tracks,
    finger_forces,
    held_links,
    ik_is_stale,
    outcomes,
    start_track,
    targets,
)
from crux.control.policy import EpisodePolicy
from crux.failures.taxonomy import ReasonCode
from tests.test_policy import FakeWorld, config, knobs

HOME = (0.30, -0.30, 0.40)
MAX_CHUNKS = 20000


def build(count: int) -> tuple[list[EnvironmentTrack], list[FakeWorld]]:
    task = config()
    worlds = [FakeWorld(task) for _ in range(count)]
    tracks = [
        start_track(EpisodePolicy(task, knobs()), world.observation(), HOME) for world in worlds
    ]
    return tracks, worlds


def run_batch(tracks: list[EnvironmentTrack], worlds: list[FakeWorld]) -> int:
    for chunk in range(MAX_CHUNKS):
        if active_tracks(tracks) == 0:
            return chunk
        for track, world in zip(tracks, worlds, strict=True):
            if not track.active:
                continue
            world.held_index = track.held_link
            world.apply_target(track.target_pos, track.finger_force)
            track.resume(world.observation())
    raise AssertionError("batch never drained")


def test_every_environment_finishes_and_reports_success() -> None:
    tracks, worlds = build(4)
    run_batch(tracks, worlds)
    finished = outcomes(tracks)
    assert len(finished) == 4
    assert all(outcome.reason_code is ReasonCode.SUCCESS for outcome in finished)


def test_targets_are_gathered_per_environment() -> None:
    tracks, _ = build(3)
    positions, quats = targets(tracks)
    assert len(positions) == 3
    assert all(len(row) == 3 for row in positions)
    assert all(len(row) == 4 for row in quats)


def test_ik_is_stale_only_while_a_target_is_changing() -> None:
    tracks, worlds = build(1)
    assert ik_is_stale(tracks)
    track, world = tracks[0], worlds[0]
    world.apply_target(track.target_pos, track.finger_force)
    track.resume(world.observation())
    assert not ik_is_stale(tracks)


def test_idle_environments_receive_the_idle_finger_force() -> None:
    tracks, worlds = build(2)
    run_batch(tracks, worlds)
    assert finger_forces(tracks, idle_force=5.0) == [5.0, 5.0]


def test_held_links_track_each_policy_independently() -> None:
    tracks, _ = build(2)
    assert held_links(tracks) == [None, None]


def test_gathering_outcomes_before_everyone_finishes_is_an_error() -> None:
    tracks, _ = build(2)
    with pytest.raises(ValueError, match="never finished"):
        outcomes(tracks)


def test_resume_reports_the_chunk_that_ends_the_episode() -> None:
    tracks, worlds = build(1)
    track, world = tracks[0], worlds[0]
    endings = 0
    for _ in range(MAX_CHUNKS):
        world.held_index = track.held_link
        world.apply_target(track.target_pos, track.finger_force)
        if track.resume(world.observation()):
            endings += 1
            break
    assert endings == 1
    assert not track.resume(world.observation())


def test_settling_environments_are_flagged_to_hold_their_pose() -> None:
    from crux.control.batch_driver import settling_mask

    tracks, worlds = build(1)
    track, world = tracks[0], worlds[0]
    seen = {True: 0, False: 0}
    for _ in range(MAX_CHUNKS):
        if not track.active:
            break
        seen[track.settling] += 1
        world.held_index = track.held_link
        world.apply_target(track.target_pos, track.finger_force)
        track.resume(world.observation())
    assert seen[True] > 0
    assert seen[False] > 0
    assert settling_mask(tracks) == [True]
