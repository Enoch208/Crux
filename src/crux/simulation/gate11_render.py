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
from crux.control.directives import Finish
from crux.control.policy import EpisodePolicy
from crux.failures.taxonomy import STAGE_ORDER, TaskStage
from crux.repair.knobs import ControllerKnobs
from crux.simulation.batchscene import BatchTaskScene, build_batch_scene
from crux.simulation.episodes import sample_params
from crux.simulation.gate1 import stage
from crux.simulation.gate10_qualify import CANDIDATE_OVERRIDES, NOMINAL_SEED
from crux.simulation.recording import claim_video, save_recording
from crux.simulation.taskconfig import TaskConfig, load_task_config

OUTPUT_DIR = Path("evidence-dev/render")
WORKING_DIR = Path()
BASELINE_ARM = "baseline-v1"
CANDIDATE_ARM = "candidate-v2"
BASELINE_SEEDS = (301, 313)
SEATING_SEEDS = (301, 303, 304, 305, 306, 311, 312, 313, 316, 319, 325, 327)
SEATING_RENDERS_WANTED = 2
ENDPOINT = TaskStage.VERIFY_SEATED
MAX_CHUNKS = 900


def next_target(arm_name: str, seed: int) -> Path:
    base = OUTPUT_DIR / f"{arm_name}-scene2-seed{seed}.mp4"
    if not base.exists():
        return base
    attempt = 2
    while (OUTPUT_DIR / f"{arm_name}-scene2-seed{seed}-r{attempt}.mp4").exists():
        attempt += 1
    return OUTPUT_DIR / f"{arm_name}-scene2-seed{seed}-r{attempt}.mp4"


def reached_endpoint(outcome: Finish | None) -> bool:
    if outcome is None:
        return False
    return STAGE_ORDER.index(outcome.task_stage) >= STAGE_ORDER.index(ENDPOINT)


def describe(outcome: Finish | None) -> str:
    if outcome is None:
        return "unfinished"
    return f"{outcome.reason_code} at {outcome.task_stage}"


def render_episode(
    scene: BatchTaskScene,
    config: TaskConfig,
    knobs: ControllerKnobs,
    params: dict[str, float],
    target: Path,
) -> Finish | None:
    scene.reset_all([(params["cable_dx"], params["cable_dy"])])
    observations = scene.observations(0, [None])
    hand = scene.hand_positions().detach().cpu()
    home = (float(hand[0][0]), float(hand[0][1]), float(hand[0][2]))
    track = start_track(
        EpisodePolicy(config, knobs, timestep_s=scene.timestep_s), observations[0], home
    )
    tracks = [track]
    chunk = config.control.chunk_steps

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
            arm_targets, finger_forces(tracks, config.control.open_force_n), settling_mask(tracks)
        )
        scene.step(chunk)
        observations = scene.observations(chunks_run * chunk, held_links(tracks))
        track.resume(observations[0])
    named = save_recording(scene.camera, target, config.render.fps)
    if not named and claim_video(WORKING_DIR, target, started) is None:
        raise RuntimeError(f"no video produced for {target}")
    return track.outcome


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config = load_task_config()
    scene = stage("build recording scene", lambda: build_batch_scene(config, 1, record=True))
    if scene.camera is None:
        print("FAIL: no camera on the recording scene", flush=True)
        return 1
    base = ControllerKnobs.baseline(config)

    for seed in BASELINE_SEEDS:
        existing = OUTPUT_DIR / f"{BASELINE_ARM}-scene2-seed{seed}.mp4"
        if existing.exists():
            print(f"  {BASELINE_ARM} seed {seed}: kept existing {existing}", flush=True)
            continue
        params = sample_params(seed, config, NOMINAL_SEED)
        knobs = base.with_overrides({"timeout_steps": 20000, "route_z_m": params["route_z_m"]})
        outcome = render_episode(scene, config, knobs, params, existing)
        print(f"  {BASELINE_ARM} seed {seed}: {describe(outcome)} -> {existing}", flush=True)

    seated = 0
    attempts = 0
    for seed in SEATING_SEEDS:
        if seated >= SEATING_RENDERS_WANTED:
            break
        params = sample_params(seed, config, NOMINAL_SEED)
        knobs = base.with_overrides({**CANDIDATE_OVERRIDES, "route_z_m": params["route_z_m"]})
        target = next_target(CANDIDATE_ARM, seed)
        outcome = render_episode(scene, config, knobs, params, target)
        attempts += 1
        if reached_endpoint(outcome):
            seated += 1
        print(f"  {CANDIDATE_ARM} seed {seed}: {describe(outcome)} -> {target}", flush=True)
    print(
        f"  {CANDIDATE_ARM} renders reaching {ENDPOINT}: {seated}/{attempts}, all clips kept",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
