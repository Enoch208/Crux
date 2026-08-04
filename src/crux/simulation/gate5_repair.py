from __future__ import annotations

from pathlib import Path

from crux.control.baseline import EpisodeOutcome
from crux.failures.recorder import write_episodes
from crux.failures.records import EpisodeRecord
from crux.repair.knobs import ControllerKnobs
from crux.repair.operators import RepairCandidate, propose
from crux.simulation.episodes import knobs_for, run_episode, sample_params, to_record
from crux.simulation.gate1 import stage
from crux.simulation.taskconfig import load_task_config
from crux.simulation.taskscene import build_task_scene

OUTPUT_PATH = Path("evidence-dev/repair_search.jsonl")
RUN_ID = "dev-repair-1"
BASELINE_VERSION = "baseline-v1"
SEEDS = (101, 102, 103, 104, 105, 106)


def describe(outcome: EpisodeOutcome, scene_tension: float) -> str:
    return (
        f"{outcome.reason_code} at {outcome.task_stage} after {outcome.steps} steps "
        f"(peak tension {scene_tension:.1f} N)"
    )


def main() -> int:
    config = load_task_config()
    scene = stage("build task scene", lambda: build_task_scene(config))
    base_knobs = ControllerKnobs.baseline(config)

    records: list[EpisodeRecord] = []
    fixed: dict[int, str] = {}
    unfixed: dict[int, str] = {}
    reproduction: tuple[int, bool] | None = None

    for seed in SEEDS:
        params = sample_params(seed, config, SEEDS[0])
        knobs = knobs_for(base_knobs, params)
        print(f"\n=== seed {seed} baseline ===", flush=True)
        outcome = run_episode(scene, knobs, params)
        print(f"  -> {describe(outcome, scene.peak_tension_n)}")
        records.append(
            to_record(
                outcome, scene, seed, params, RUN_ID, f"{RUN_ID}-{seed}-baseline", BASELINE_VERSION
            )
        )
        if not outcome.reason_code.is_failure:
            continue

        if reproduction is None:
            print(f"--- seed {seed} reproduction check ---", flush=True)
            again = run_episode(scene, knobs, params)
            matched = (again.reason_code, again.task_stage) == (
                outcome.reason_code,
                outcome.task_stage,
            )
            print(f"  -> {describe(again, scene.peak_tension_n)} | reproduced: {matched}")
            reproduction = (seed, matched)
            records.append(
                to_record(
                    again,
                    scene,
                    seed,
                    params,
                    RUN_ID,
                    f"{RUN_ID}-{seed}-replay",
                    BASELINE_VERSION,
                    secondary_tags=("reproduction-check", f"matched={matched}"),
                )
            )

        candidates: tuple[RepairCandidate, ...] = propose(outcome.reason_code, outcome.task_stage)
        print(f"--- seed {seed}: {len(candidates)} candidate repair(s) ---", flush=True)
        for candidate in candidates:
            print(f"  trying {candidate.name}: {candidate.rationale}", flush=True)
            repaired = candidate.apply(knobs)
            attempt = run_episode(scene, repaired, params)
            print(f"  -> {describe(attempt, scene.peak_tension_n)}")
            records.append(
                to_record(
                    attempt,
                    scene,
                    seed,
                    params,
                    RUN_ID,
                    f"{RUN_ID}-{seed}-{candidate.name}",
                    f"repair:{candidate.name}",
                    secondary_tags=(
                        f"targets={outcome.reason_code}@{outcome.task_stage}",
                        *(f"{k}={v}" for k, v in candidate.overrides),
                    ),
                )
            )
            if not attempt.reason_code.is_failure:
                fixed[seed] = candidate.name
                break
        if seed not in fixed:
            unfixed[seed] = f"{outcome.reason_code}@{outcome.task_stage}"

    write_episodes(OUTPUT_PATH, records)
    print("\n=== repair search summary ===")
    if reproduction is not None:
        seed, matched = reproduction
        print(f"failure reproduction (seed {seed}): {'MATCH' if matched else 'DIVERGED'}")
    print(f"repaired seeds: {fixed or 'none'}")
    print(f"unrepaired seeds: {unfixed or 'none'}")
    print(f"episodes written: {OUTPUT_PATH} ({len(records)} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
