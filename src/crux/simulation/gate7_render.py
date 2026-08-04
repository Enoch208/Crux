from __future__ import annotations

from pathlib import Path

from crux.repair.knobs import ControllerKnobs
from crux.simulation.episodes import knobs_for, run_episode, sample_params
from crux.simulation.gate1 import stage
from crux.simulation.recording import save_recording
from crux.simulation.taskconfig import load_task_config
from crux.simulation.taskscene import build_task_scene

OUTPUT_DIR = Path("evidence-dev/render")
SEED = 101


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config = load_task_config()
    scene = stage("build task scene with camera", lambda: build_task_scene(config, record=True))
    if scene.camera is None:
        print("FAIL: scene built without a camera", flush=True)
        return 1

    params = sample_params(SEED, config, SEED)
    knobs = knobs_for(ControllerKnobs.baseline(config), params)
    video = OUTPUT_DIR / f"baseline-v1-seed{SEED}.mp4"

    getattr(scene.camera, "start_recording")()
    outcome = run_episode(scene, knobs, params)
    named = save_recording(scene.camera, video, config.render.fps)

    print(
        f"\nepisode: {outcome.reason_code} at {outcome.task_stage} after {outcome.steps} steps",
        flush=True,
    )
    if not named:
        print(
            "note: this Genesis build names the file itself; check the path it logged above",
            flush=True,
        )
        return 0
    if not video.exists():
        print(f"FAIL: no file written at {video}", flush=True)
        return 1
    print(f"PASS: wrote {video} ({video.stat().st_size} bytes)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
