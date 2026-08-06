from __future__ import annotations

import json
import time
from collections import Counter
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
from crux.repair.candidates import V4_OVERRIDES
from crux.repair.knobs import ControllerKnobs
from crux.simulation.batchscene import build_batch_scene
from crux.simulation.episodes import sample_params
from crux.simulation.gate1 import stage
from crux.simulation.gate10_qualify import NOMINAL_SEED
from crux.simulation.taskconfig import load_task_config

OUTPUT_PATH = Path("evidence-dev/endgame_sweep.jsonl")
SEEDS = tuple(range(101, 133))
MAX_CHUNKS = 1100
ENDGAME_STAGES = (TaskStage.ALIGN_CONNECTOR, TaskStage.INSERT_CONNECTOR)
RECOVERY_OVERRIDES: dict[str, float] = {"slip_recover_attempts": 2}
ROUTE_GUARD_OVERRIDES: dict[str, float] = {
    "slip_guard": 1,
    "slip_guard_endgame": 0,
    "slip_warn_ratio": 0.45,
    "slip_debounce_chunks": 2,
    "slip_grip_boost": 1.8,
}
ARMS: tuple[tuple[str, dict[str, float]], ...] = (
    ("v4-control", {}),
    ("v4-recover", RECOVERY_OVERRIDES),
    ("v4-routeguard", ROUTE_GUARD_OVERRIDES),
    ("v4-both", {**RECOVERY_OVERRIDES, **ROUTE_GUARD_OVERRIDES}),
)


@dataclass(frozen=True)
class SweepRecord:
    arm: str
    seed: int
    reason_code: str
    task_stage: str
    notes: tuple[str, ...]


def summarise(arm_name: str, records: list[SweepRecord]) -> None:
    succeeded = sum(1 for r in records if r.reason_code == str(ReasonCode.SUCCESS))
    slips = Counter(r.task_stage for r in records if r.reason_code == str(ReasonCode.CABLE_SLIP))
    endgame_slips = sum(slips[str(stage_)] for stage_ in ENDGAME_STAGES)
    route_slips = sum(slips.values()) - endgame_slips
    recoveries = sum(1 for r in records for note in r.notes if "recovery attempt 1" in note)
    rescued = sum(
        1
        for r in records
        if r.reason_code == str(ReasonCode.SUCCESS)
        and any("recovery attempt" in note for note in r.notes)
    )
    reasons = Counter(r.reason_code for r in records)
    print(
        f"  {arm_name}: success {succeeded}/{len(records)}  ·  "
        f"slips route {route_slips} / endgame {endgame_slips}  ·  "
        f"recoveries fired {recoveries}, episodes rescued {rescued}"
    )
    print(f"    reason codes: {dict(sorted(reasons.items()))}")


def main() -> int:
    config = load_task_config()
    n_envs = len(ARMS) * len(SEEDS)
    scene = stage(
        f"build batched scene with {n_envs} envs", lambda: build_batch_scene(config, n_envs)
    )
    base = ControllerKnobs.baseline(config)

    assignments: list[tuple[str, int, dict[str, float]]] = []
    for arm_name, _ in ARMS:
        for seed in SEEDS:
            params = sample_params(seed, config, NOMINAL_SEED)
            assignments.append((arm_name, seed, params))

    scene.reset_all([(p["cable_dx"], p["cable_dy"]) for _, _, p in assignments])
    observations = scene.observations(0, [None] * n_envs)
    hand = scene.hand_positions().detach().cpu()
    home = (float(hand[0][0]), float(hand[0][1]), float(hand[0][2]))

    arm_by_name = dict(ARMS)
    tracks: list[EnvironmentTrack] = []
    for env, (arm_name, _, params) in enumerate(assignments):
        knobs = base.with_overrides(
            {**V4_OVERRIDES, **arm_by_name[arm_name], "route_z_m": params["route_z_m"]}
        )
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
            arm_targets,
            finger_forces(tracks, config.control.open_force_n),
            settling_mask(tracks),
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
    elapsed = time.perf_counter() - started
    print(f"\n{n_envs} episodes in {elapsed:.1f} s", flush=True)

    records: list[SweepRecord] = []
    for env, (arm_name, seed, _) in enumerate(assignments):
        outcome = tracks[env].outcome
        if outcome is None:
            continue
        records.append(
            SweepRecord(
                arm=arm_name,
                seed=seed,
                reason_code=str(outcome.reason_code),
                task_stage=str(outcome.task_stage),
                notes=outcome.notes,
            )
        )
    OUTPUT_PATH.write_text(
        "".join(json.dumps(asdict(record)) + "\n" for record in records), encoding="utf-8"
    )

    print("\n=== endgame sweep: scoped slip repairs vs v4 control (matched seeds 101-132) ===")
    for arm_name, _ in ARMS:
        summarise(arm_name, [r for r in records if r.arm == arm_name])

    control = {r.seed: r for r in records if r.arm == "v4-control"}
    print("\n  per-arm discordant seeds vs control:")
    for arm_name, _ in ARMS[1:]:
        gained = sorted(
            r.seed
            for r in records
            if r.arm == arm_name
            and r.reason_code == str(ReasonCode.SUCCESS)
            and control[r.seed].reason_code != str(ReasonCode.SUCCESS)
        )
        lost = sorted(
            r.seed
            for r in records
            if r.arm == arm_name
            and r.reason_code != str(ReasonCode.SUCCESS)
            and control[r.seed].reason_code == str(ReasonCode.SUCCESS)
        )
        print(f"    {arm_name}: gained {gained} · lost {lost}")
    print(f"\nrecords: {OUTPUT_PATH} ({len(records)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
