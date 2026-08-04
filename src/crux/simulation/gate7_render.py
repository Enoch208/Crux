from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from crux.failures.taxonomy import ReasonCode, TaskStage, stage_index
from crux.repair.knobs import ControllerKnobs
from crux.simulation.episodes import knobs_for, run_episode, sample_params
from crux.simulation.gate1 import stage
from crux.simulation.recording import claim_video, save_recording
from crux.simulation.taskconfig import load_task_config
from crux.simulation.taskscene import build_task_scene

OUTPUT_DIR = Path("evidence-dev/render")
WORKING_DIR = Path()
SEEDS = (101, 103, 105, 107, 109)
NOMINAL_SEED = 101
CONTROLLER = "baseline-v1"


@dataclass(frozen=True, slots=True)
class RenderedEpisode:
    seed: int
    reason_code: ReasonCode
    task_stage: TaskStage
    steps: int
    path: Path


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config = load_task_config()
    scene = stage("build task scene with camera", lambda: build_task_scene(config, record=True))
    if scene.camera is None:
        print("FAIL: scene built without a camera", flush=True)
        return 1

    base_knobs = ControllerKnobs.baseline(config)
    rendered: list[RenderedEpisode] = []

    for seed in SEEDS:
        params = sample_params(seed, config, NOMINAL_SEED)
        knobs = knobs_for(base_knobs, params)
        target = OUTPUT_DIR / f"{CONTROLLER}-seed{seed}.mp4"
        started = time.time()

        getattr(scene.camera, "start_recording")()
        outcome = run_episode(scene, knobs, params)
        if not save_recording(scene.camera, target, config.render.fps) and (
            claim_video(WORKING_DIR, target, started) is None
        ):
            print(f"FAIL: seed {seed} produced no video file", flush=True)
            return 1
        if not target.exists():
            print(f"FAIL: seed {seed} left no video at {target}", flush=True)
            return 1

        rendered.append(
            RenderedEpisode(seed, outcome.reason_code, outcome.task_stage, outcome.steps, target)
        )
        print(
            f"  seed {seed}: {outcome.reason_code} at {outcome.task_stage} "
            f"after {outcome.steps} steps -> {target} ({target.stat().st_size} bytes)",
            flush=True,
        )

    deepest = max(rendered, key=lambda episode: stage_index(episode.task_stage))
    print("\n=== rendered episodes ===")
    for episode in rendered:
        marker = "  <- deepest, use this for the demo" if episode is deepest else ""
        print(
            f"  seed {episode.seed}: {episode.reason_code} at {episode.task_stage} "
            f"-> {episode.path}{marker}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
