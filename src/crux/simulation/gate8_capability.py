from __future__ import annotations

from pathlib import Path

from crux.failures.recorder import write_episodes
from crux.failures.records import EpisodeRecord
from crux.failures.taxonomy import TaskStage, stage_index
from crux.qualification.suites import SuiteName
from crux.repair.knobs import ControllerKnobs
from crux.repair.operators import (
    GRASP_AT_HEIGHT,
    MORE_BUDGET,
    SLIDE_INSERT,
    TIP_HOLD,
    RepairCandidate,
)
from crux.simulation.episodes import knobs_for, run_episode, sample_params, to_record
from crux.simulation.gate1 import stage
from crux.simulation.taskconfig import load_task_config
from crux.simulation.taskscene import build_task_scene

OUTPUT_PATH = Path("evidence-dev/capability_sprint.jsonl")
RUN_ID = "dev-capability-1"
DEV_SEEDS = (101, 103, 105, 107, 109, 111)
NOMINAL_SEED = 101
ARMS: tuple[tuple[str, tuple[RepairCandidate, ...]], ...] = (
    ("baseline-v1", ()),
    ("slide-insert", (SLIDE_INSERT,)),
    ("slide-insert+grasp-at-height", (SLIDE_INSERT, GRASP_AT_HEIGHT)),
    ("slide-insert+grasp-at-height+more-budget", (SLIDE_INSERT, GRASP_AT_HEIGHT, MORE_BUDGET)),
    ("tip-hold+grasp-at-height", (TIP_HOLD, GRASP_AT_HEIGHT)),
)


def arm_knobs(base: ControllerKnobs, candidates: tuple[RepairCandidate, ...]) -> ControllerKnobs:
    knobs = base
    for candidate in candidates:
        knobs = candidate.apply(knobs)
    return knobs


def main() -> int:
    config = load_task_config()
    scene = stage("build task scene", lambda: build_task_scene(config))
    base_knobs = ControllerKnobs.baseline(config)
    print(f"capability sprint: {len(ARMS)} arms x {len(DEV_SEEDS)} seeds", flush=True)

    records: list[EpisodeRecord] = []
    successes: dict[str, int] = {name: 0 for name, _ in ARMS}
    seated: dict[str, int] = {name: 0 for name, _ in ARMS}
    best_lateral: dict[str, float] = {}

    for seed in DEV_SEEDS:
        params = sample_params(seed, config, NOMINAL_SEED)
        for name, candidates in ARMS:
            knobs = arm_knobs(knobs_for(base_knobs, params), candidates)
            outcome = run_episode(scene, knobs, params)
            if not outcome.reason_code.is_failure:
                successes[name] += 1
            if stage_index(outcome.task_stage) >= stage_index(TaskStage.VERIFY_SEATED):
                seated[name] += 1
            if outcome.seat_lateral_m is not None:
                previous = best_lateral.get(name)
                if previous is None or outcome.seat_lateral_m < previous:
                    best_lateral[name] = outcome.seat_lateral_m
            seat = ""
            if outcome.seat_lateral_m is not None and outcome.seat_depth_m is not None:
                seat = (
                    f", seat lateral {outcome.seat_lateral_m * 1000:.1f} mm "
                    f"tip z {outcome.seat_depth_m * 1000:.1f} mm"
                )
            print(
                f"  seed {seed} {name}: {outcome.reason_code} at {outcome.task_stage} "
                f"after {outcome.steps} steps{seat}",
                flush=True,
            )
            records.append(
                to_record(
                    outcome,
                    scene,
                    seed,
                    params,
                    RUN_ID,
                    f"{RUN_ID}-{seed}-{name}",
                    name,
                    suite=SuiteName.STANDARD,
                )
            )

    write_episodes(OUTPUT_PATH, records)
    print("\n=== capability sprint ===")
    total = len(DEV_SEEDS)
    for name, _ in ARMS:
        closest = best_lateral.get(name)
        lateral = f"{closest * 1000:.1f} mm" if closest is not None else "never seated"
        print(
            f"  {name}: SUCCESS {successes[name]}/{total}, reached seating {seated[name]}/{total}, "
            f"closest lateral {lateral}"
        )
    print(f"\nepisodes written: {OUTPUT_PATH} ({len(records)} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
