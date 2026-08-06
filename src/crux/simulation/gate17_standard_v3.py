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
from crux.qualification.metrics import aggregate_suite
from crux.qualification.progress import compare_stage_reached
from crux.qualification.suites import SuiteName
from crux.repair.knobs import ControllerKnobs
from crux.simulation.batchscene import build_batch_scene
from crux.simulation.episodes import sample_params
from crux.simulation.gate1 import stage
from crux.simulation.gate10_qualify import BASELINE_OVERRIDES, NOMINAL_SEED
from crux.simulation.gate16_qualify_v3 import V3_OVERRIDES
from crux.simulation.taskconfig import load_task_config

OUTPUT_PATH = Path("evidence-dev/qualification_v3_standard_fixedmetric.jsonl")
SPEC_PATH = Path("evidence-dev/candidate_v3.json")
RUN_ID = "dev-qualify-4-standard"
SUITE_SEEDS = tuple(range(101, 133))
MAX_CHUNKS = 900
ENDPOINT = TaskStage.VERIFY_SEATED
CONFIDENCE = 0.95
ARMS: tuple[tuple[str, dict[str, float]], ...] = (
    ("baseline-v1", BASELINE_OVERRIDES),
    ("candidate-v3", V3_OVERRIDES),
)


def main() -> int:
    config = load_task_config()
    n_envs = len(ARMS) * len(SUITE_SEEDS)
    scene = stage(
        f"build batched scene with {n_envs} envs", lambda: build_batch_scene(config, n_envs)
    )
    base = ControllerKnobs.baseline(config)

    assignments: list[tuple[str, int, ControllerKnobs, dict[str, float]]] = []
    for version, overrides in ARMS:
        for seed in SUITE_SEEDS:
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
    chunks_run = 0
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
    elapsed = time.perf_counter() - started
    print(
        f"\n{n_envs} episodes in {elapsed:.1f} s "
        f"({chunks_run * chunk * n_envs / elapsed:.0f} env-steps/s)",
        flush=True,
    )

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
                suite=SuiteName.STANDARD,
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
    by_version = {
        version: [r for r in records if r.controller_version == version] for version, _ in ARMS
    }

    base_spec = base.with_overrides(dict(V3_OVERRIDES))
    SPEC_PATH.write_text(base_spec.model_dump_json(indent=2), encoding="utf-8")
    print(f"controller spec written: {SPEC_PATH}", flush=True)
    print("\n=== standard-suite qualification for v3 (selection-era seeds 101-132) ===")
    for version, _ in ARMS:
        arm = by_version[version]
        if not arm:
            continue
        metrics = aggregate_suite(arm)
        interval = metrics.success.wilson_interval(CONFIDENCE)
        print(
            f"  {version}: success {metrics.success.successes}/{metrics.success.total}, "
            f"Wilson [{interval.lower * 100:.1f}, {interval.upper * 100:.1f}]%"
        )
        print(f"    reason codes: {metrics.reason_code_counts}")

    for left, right in (("baseline-v1", "candidate-v3"),):
        if not by_version[left] or not by_version[right]:
            continue
        depth = compare_stage_reached(by_version[left], by_version[right], ENDPOINT)
        print(
            f"\n  {left} vs {right}, reached {ENDPOINT}: "
            f"{depth.baseline_reached.successes}/{depth.pairs} vs "
            f"{depth.repaired_reached.successes}/{depth.pairs}, "
            f"delta {depth.delta_percentage_points:+.1f} pp, "
            f"McNemar p = {depth.mcnemar_p_value:.4f}"
        )
    print(f"\nepisodes written: {OUTPUT_PATH} ({len(records)} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
