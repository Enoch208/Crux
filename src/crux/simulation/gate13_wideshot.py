from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from crux.control.batch_driver import (
    EnvironmentTrack,
    active_tracks,
    finger_forces,
    held_links,
    ik_is_stale,
    settling_mask,
    start_track,
    targets,
)
from crux.control.policy import EpisodePolicy
from crux.errors import BackendError, ErrorCode
from crux.repair.knobs import ControllerKnobs
from crux.simulation.batchscene import BatchTaskScene, build_batch_scene
from crux.simulation.episodes import sample_params
from crux.simulation.gate1 import stage
from crux.simulation.gate10_qualify import CANDIDATE_OVERRIDES, NOMINAL_SEED
from crux.simulation.recording import claim_video, save_recording
from crux.simulation.taskconfig import load_task_config

OUTPUT_DIR = Path("evidence-dev/render")
TELEMETRY_PATH = Path("evidence-dev/telemetry_wideshot.log")
WORKING_DIR = Path()
SEEDS = tuple(range(101, 117))
MAX_CHUNKS = 900
TELEMETRY_EVERY_CHUNKS = 20
LAYOUT_TOLERANCE_M = 0.6
ROCM_SMI_ARGS = ("rocm-smi", "--showuse", "--showmemuse", "--showpower", "--showtemp")


def sample_telemetry(chunk: int) -> None:
    result = subprocess.run(ROCM_SMI_ARGS, capture_output=True, text=True, check=True)
    with TELEMETRY_PATH.open("a", encoding="utf-8") as log:
        log.write(f"=== chunk {chunk} wall {time.strftime('%H:%M:%S')} ===\n")
        log.write(result.stdout)


def assert_layout_aligned(scene: BatchTaskScene) -> None:
    base = scene.config.layout.cable_base
    observations = scene.observations(0, [None] * scene.n_envs)
    for env, observation in enumerate(observations):
        row = observation.cable_rows[0]
        drift = ((row[0] - base[0]) ** 2 + (row[1] - base[1]) ** 2) ** 0.5
        if drift > LAYOUT_TOLERANCE_M:
            raise BackendError(
                ErrorCode.SCENE_LAYOUT_MISALIGNED,
                f"env {env} cable at ({row[0]:+.2f}, {row[1]:+.2f}) is {drift:.2f} m from "
                f"layout base ({base[0]:+.2f}, {base[1]:+.2f}); env offset convention mismatch",
            )


def main() -> int:
    if shutil.which(ROCM_SMI_ARGS[0]) is None:
        print("FAIL: rocm-smi not on PATH", flush=True)
        return 1
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TELEMETRY_PATH.unlink(missing_ok=True)
    config = load_task_config()
    n_envs = len(SEEDS)
    scene = stage(
        f"build wide recording scene with {n_envs} envs",
        lambda: build_batch_scene(config, n_envs, record=True, wide=True),
    )
    if scene.camera is None:
        print("FAIL: no camera on the recording scene", flush=True)
        return 1
    base = ControllerKnobs.baseline(config)

    assignments = [(seed, sample_params(seed, config, NOMINAL_SEED)) for seed in SEEDS]
    scene.reset_all([(p["cable_dx"], p["cable_dy"]) for _, p in assignments])
    assert_layout_aligned(scene)
    observations = scene.observations(0, [None] * n_envs)
    hand = scene.hand_positions().detach().cpu()
    home = (float(hand[0][0]), float(hand[0][1]), float(hand[0][2]))

    tracks: list[EnvironmentTrack] = []
    for env, (_, params) in enumerate(assignments):
        knobs = base.with_overrides({**CANDIDATE_OVERRIDES, "route_z_m": params["route_z_m"]})
        policy = EpisodePolicy(config, knobs, timestep_s=scene.timestep_s)
        tracks.append(start_track(policy, observations[env], home))

    target = OUTPUT_DIR / "candidate-v2-wideshot-16env.mp4"
    started = time.time()
    getattr(scene.camera, "start_recording")()
    chunk = config.control.chunk_steps
    arm_targets = None
    for chunks_run in range(1, MAX_CHUNKS + 1):
        if active_tracks(tracks) == 0:
            break
        if arm_targets is None or ik_is_stale(tracks):
            positions, quats = targets(tracks)
            arm_targets = scene.solve_ik(positions, quats)
        scene.command(
            arm_targets, finger_forces(tracks, config.control.open_force_n), settling_mask(tracks)
        )
        scene.step(chunk)
        if chunks_run % TELEMETRY_EVERY_CHUNKS == 0:
            sample_telemetry(chunks_run)
        observations = scene.observations(chunks_run * chunk, held_links(tracks))
        for env, track in enumerate(tracks):
            track.resume(observations[env])
    named = save_recording(scene.camera, target, config.render.fps)
    if not named and claim_video(WORKING_DIR, target, started) is None:
        print("FAIL: wide shot produced no video", flush=True)
        return 1

    for env, (seed, _) in enumerate(assignments):
        outcome = tracks[env].outcome
        result = (
            f"{outcome.reason_code} at {outcome.task_stage}"
            if outcome is not None
            else "unfinished"
        )
        print(f"  env {env:2d} seed {seed}: {result}", flush=True)
    samples = TELEMETRY_PATH.read_text(encoding="utf-8").count("=== chunk")
    print(f"  wide shot -> {target}", flush=True)
    print(f"  telemetry: {samples} rocm-smi samples -> {TELEMETRY_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
