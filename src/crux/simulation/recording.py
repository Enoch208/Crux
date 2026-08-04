from __future__ import annotations

import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any

FILENAME_PARAMETERS = ("save_to_filename", "filename", "path", "save_to", "file")
FPS_PARAMETER = "fps"


def frame_interval(fps: int, timestep_s: float) -> int:
    if fps <= 0:
        raise ValueError(f"fps must be positive, got {fps}")
    if timestep_s <= 0.0:
        raise ValueError(f"timestep must be positive, got {timestep_s}")
    return max(1, round(1.0 / (fps * timestep_s)))


def recording_step(
    step: Callable[[], object],
    render: Callable[[], object],
    interval: int,
) -> Callable[[], object]:
    if interval < 1:
        raise ValueError(f"interval must be at least 1, got {interval}")
    taken = 0

    def stepped() -> object:
        nonlocal taken
        result = step()
        if taken % interval == 0:
            render()
        taken += 1
        return result

    return stepped


def recording_kwargs(stop: Callable[..., Any], path: Path, fps: int) -> dict[str, Any]:
    parameters = inspect.signature(stop).parameters
    kwargs: dict[str, Any] = {}
    for name in FILENAME_PARAMETERS:
        if name in parameters:
            kwargs[name] = str(path)
            break
    if FPS_PARAMETER in parameters:
        kwargs[FPS_PARAMETER] = fps
    return kwargs


def save_recording(camera: object, path: Path, fps: int) -> bool:
    stop = getattr(camera, "stop_recording")
    kwargs = recording_kwargs(stop, path, fps)
    stop(**kwargs)
    return any(name in kwargs for name in FILENAME_PARAMETERS)
