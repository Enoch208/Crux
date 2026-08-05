from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
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
from crux.failures.taxonomy import ReasonCode, TaskStage
from crux.repair.knobs import ControllerKnobs
from crux.simulation.batchscene import build_batch_scene
from crux.simulation.episodes import sample_params
from crux.simulation.gate1 import stage
from crux.simulation.gate10_qualify import NOMINAL_SEED
from crux.simulation.gate16_qualify_v3 import V3_OVERRIDES
from crux.simulation.taskconfig import load_task_config

OUTPUT_PATH = Path("evidence-dev/seat_postmortem.jsonl")
SEEDS = tuple(range(101, 133))
MAX_CHUNKS = 900
ENDGAME_STAGES = (TaskStage.INSERT_CONNECTOR, TaskStage.VERIFY_SEATED)


@dataclass(frozen=True)
class SeatRecord:
    seed: int
    reason_code: str
    task_stage: str
    seat_lateral_m: float | None
    seat_depth_m: float | None
    notes: tuple[str, ...]


def main() -> int:
    config = load_task_config()
    thresholds = config.thresholds
    n_envs = len(SEEDS)
    scene = stage(
        f"build batched scene with {n_envs} envs", lambda: build_batch_scene(config, n_envs)
    )
    base = ControllerKnobs.baseline(config)

    assignments = [(seed, sample_params(seed, config, NOMINAL_SEED)) for seed in SEEDS]
    scene.reset_all([(p["cable_dx"], p["cable_dy"]) for _, p in assignments])
    observations = scene.observations(0, [None] * n_envs)
    hand = scene.hand_positions().detach().cpu()
    home = (float(hand[0][0]), float(hand[0][1]), float(hand[0][2]))

    tracks: list[EnvironmentTrack] = []
    for env, (_, params) in enumerate(assignments):
        knobs = base.with_overrides({**V3_OVERRIDES, "route_z_m": params["route_z_m"]})
        policy = EpisodePolicy(config, knobs, timestep_s=scene.timestep_s)
        tracks.append(start_track(policy, observations[env], home))

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
            for track in tracks:
                if track.active:
                    track.outcome = Finish(
                        ReasonCode.UNSTABLE_SIMULATION,
                        track.policy.stage,
                        tuple(track.policy.notes),
                    )
            break
        observations = scene.observations(chunks_run * chunk, held_links(tracks))
        for env, track in enumerate(tracks):
            track.resume(observations[env])
    print(f"\n{n_envs} episodes in {time.perf_counter() - started:.1f} s", flush=True)

    records: list[SeatRecord] = []
    for env, (seed, _) in enumerate(assignments):
        outcome = tracks[env].outcome
        if outcome is None:
            continue
        records.append(
            SeatRecord(
                seed=seed,
                reason_code=str(outcome.reason_code),
                task_stage=str(outcome.task_stage),
                seat_lateral_m=outcome.seat_lateral_m,
                seat_depth_m=outcome.seat_depth_m,
                notes=outcome.notes,
            )
        )
    OUTPUT_PATH.write_text(
        "".join(json.dumps(asdict(record)) + "\n" for record in records), encoding="utf-8"
    )

    endgame = [
        r
        for r in records
        if r.seat_lateral_m is not None and r.task_stage in {str(s) for s in ENDGAME_STAGES}
    ]
    print("\n=== corrected-metric endgame distribution (candidate-v3, selection seeds) ===")
    print(f"  seating tolerance: lateral < {thresholds.seat_lateral_m * 1000:.1f} mm")
    for record in sorted(endgame, key=lambda r: r.seat_lateral_m or 0.0):
        lateral_mm = (record.seat_lateral_m or 0.0) * 1000
        depth_mm = (record.seat_depth_m or 0.0) * 1000
        margin = lateral_mm - thresholds.seat_lateral_m * 1000
        print(
            f"  seed {record.seed}: lateral {lateral_mm:6.2f} mm "
            f"({margin:+6.2f} mm vs tolerance), z {depth_mm:5.2f} mm  [{record.reason_code}]"
        )

    within = [r for r in endgame if (r.seat_lateral_m or 1.0) < thresholds.seat_lateral_m]
    near = [
        r
        for r in endgame
        if thresholds.seat_lateral_m <= (r.seat_lateral_m or 1.0) < thresholds.seat_lateral_m * 1.5
    ]
    print(f"\n  reached the endgame: {len(endgame)}/{len(records)}")
    print(f"  already within tolerance: {len(within)}")
    print(f"  within 1.5x tolerance (convertible by a small alignment gain): {len(near)}")
    print(f"  records: {OUTPUT_PATH} ({len(records)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
