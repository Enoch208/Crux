from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from crux.simulation.recording import (
    claim_video,
    frame_interval,
    newest_video,
    recording_kwargs,
    recording_step,
    save_recording,
)

VIDEO = Path("/tmp/clip.mp4")


def test_frame_interval_matches_the_simulation_rate() -> None:
    assert frame_interval(fps=30, timestep_s=0.005) == 7
    assert frame_interval(fps=200, timestep_s=0.005) == 1


def test_frame_interval_never_drops_below_one() -> None:
    assert frame_interval(fps=1000, timestep_s=0.005) == 1


def test_frame_interval_rejects_nonsense() -> None:
    with pytest.raises(ValueError, match="fps must be positive"):
        frame_interval(fps=0, timestep_s=0.005)
    with pytest.raises(ValueError, match="timestep must be positive"):
        frame_interval(fps=30, timestep_s=0.0)


def test_recording_step_captures_the_first_and_every_nth_frame() -> None:
    steps: list[int] = []
    frames: list[int] = []
    stepped = recording_step(lambda: steps.append(1), lambda: frames.append(1), interval=3)
    for _ in range(7):
        stepped()
    assert len(steps) == 7
    assert len(frames) == 3


def test_recording_step_rejects_a_zero_interval() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        recording_step(lambda: None, lambda: None, interval=0)


def test_filename_and_fps_are_both_supplied_when_accepted() -> None:
    def stop(save_to_filename: str | None = None, fps: int = 30) -> None: ...

    assert recording_kwargs(stop, VIDEO, 24) == {
        "save_to_filename": str(VIDEO),
        "fps": 24,
    }


def test_the_alternate_filename_spelling_is_used() -> None:
    def stop(filename: str | None = None) -> None: ...

    assert recording_kwargs(stop, VIDEO, 24) == {"filename": str(VIDEO)}


def test_a_signature_without_a_filename_gets_no_filename() -> None:
    def stop(fps: int = 30) -> None: ...

    assert recording_kwargs(stop, VIDEO, 24) == {"fps": 24}


def test_a_bare_signature_gets_nothing() -> None:
    def stop() -> None: ...

    assert recording_kwargs(stop, VIDEO, 24) == {}


def test_newest_video_ignores_files_written_before_the_run(tmp_path: Path) -> None:
    stale = tmp_path / "stale.mp4"
    stale.write_bytes(b"old")
    os.utime(stale, (1000.0, 1000.0))
    assert newest_video(tmp_path, since=2000.0) is None


def test_newest_video_picks_the_most_recent(tmp_path: Path) -> None:
    for name, when in (("a.mp4", 3000.0), ("b.mp4", 4000.0)):
        path = tmp_path / name
        path.write_bytes(b"x")
        os.utime(path, (when, when))
    found = newest_video(tmp_path, since=2000.0)
    assert found is not None
    assert found.name == "b.mp4"


def test_claim_video_moves_the_file_to_the_target(tmp_path: Path) -> None:
    source_dir = tmp_path / "cwd"
    source_dir.mkdir()
    produced = source_dir / "auto_cam_0.mp4"
    produced.write_bytes(b"frames")
    target = tmp_path / "evidence" / "episode.mp4"
    claimed = claim_video(source_dir, target, since=0.0)
    assert claimed == target
    assert target.read_bytes() == b"frames"
    assert not produced.exists()


def test_claim_video_returns_none_when_nothing_was_written(tmp_path: Path) -> None:
    assert claim_video(tmp_path, tmp_path / "out.mp4", since=0.0) is None


def test_save_recording_reports_whether_it_named_the_file() -> None:
    calls: list[dict[str, Any]] = []

    class NamedCamera:
        def stop_recording(self, save_to_filename: str | None = None, fps: int = 30) -> None:
            calls.append({"save_to_filename": save_to_filename, "fps": fps})

    class AnonymousCamera:
        def stop_recording(self) -> None:
            calls.append({})

    assert save_recording(NamedCamera(), VIDEO, 24) is True
    assert calls[-1]["save_to_filename"] == str(VIDEO)
    assert save_recording(AnonymousCamera(), VIDEO, 24) is False
