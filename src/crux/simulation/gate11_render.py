from __future__ import annotations

import time
from pathlib import Path

from crux.control.batch_driver import (
    finger_forces,
    held_links,
    ik_is_stale,
    settling_mask,
    start_track,
    targets,
)
from crux.control.policy import EpisodePolicy
from crux.repair.knobs import ControllerKnobs
from crux.simulation.batchscene import build_batch_scene
from crux.simulation.episodes import sample_params
from crux.simulation.gate1 import stage
from crux.simulation.gate10_qualify import CANDIDATE_OVERRIDES, NOMINAL_SEED
from crux.simulation.recording import claim_video, save_recording
from crux.simulation.taskconfig import load_task_config

OUTPUT_DIR = Path("evidence-dev/render")
WORKING_DIR = Path()
SEEDS = (301, 305, 309, 313)
MAX_CHUNKS = 900


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config = load_task_config()
    scene = stage("build recording scene", lambda: build_batch_scene(config, 1, record=True))
    if scene.camera is None:
        print("FAIL: no camera on the recording scene", flush=True)
        return 1
    base = ControllerKnobs.baseline(config)
    chunk = config.control.chunk_steps

    for seed in SEEDS:
        params = sample_params(seed, config, NOMINAL_SEED)
        knobs = base.with_overrides({**CANDIDATE_OVERRIDES, "route_z_m": params["route_z_m"]})
        scene.reset_all([(params["cable_dx"], params["cable_dy"])])
        observations = scene.observations(0, [None])
        hand = scene.hand_positions().detach().cpu()
        home = (float(hand[0][0]), float(hand[0][1]), float(hand[0][2]))
        track = start_track(
            EpisodePolicy(config, knobs, timestep_s=scene.timestep_s), observations[0], home
        )
        tracks = [track]

        target = OUTPUT_DIR / f"candidate-v2-seed{seed}.mp4"
        started = time.time()
        getattr(scene.camera, "start_recording")()
        arm_targets = None
        for chunks_run in range(1, MAX_CHUNKS + 1):
            if not track.active:
                break
            if arm_targets is None or ik_is_stale(tracks):
                positions, quats = targets(tracks)
                arm_targets = scene.solve_ik(positions, quats)
            scene.command(
                arm_targets,
                finger_forces(tracks, config.control.open_force_n),
                settling_mask(tracks),
            )
            scene.step(chunk)
            observations = scene.observations(chunks_run * chunk, held_links(tracks))
            track.resume(observations[0])
        named = save_recording(scene.camera, target, config.render.fps)
        if not named and claim_video(WORKING_DIR, target, started) is None:
            print(f"FAIL: seed {seed} produced no video", flush=True)
            return 1

        outcome = track.outcome
        result = (
            f"{outcome.reason_code} at {outcome.task_stage}"
            if outcome is not None
            else "unfinished"
        )
        print(f"  seed {seed}: {result} -> {target} ({target.stat().st_size} bytes)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
