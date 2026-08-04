from __future__ import annotations

from pathlib import Path

import genesis as gs

from crux.simulation.gate1 import TIMESTEP_S, stage

OUTPUT_DIR = Path("evidence-dev/render")
PROBE_FRAMES = 12
RESOLUTION = (640, 480)
CAMERA_POS = (1.1, -0.6, 0.7)
CAMERA_LOOKAT = (0.46, 0.0, 0.05)


def describe(label: str, target: object, needle: str) -> None:
    names = sorted(name for name in dir(target) if needle in name.lower())
    print(f"  {label}: {names or 'none'}", flush=True)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    gs.init(backend=gs.amdgpu)

    print("\n=== camera API surface ===", flush=True)
    describe("gs.options", gs.options, "render")
    scene = gs.Scene(sim_options=gs.options.SimOptions(dt=TIMESTEP_S), show_viewer=False)
    describe("scene", scene, "camera")
    describe("scene", scene, "record")

    scene.add_entity(gs.morphs.Plane())
    scene.add_entity(gs.morphs.Box(pos=(0.46, 0.0, 0.05), size=(0.1, 0.1, 0.1), fixed=True))

    add_camera = getattr(scene, "add_camera", None)
    if not callable(add_camera):
        print("\nFAIL: scene.add_camera is unavailable on this build", flush=True)
        return 1

    camera = add_camera(res=RESOLUTION, pos=CAMERA_POS, lookat=CAMERA_LOOKAT, fov=45)
    print(f"\ncamera object: {type(camera).__name__}", flush=True)
    describe("camera", camera, "record")
    describe("camera", camera, "render")

    stage("build scene with camera", scene.build)

    frame = getattr(camera, "render")()
    shapes = [getattr(item, "shape", type(item).__name__) for item in frame]
    print(f"\nsingle render() returned {len(frame)} buffer(s): {shapes}", flush=True)

    video_path = OUTPUT_DIR / "probe.mp4"
    getattr(camera, "start_recording")()
    for _ in range(PROBE_FRAMES):
        scene.step()
        getattr(camera, "render")()
    getattr(camera, "stop_recording")(save_to_filename=str(video_path), fps=30)

    if not video_path.exists():
        print(f"\nFAIL: no file written at {video_path}", flush=True)
        return 1
    print(f"\nPASS: wrote {video_path} ({video_path.stat().st_size} bytes)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
