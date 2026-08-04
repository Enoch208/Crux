from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from crux.simulation.recording import (
    frame_interval,
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
