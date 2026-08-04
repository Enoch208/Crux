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
from crux.failures.taxonomy import ReasonCode, TaskStage, stage_index
from crux.qualification.suites import SuiteName
from crux.repair.knobs import ControllerKnobs
from crux.simulation.batchscene import build_batch_scene
from crux.simulation.episodes import sample_params
from crux.simulation.gate1 import stage
from crux.simulation.taskconfig import load_task_config

OUTPUT_PATH = Path("evidence-dev/knob_sweep.jsonl")
RUN_ID = "dev-sweep-7"
SEEDS = (101, 103, 105, 107)
NOMINAL_SEED = 101
MAX_CHUNKS = 800
BASE = {"drag_speed_mps": 0.30, "insert_carry_z_m": 0.035, "grasp_at_link_height": 1}
PRECISE = {"align_step_cap_m": 0.008, "align_corrections": 6}
WITHDRAW = {"withdraw_sideways_m": 0.06}
DEEP = {"insert_z_m": 0.006}
TIP = {"insert_link_from_end": 0}
SWEEP: tuple[tuple[str, dict[str, float]], ...] = (
    ("tip", {**BASE, **TIP}),
    ("tip+precise", {**BASE, **TIP, **PRECISE}),
    ("tip+deep", {**BASE, **TIP, **DEEP}),
    ("tip+precise+deep", {**BASE, **TIP, **PRECISE, **DEEP}),
    ("dangle", {**BASE}),
    ("dangle+precise", {**BASE, **PRECISE}),
    ("dangle1+precise", {**BASE, "insert_link_from_end": 1, **PRECISE}),
    ("tip+precise+slow", {**BASE, **TIP, **PRECISE, "drag_speed_mps": 0.15}),
)
BUDGET = {"timeout_steps": 20000}


def main() -> int:
    config = load_task_config()
    n_envs = len(SWEEP) * len(SEEDS)
    scene = stage(
        f"build batched scene with {n_envs} envs", lambda: build_batch_scene(config, n_envs)
    )
    base = ControllerKnobs.baseline(config)

    assignments: list[tuple[str, int, ControllerKnobs, dict[str, float]]] = []
    for arm_name, overrides in SWEEP:
        for seed in SEEDS:
            params = sample_params(seed, config, NOMINAL_SEED)
            knobs = base.with_overrides(
                {
                    **BUDGET,
                    "route_z_m": params["route_z_m"],
                    **overrides,
                }
            )
            assignments.append((arm_name, seed, knobs, params))

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

    watch = 0
    last_stage = tracks[watch].policy.stage
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
        spy = tracks[watch]
        if spy.active:
            if spy.policy.stage is not last_stage:
                print(f"  [env0 chunk {chunks_run}] stage -> {spy.policy.stage}", flush=True)
                last_stage = spy.policy.stage
            held = spy.held_link
            if held is not None:
                obs = observations[watch]
                link = obs.cable_rows[held]
                tip = (
                    obs.hand_pos[0],
                    obs.hand_pos[1],
                    obs.hand_pos[2] - config.control.hand_to_tip_m,
                )
                drift = sum((a - b) ** 2 for a, b in zip(link, tip, strict=True)) ** 0.5
                if drift > 0.015:
                    print(
                        f"  [env0 chunk {chunks_run}] {spy.policy.stage} slip {drift * 1000:.0f} mm"
                        f" link ({link[0]:+.3f},{link[1]:+.3f},{link[2]:+.3f})"
                        f" tip ({tip[0]:+.3f},{tip[1]:+.3f},{tip[2]:+.3f})"
                        f" gap {obs.pinch_gap_m * 1000:.1f} mm",
                        flush=True,
                    )
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
    by_arm: dict[str, list[Finish]] = {name: [] for name, _ in SWEEP}
    for env, (arm_name, seed, _knobs, params) in enumerate(assignments):
        outcome = tracks[env].outcome
        if outcome is None:
            continue
        by_arm[arm_name].append(outcome)
        records.append(
            EpisodeRecord(
                run_id=RUN_ID,
                episode_id=f"{RUN_ID}-{arm_name}-{seed}",
                seed=seed,
                controller_version=f"sweep:{arm_name}",
                suite=SuiteName.STANDARD,
                reason_code=outcome.reason_code,
                task_stage=outcome.task_stage,
                simulation_step=finished_at[env],
                timestamp=datetime.now(UTC),
                environment_parameters={k: float(v) for k, v in params.items()},
                metrics=EpisodeMetrics(
                    completion_steps=finished_at[env],
                    completion_seconds=finished_at[env] * scene.timestep_s,
                    max_cable_tension=0.0,
                    max_collision_impulse=0.0,
                ),
            )
        )

    print("\n=== seating post-mortems ===")
    for arm_name, outcomes in by_arm.items():
        for o in outcomes:
            if o.reason_code in (ReasonCode.CONNECTOR_MISALIGNED, ReasonCode.INCOMPLETE_INSERTION):
                story = [n for n in o.notes if "connector offset" in n]
                for line in story:
                    print(f"  [{arm_name}] {line}")
                break

    print("\n=== sweep results ===")
    for arm_name, outcomes in by_arm.items():
        if not outcomes:
            continue
        successes = sum(1 for o in outcomes if not o.reason_code.is_failure)
        deepest = max(outcomes, key=lambda o: stage_index(o.task_stage))
        seated = sum(
            1 for o in outcomes if stage_index(o.task_stage) >= stage_index(TaskStage.VERIFY_SEATED)
        )
        codes: dict[str, int] = {}
        for o in outcomes:
            codes[str(o.reason_code)] = codes.get(str(o.reason_code), 0) + 1
        seats = ", ".join(
            f"({o.seat_lateral_m * 1000:.0f},{o.seat_depth_m * 1000:.0f})"
            for o in outcomes
            if o.seat_lateral_m is not None and o.seat_depth_m is not None
        )
        print(
            f"  {arm_name}: SUCCESS {successes}/{len(outcomes)}, seated {seated}, "
            f"deepest {deepest.task_stage}, codes {codes}, seat(lat,z)mm [{seats}]"
        )

    write_episodes(OUTPUT_PATH, records)
    print(f"\nepisodes written: {OUTPUT_PATH} ({len(records)} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
