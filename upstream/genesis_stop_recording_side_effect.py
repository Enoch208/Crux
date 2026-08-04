"""Minimal reproduction: a failed `stop_recording` call still writes a video, elsewhere.

Genesis 1.3.1, AMD Radeon PRO W7900 (gfx1100), ROCm 7.2.1.

`Camera.stop_recording()` on this version does not accept a `save_to_filename` keyword.
Calling it with one raises `TypeError`, which is reasonable on its own. What is surprising
is that the recording is still flushed to disk during teardown, under a name derived from
the entry-point module - for a `python -m` invocation that is literally
`<frozen runpy>_cam_0_<timestamp>.mp4` in the working directory.

So a caller whose save failed with an exception ends up with a video file they did not name,
in a directory they did not choose, with a name containing angle brackets. A caller that
handles the TypeError and moves on never learns the file exists.

Expected: either the keyword is accepted, or the failed call leaves no artefact behind.
"""

from __future__ import annotations

from pathlib import Path

import genesis as gs

FRAMES = 12
RESOLUTION = (320, 240)


def mp4_files() -> set[Path]:
    return set(Path().glob("*.mp4"))


def main() -> int:
    gs.init(backend=gs.gpu)
    scene = gs.Scene(sim_options=gs.options.SimOptions(dt=0.005), show_viewer=False)
    scene.add_entity(gs.morphs.Plane())
    scene.add_entity(gs.morphs.Box(pos=(0.0, 0.0, 0.1), size=(0.1, 0.1, 0.1), fixed=True))
    camera = scene.add_camera(res=RESOLUTION, pos=(0.6, -0.6, 0.5), lookat=(0.0, 0.0, 0.1), fov=45)
    scene.build()

    before = mp4_files()
    camera.start_recording()
    for _ in range(FRAMES):
        scene.step()
        camera.render()

    target = Path("intended-name.mp4")
    try:
        camera.stop_recording(save_to_filename=str(target))
    except TypeError as error:
        print(f"stop_recording raised TypeError: {error}")

    appeared = sorted(path.name for path in mp4_files() - before)
    print(f"caller asked for: {target}")
    print(f"caller got:       {appeared or 'nothing'}")
    print(f"intended file exists: {target.exists()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
