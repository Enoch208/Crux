from __future__ import annotations

import json
import sys
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
from crux.simulation.gate10_qualify import NOMINAL_SEED
from crux.simulation.gate16_qualify_v3 import V3_OVERRIDES
from crux.simulation.taskconfig import TaskConfig, load_task_config

OUTPUT_PATH = Path("evidence-dev/design_sweep.jsonl")
SEEDS = tuple(range(101, 133))
MAX_CHUNKS = 900
ENDPOINT = TaskStage.VERIFY_SEATED


@dataclass(frozen=True)
class DesignPoint:
    socket_width_m: float
    episodes: int
    successes: int
    seated: int
    reason_counts: dict[str, int]
    wall_seconds: float


def widened(config: TaskConfig, socket_width_m: float) -> TaskConfig:
    layout = config.layout.model_copy(update={"socket_width_m": socket_width_m})
    return config.model_copy(update={"layout": layout})


def reached_endpoint(outcome: Finish) -> bool:
    return STAGE_ORDER.index(outcome.task_stage) >= STAGE_ORDER.index(ENDPOINT)


def run_design_point(config: TaskConfig, socket_width_m: float) -> DesignPoint:
    n_envs = len(SEEDS)
    scene = stage(
        f"build scene at socket width {socket_width_m * 1000:.0f} mm",
        lambda: build_batch_scene(config, n_envs),
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
        tracks.append(
            start_track(
                EpisodePolicy(config, knobs, timestep_s=scene.timestep_s), observations[env], home
            )
        )

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
    elapsed = time.perf_counter() - started

    outcomes = [track.outcome for track in tracks if track.outcome is not None]
    counts: dict[str, int] = {}
    for outcome in outcomes:
        key = str(outcome.reason_code)
        counts[key] = counts.get(key, 0) + 1
    return DesignPoint(
        socket_width_m=socket_width_m,
        episodes=len(outcomes),
        successes=sum(1 for o in outcomes if o.reason_code is ReasonCode.SUCCESS),
        seated=sum(1 for o in outcomes if reached_endpoint(o)),
        reason_counts=counts,
        wall_seconds=round(elapsed, 1),
    )


def print_curve() -> None:
    if not OUTPUT_PATH.exists():
        return
    points = [json.loads(line) for line in OUTPUT_PATH.read_text().splitlines() if line]
    points.sort(key=lambda p: p["socket_width_m"])
    print("\n=== fixture tolerance curve (candidate-v3, seeds 101-132) ===")
    print("  channel width | success | reached seating | wall")
    for point in points:
        print(
            f"  {point['socket_width_m'] * 1000:9.1f} mm | "
            f"{point['successes']:3d}/{point['episodes']:<3d} | "
            f"{point['seated']:3d}/{point['episodes']:<11d} | {point['wall_seconds']:.0f} s"
        )


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: gate20_design_sweep <socket_width_m>", flush=True)
        print_curve()
        return 1
    socket_width_m = float(sys.argv[1])
    config = widened(load_task_config(), socket_width_m)
    point = run_design_point(config, socket_width_m)
    with OUTPUT_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(point)) + "\n")
    print(
        f"\n  width {socket_width_m * 1000:.1f} mm: success {point.successes}/{point.episodes}, "
        f"seated {point.seated}/{point.episodes}, {point.reason_counts}",
        flush=True,
    )
    print_curve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
