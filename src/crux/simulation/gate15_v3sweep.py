from __future__ import annotations

import json
import shutil
import subprocess
import threading
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
from crux.failures.taxonomy import STAGE_ORDER, ReasonCode, TaskStage
from crux.repair.knobs import ControllerKnobs
from crux.simulation.batchscene import build_batch_scene
from crux.simulation.episodes import sample_params
from crux.simulation.gate1 import stage
from crux.simulation.gate10_qualify import CANDIDATE_OVERRIDES, NOMINAL_SEED
from crux.simulation.taskconfig import load_task_config

OUTPUT_PATH = Path("evidence-dev/v3_selection_sweep_r3.jsonl")
TELEMETRY_PATH = Path("evidence-dev/telemetry_sweep_r3.log")
SEEDS = tuple(range(101, 133))
MAX_CHUNKS = 900
ENDPOINT = TaskStage.VERIFY_SEATED
TELEMETRY_PERIOD_S = 5.0
ROCM_SMI_ARGS = ("rocm-smi", "--showuse", "--showmemuse", "--showpower", "--showtemp")
ARMS: tuple[tuple[str, dict[str, float]], ...] = (
    ("v3", {"grasp_attempts": 3}),
    ("v3-nudge", {"grasp_attempts": 3, "nudge_seat": 1}),
    ("v3-nudge-mouth", {"grasp_attempts": 3, "nudge_seat": 1, "mouth_entry_m": 0.020}),
    ("v3-mouth", {"grasp_attempts": 3, "mouth_entry_m": 0.020}),
)


@dataclass(frozen=True)
class SweepRecord:
    arm: str
    seed: int
    reason_code: str
    task_stage: str
    notes: tuple[str, ...]


def telemetry_loop(stop: threading.Event) -> None:
    while not stop.is_set():
        result = subprocess.run(ROCM_SMI_ARGS, capture_output=True, text=True, check=False)
        with TELEMETRY_PATH.open("a", encoding="utf-8") as log:
            log.write(f"=== wall {time.strftime('%H:%M:%S')} ===\n")
            log.write(result.stdout)
        stop.wait(TELEMETRY_PERIOD_S)


def reached_endpoint(outcome: Finish) -> bool:
    return STAGE_ORDER.index(outcome.task_stage) >= STAGE_ORDER.index(ENDPOINT)


def main() -> int:
    if shutil.which(ROCM_SMI_ARGS[0]) is None:
        print("FAIL: rocm-smi not on PATH", flush=True)
        return 1
    TELEMETRY_PATH.unlink(missing_ok=True)
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
            {**CANDIDATE_OVERRIDES, **arm_by_name[arm_name], "route_z_m": params["route_z_m"]}
        )
        policy = EpisodePolicy(config, knobs, timestep_s=scene.timestep_s)
        tracks.append(start_track(policy, observations[env], home))

    stop = threading.Event()
    sampler = threading.Thread(target=telemetry_loop, args=(stop,), daemon=True)
    sampler.start()
    chunk = config.control.chunk_steps
    started = time.perf_counter()
    arm_targets = None
    try:
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
    finally:
        stop.set()
        sampler.join(timeout=TELEMETRY_PERIOD_S + 2.0)
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

    print("\n=== selection sweep: candidate-v3 arms vs v2 control (matched seeds) ===")
    for arm_name, _ in ARMS:
        arm_records = [r for r in records if r.arm == arm_name]
        outcomes = {
            env: tracks[env].outcome
            for env, (name, _, _) in enumerate(assignments)
            if name == arm_name
        }
        finished = [o for o in outcomes.values() if o is not None]
        seated = sum(1 for o in finished if reached_endpoint(o))
        succeeded = sum(1 for o in finished if o.reason_code is ReasonCode.SUCCESS)
        regrip_misses = sum(
            1
            for o in finished
            if o.reason_code is ReasonCode.MISSED_GRASP
            and o.task_stage in (TaskStage.VERIFY_CLIP_1, TaskStage.VERIFY_CLIP_2)
        )
        retries_used = sum(
            1 for r in arm_records for note in r.notes if "reopening for attempt" in note
        )
        print(
            f"  {arm_name:14s} success {succeeded}/{len(finished)}, "
            f"seated {seated}/{len(finished)}, regrip misses {regrip_misses}, "
            f"retries fired {retries_used}"
        )
    samples = TELEMETRY_PATH.read_text(encoding="utf-8").count("=== wall")
    print(f"\n  records: {OUTPUT_PATH} ({len(records)})")
    print(f"  telemetry: {samples} samples under live load -> {TELEMETRY_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
