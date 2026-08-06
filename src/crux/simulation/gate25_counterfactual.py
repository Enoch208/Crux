from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from crux.control.batch_driver import (
    finger_forces,
    held_links,
    ik_is_stale,
    settling_mask,
    start_track,
    targets,
)
from crux.control.policy import EpisodePolicy
from crux.failures.taxonomy import TaskStage
from crux.repair.counterfactual import SearchOutcome, best, fan, improvement
from crux.repair.knobs import ControllerKnobs
from crux.simulation.batchscene import BatchTaskScene, build_batch_scene
from crux.simulation.episodes import sample_params
from crux.simulation.gate1 import stage
from crux.simulation.gate10_qualify import NOMINAL_SEED
from crux.simulation.gate21_qualify_v4 import V4_OVERRIDES
from crux.simulation.taskconfig import TaskConfig, load_task_config

OUTPUT_PATH = Path("evidence-dev/counterfactual_search.jsonl")
SEEDS = (501, 503, 507, 509, 511, 513, 515, 517)
CANDIDATES = 32
SEARCH_RADIUS_M = 0.008
SEARCH_RINGS = 2
SETTLE_CHUNKS = 14
MAX_CHUNKS = 900


@dataclass(frozen=True)
class SeedResult:
    seed: int
    nominal_seated: bool
    chosen_seated: bool
    chosen_offset_mm: tuple[float, float]
    seated_candidates: int
    candidates: int
    search_seconds: float


def run_seed(
    scene: BatchTaskScene,
    config: TaskConfig,
    knobs: ControllerKnobs,
    params: dict[str, float],
    seed: int,
) -> SeedResult | None:
    """Drive one episode to the seating decision, then search physical futures."""
    candidates = fan(CANDIDATES, SEARCH_RADIUS_M, SEARCH_RINGS)
    scene.reset_all([(params["cable_dx"], params["cable_dy"])] * scene.n_envs)
    observations = scene.observations(0, [None] * scene.n_envs)
    hand = scene.hand_positions().detach().cpu()
    home = (float(hand[0][0]), float(hand[0][1]), float(hand[0][2]))
    track = start_track(
        EpisodePolicy(config, knobs, timestep_s=scene.timestep_s), observations[0], home
    )
    tracks = [track]
    chunk = config.control.chunk_steps

    arm_targets = None
    for chunks_run in range(1, MAX_CHUNKS + 1):
        if not track.active or track.policy.stage is TaskStage.INSERT_CONNECTOR:
            break
        if arm_targets is None or ik_is_stale(tracks):
            positions, quats = targets(tracks)
            arm_targets = scene.solve_ik(positions * scene.n_envs, quats * scene.n_envs)
        scene.command(
            arm_targets,
            finger_forces(tracks, config.control.open_force_n) * scene.n_envs,
            settling_mask(tracks) * scene.n_envs,
        )
        scene.step(chunk)
        observations = scene.observations(chunks_run * chunk, held_links(tracks) * scene.n_envs)
        track.resume(observations[0])
    if track.policy.stage is not TaskStage.INSERT_CONNECTOR:
        print(f"  seed {seed}: never reached the insertion decision, skipped", flush=True)
        return None

    state = scene.capture(0)
    started = time.perf_counter()
    scene.restore_everywhere(state)
    observations = scene.observations(0, [None] * scene.n_envs)
    policy = track.policy
    tip = policy.tip_of(observations[0])
    positions = [
        [tip[0] + candidate.offset_x_m, tip[1] + candidate.offset_y_m, knobs.insert_z_m]
        for candidate in candidates
    ]
    quats = [list(policy.tool_quat)] * len(candidates)
    arm_targets = scene.solve_ik(positions, quats)
    for _ in range(SETTLE_CHUNKS):
        scene.command(arm_targets, [knobs.close_force_n] * scene.n_envs, [False] * scene.n_envs)
        scene.step(chunk)
    observations = scene.observations(0, [None] * scene.n_envs)
    elapsed = time.perf_counter() - started

    outcomes: list[SearchOutcome] = []
    for index, candidate in enumerate(candidates):
        seated, lateral, depth = policy.seat_metrics(observations[index])
        outcomes.append(
            SearchOutcome(candidate=candidate, seated=seated, lateral_m=lateral, depth_m=depth)
        )
    nominal_seated, chosen_seated = improvement(outcomes)
    winner = best(outcomes)
    seated_count = sum(1 for outcome in outcomes if outcome.seated)
    print(
        f"  seed {seed}: nominal {'SEATS' if nominal_seated else 'misses'} -> "
        f"search picks {winner.candidate.label} {'SEATS' if chosen_seated else 'misses'} "
        f"({seated_count}/{len(candidates)} futures seat, {elapsed:.1f} s)",
        flush=True,
    )
    return SeedResult(
        seed=seed,
        nominal_seated=nominal_seated,
        chosen_seated=chosen_seated,
        chosen_offset_mm=(
            round(winner.candidate.offset_x_m * 1000, 2),
            round(winner.candidate.offset_y_m * 1000, 2),
        ),
        seated_candidates=seated_count,
        candidates=len(candidates),
        search_seconds=round(elapsed, 2),
    )


def main() -> int:
    config = load_task_config()
    scene = stage(
        f"build scene with {CANDIDATES} envs for parallel futures",
        lambda: build_batch_scene(config, CANDIDATES),
    )
    base = ControllerKnobs.baseline(config)
    print(
        f"\n=== counterfactual search: {CANDIDATES} physical futures per decision, "
        f"radius {SEARCH_RADIUS_M * 1000:.0f} mm ===",
        flush=True,
    )
    results: list[SeedResult] = []
    for seed in SEEDS:
        params = sample_params(seed, config, NOMINAL_SEED)
        knobs = base.with_overrides({**V4_OVERRIDES, "route_z_m": params["route_z_m"]})
        result = run_seed(scene, config, knobs, params, seed)
        if result is not None:
            results.append(result)

    OUTPUT_PATH.write_text(
        "".join(json.dumps(asdict(result)) + "\n" for result in results), encoding="utf-8"
    )
    if results:
        nominal = sum(1 for r in results if r.nominal_seated)
        chosen = sum(1 for r in results if r.chosen_seated)
        rescued = sum(1 for r in results if r.chosen_seated and not r.nominal_seated)
        print(
            f"\n  decisions searched: {len(results)}  ·  nominal action seats "
            f"{nominal}/{len(results)}  ·  searched action seats {chosen}/{len(results)}"
        )
        print(f"  futures that rescued a failing decision: {rescued}")
        print(f"  mean search time: {sum(r.search_seconds for r in results) / len(results):.1f} s")
    print(f"\nrecords: {OUTPUT_PATH} ({len(results)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
