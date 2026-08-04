from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

from crux.control.batch_driver import (
    EnvironmentTrack,
    active_tracks,
    finger_forces,
    held_links,
    ik_is_stale,
    start_track,
    targets,
)
from crux.control.policy import EpisodePolicy
from crux.failures.recorder import write_episodes
from crux.failures.records import EpisodeMetrics, EpisodeRecord
from crux.qualification.suites import SuiteName
from crux.repair.knobs import ControllerKnobs
from crux.simulation.batchscene import BatchTaskScene, build_batch_scene
from crux.simulation.episodes import knobs_for, sample_params
from crux.simulation.gate1 import stage
from crux.simulation.taskconfig import load_task_config

OUTPUT_PATH = Path("evidence-dev/batch_episodes.jsonl")
RUN_ID = "dev-batch-1"
CONTROLLER = "baseline-v1"
N_ENVS = 16
NOMINAL_SEED = 101
MAX_CHUNKS = 800


def home_pose(scene: BatchTaskScene) -> tuple[float, float, float]:
    hand = scene.hand_positions().detach().cpu()
    return (float(hand[0][0]), float(hand[0][1]), float(hand[0][2]))


def main() -> int:
    config = load_task_config()
    seeds = tuple(range(NOMINAL_SEED, NOMINAL_SEED + N_ENVS))
    scene = stage(
        f"build batched scene with {N_ENVS} envs", lambda: build_batch_scene(config, N_ENVS)
    )
    base_knobs = ControllerKnobs.baseline(config)

    params = [sample_params(seed, config, NOMINAL_SEED) for seed in seeds]
    scene.reset_all([(p["cable_dx"], p["cable_dy"]) for p in params])

    chunk = config.control.chunk_steps
    observations = scene.observations(0, [None] * N_ENVS)
    home = home_pose(scene)
    tracks: list[EnvironmentTrack] = [
        start_track(
            EpisodePolicy(config, knobs_for(base_knobs, params[env])), observations[env], home
        )
        for env in range(N_ENVS)
    ]
    finished_at: list[int] = [0] * N_ENVS

    started = time.perf_counter()
    arm_targets = None
    chunks_run = 0
    for chunks_run in range(1, MAX_CHUNKS + 1):
        if active_tracks(tracks) == 0:
            break
        if arm_targets is None or ik_is_stale(tracks):
            positions, quats = targets(tracks)
            arm_targets = scene.solve_ik(positions, quats)
        scene.command(arm_targets, finger_forces(tracks, config.control.open_force_n))
        scene.step(chunk)
        observations = scene.observations(chunks_run * chunk, held_links(tracks))
        for env, track in enumerate(tracks):
            if not track.active:
                continue
            track.resume(observations[env])
            if not track.active:
                finished_at[env] = chunks_run * chunk
    elapsed = time.perf_counter() - started

    steps = chunks_run * chunk
    print(
        f"\n{N_ENVS} episodes in {elapsed:.1f} s: {steps} scene steps, "
        f"{steps / elapsed:.1f} scene steps/s, {steps * N_ENVS / elapsed:.1f} env-steps/s",
        flush=True,
    )

    records: list[EpisodeRecord] = []
    tally: dict[str, int] = {}
    for env, track in enumerate(tracks):
        outcome = track.outcome
        if outcome is None:
            print(f"  seed {seeds[env]}: unfinished after {MAX_CHUNKS} chunks", flush=True)
            continue
        tally[str(outcome.reason_code)] = tally.get(str(outcome.reason_code), 0) + 1
        print(
            f"  seed {seeds[env]}: {outcome.reason_code} at {outcome.task_stage} "
            f"after {finished_at[env]} steps",
            flush=True,
        )
        records.append(
            EpisodeRecord(
                run_id=RUN_ID,
                episode_id=f"{RUN_ID}-{seeds[env]}",
                seed=seeds[env],
                controller_version=CONTROLLER,
                suite=SuiteName.STANDARD,
                reason_code=outcome.reason_code,
                task_stage=outcome.task_stage,
                simulation_step=finished_at[env],
                timestamp=datetime.now(UTC),
                environment_parameters={k: float(v) for k, v in params[env].items()},
                metrics=EpisodeMetrics(
                    completion_steps=finished_at[env],
                    completion_seconds=finished_at[env] * scene.timestep_s,
                    max_cable_tension=0.0,
                    max_collision_impulse=0.0,
                ),
            )
        )

    write_episodes(OUTPUT_PATH, records)
    print(f"\nreason codes: {tally}")
    print(f"episodes written: {OUTPUT_PATH} ({len(records)} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
