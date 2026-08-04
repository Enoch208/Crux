from __future__ import annotations

from pathlib import Path

from crux.failures.recorder import write_episodes
from crux.failures.records import EpisodeRecord
from crux.failures.taxonomy import TaskStage
from crux.qualification.metrics import aggregate_suite
from crux.qualification.progress import compare_stage_reached
from crux.qualification.suites import SuiteName, assert_heldout_uncontaminated
from crux.repair.knobs import ControllerKnobs
from crux.repair.operators import GRASP_AT_HEIGHT, SHORT_DANGLE_REGRASP, RepairCandidate
from crux.simulation.episodes import knobs_for, run_episode, sample_params, to_record
from crux.simulation.gate1 import stage
from crux.simulation.taskconfig import load_task_config
from crux.simulation.taskscene import build_task_scene

OUTPUT_PATH = Path("evidence-dev/repair_ablation.jsonl")
RUN_ID = "dev-ablate-1"
DEV_SEEDS = tuple(range(101, 113))
QUALIFIED_SEEDS = tuple(range(201, 221))
NOMINAL_SEED = DEV_SEEDS[0]
ENDPOINT = TaskStage.VERIFY_SEATED
CONFIDENCE = 0.95
BASELINE_ARM = "baseline-v1"
ARMS: tuple[tuple[str, tuple[RepairCandidate, ...]], ...] = (
    (BASELINE_ARM, ()),
    ("grasp-at-height", (GRASP_AT_HEIGHT,)),
    ("short-dangle-regrasp", (SHORT_DANGLE_REGRASP,)),
    ("both", (GRASP_AT_HEIGHT, SHORT_DANGLE_REGRASP)),
)


def arm_knobs(base: ControllerKnobs, candidates: tuple[RepairCandidate, ...]) -> ControllerKnobs:
    knobs = base
    for candidate in candidates:
        knobs = candidate.apply(knobs)
    return knobs


def main() -> int:
    assert_heldout_uncontaminated(QUALIFIED_SEEDS, DEV_SEEDS)
    config = load_task_config()
    scene = stage("build task scene", lambda: build_task_scene(config))
    base_knobs = ControllerKnobs.baseline(config)
    print(f"ablation: {len(ARMS)} arms x {len(DEV_SEEDS)} dev seeds", flush=True)

    by_arm: dict[str, list[EpisodeRecord]] = {name: [] for name, _ in ARMS}
    for seed in DEV_SEEDS:
        params = sample_params(seed, config, NOMINAL_SEED)
        for name, candidates in ARMS:
            knobs = arm_knobs(knobs_for(base_knobs, params), candidates)
            outcome = run_episode(scene, knobs, params)
            print(
                f"  seed {seed} {name}: {outcome.reason_code} at {outcome.task_stage} "
                f"after {outcome.steps} steps",
                flush=True,
            )
            by_arm[name].append(
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

    write_episodes(OUTPUT_PATH, [record for records in by_arm.values() for record in records])

    print("\n=== ablation on dev seeds ===")
    for name, _ in ARMS:
        metrics = aggregate_suite(by_arm[name])
        print(
            f"  {name}: success {metrics.success.successes}/{metrics.success.total}, "
            f"mean tension {metrics.mean_max_cable_tension:.1f} N"
        )
        print(f"    reason codes: {metrics.reason_code_counts}")

    print(f"\n  matched vs {BASELINE_ARM}, endpoint {ENDPOINT}:")
    for name, _ in ARMS:
        if name == BASELINE_ARM:
            continue
        depth = compare_stage_reached(by_arm[BASELINE_ARM], by_arm[name], ENDPOINT)
        interval = depth.repaired_reached.wilson_interval(CONFIDENCE)
        print(
            f"    {name}: reached {depth.repaired_reached.successes}/{depth.pairs} "
            f"[{interval.lower * 100:.1f}, {interval.upper * 100:.1f}]% vs baseline "
            f"{depth.baseline_reached.successes}/{depth.pairs}, "
            f"delta {depth.delta_percentage_points:+.1f} pp, p = {depth.mcnemar_p_value:.4f}, "
            f"progress {depth.baseline_mean_progress:.3f} -> {depth.repaired_mean_progress:.3f}"
        )

    print(f"\nepisodes written: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
