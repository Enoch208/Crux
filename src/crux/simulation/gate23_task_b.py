from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

import genesis as gs

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
from crux.control.directives import Finish
from crux.control.policy import EpisodePolicy
from crux.failures.recorder import write_episodes
from crux.failures.records import EpisodeMetrics, EpisodeRecord
from crux.failures.taxonomy import ReasonCode, TaskStage
from crux.qualification.compare import mcnemar_exact_p_value
from crux.qualification.metrics import aggregate_suite
from crux.qualification.progress import compare_stage_reached
from crux.qualification.suites import SuiteName
from crux.repair.knobs import ControllerKnobs
from crux.simulation.batchscene import build_batch_scene
from crux.simulation.episodes import sample_params
from crux.simulation.gate1 import stage
from crux.simulation.gate10_qualify import BASELINE_OVERRIDES, NOMINAL_SEED
from crux.simulation.gate21_qualify_v4 import V4_OVERRIDES
from crux.simulation.taskconfig import load_task_config

CONFIG_PATH = Path("configs/task_b.yaml")
OUTPUT_PATH = Path("evidence-dev/qualification_task_b.jsonl")
RUN_ID = "dev-qualify-task-b"
SEEDS = tuple(range(601, 633))
MAX_CHUNKS = 900
ENDPOINT = TaskStage.VERIFY_SEATED
CONFIDENCE = 0.95
ARMS: tuple[tuple[str, dict[str, float]], ...] = (
    ("baseline-v1", BASELINE_OVERRIDES),
    ("candidate-v4", V4_OVERRIDES),
)


def main() -> int:
    config = load_task_config(CONFIG_PATH)
    n_envs = len(ARMS) * len(SEEDS)
    scene = stage(
        f"build task-B scene with {n_envs} envs", lambda: build_batch_scene(config, n_envs)
    )
    base = ControllerKnobs.baseline(config)

    assignments: list[tuple[str, int, ControllerKnobs, dict[str, float]]] = []
    for version, overrides in ARMS:
        for seed in SEEDS:
            params = sample_params(seed, config, NOMINAL_SEED)
            knobs = base.with_overrides({**overrides, "route_z_m": params["route_z_m"]})
            assignments.append((version, seed, knobs, params))

    scene.reset_all([(p["cable_dx"], p["cable_dy"]) for _, _, _, p in assignments])
    observations = scene.observations(0, [None] * n_envs)
    hand = scene.hand_positions().detach().cpu()
    home = (float(hand[0][0]), float(hand[0][1]), float(hand[0][2]))

    tracks: list[EnvironmentTrack] = [
        start_track(
            EpisodePolicy(config, knobs, timestep_s=scene.timestep_s), observations[env], home
        )
        for env, (_, _, knobs, _) in enumerate(assignments)
    ]
    finished_at = [0] * n_envs
    chunk = config.control.chunk_steps

    started = time.perf_counter()
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
        try:
            scene.step(chunk)
        except gs.GenesisException as error:
            print(f"\nsolver exploded at chunk {chunks_run}: {error}", flush=True)
            for env, track in enumerate(tracks):
                if track.active:
                    track.outcome = Finish(
                        ReasonCode.UNSTABLE_SIMULATION,
                        track.policy.stage,
                        tuple(track.policy.notes),
                    )
                    finished_at[env] = chunks_run * chunk
            break
        observations = scene.observations(chunks_run * chunk, held_links(tracks))
        for env, track in enumerate(tracks):
            if track.resume(observations[env]):
                finished_at[env] = chunks_run * chunk
    print(f"\n{n_envs} episodes in {time.perf_counter() - started:.1f} s", flush=True)

    records: list[EpisodeRecord] = []
    for env, (version, seed, _knobs, params) in enumerate(assignments):
        outcome = tracks[env].outcome
        if outcome is None:
            continue
        records.append(
            EpisodeRecord(
                run_id=RUN_ID,
                episode_id=f"{RUN_ID}-{seed}-{version}",
                seed=seed,
                controller_version=version,
                suite=SuiteName.HELDOUT,
                reason_code=outcome.reason_code,
                task_stage=outcome.task_stage,
                simulation_step=finished_at[env],
                timestamp=datetime.now(UTC),
                environment_parameters={k: float(v) for k, v in params.items()},
                metrics=EpisodeMetrics(
                    completion_steps=finished_at[env],
                    completion_seconds=finished_at[env] * scene.timestep_s,
                    max_cable_tension=tracks[env].policy.max_cable_tension_n,
                    max_collision_impulse=tracks[env].policy.max_arm_contact_n,
                ),
            )
        )
    write_episodes(OUTPUT_PATH, records)
    by_version = {v: [r for r in records if r.controller_version == v] for v, _ in ARMS}

    print("\n=== TASK B — a task this harness has never been tuned for ===")
    print(f"  config: {CONFIG_PATH} (tighter gates, longer floppier cable, wider randomization)")
    for version, _ in ARMS:
        arm = by_version[version]
        if not arm:
            continue
        metrics = aggregate_suite(arm)
        interval = metrics.success.wilson_interval(CONFIDENCE)
        print(
            f"  {version}: success {metrics.success.successes}/{metrics.success.total} "
            f"[{interval.lower * 100:.1f}, {interval.upper * 100:.1f}]%  "
            f"{metrics.reason_code_counts}"
        )

    base_arm, cand_arm = by_version["baseline-v1"], by_version["candidate-v4"]
    if base_arm and cand_arm:
        left = {r.seed: r.reason_code is ReasonCode.SUCCESS for r in base_arm}
        right = {r.seed: r.reason_code is ReasonCode.SUCCESS for r in cand_arm}
        pairs = sorted(set(left) & set(right))
        left_only = sum(1 for s in pairs if left[s] and not right[s])
        right_only = sum(1 for s in pairs if right[s] and not left[s])
        delta = (sum(right.values()) - sum(left.values())) / len(pairs) * 100
        print(
            f"\n  task success: {sum(left.values())}/{len(pairs)} vs "
            f"{sum(right.values())}/{len(pairs)}, "
            f"{delta:+.1f} pp, discordant {left_only}/{right_only}, "
            f"exact McNemar p = {mcnemar_exact_p_value(left_only, right_only):.4f}"
        )
        depth = compare_stage_reached(base_arm, cand_arm, ENDPOINT)
        print(
            f"  reached {ENDPOINT}: {depth.baseline_reached.successes}/{depth.pairs} vs "
            f"{depth.repaired_reached.successes}/{depth.pairs}, "
            f"{depth.delta_percentage_points:+.1f} pp, p = {depth.mcnemar_p_value:.4f}"
        )
    print(f"\nepisodes written: {OUTPUT_PATH} ({len(records)} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
