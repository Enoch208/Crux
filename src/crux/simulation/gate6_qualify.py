from __future__ import annotations

from pathlib import Path

from crux.failures.recorder import write_episodes
from crux.failures.records import EpisodeRecord
from crux.failures.taxonomy import TaskStage
from crux.qualification.compare import compare_matched
from crux.qualification.metrics import aggregate_suite
from crux.qualification.progress import compare_stage_reached
from crux.qualification.suites import SuiteName, assert_heldout_uncontaminated
from crux.repair.knobs import ControllerKnobs
from crux.repair.operators import GRASP_AT_HEIGHT, SHORT_DANGLE_REGRASP
from crux.simulation.episodes import knobs_for, run_episode, sample_params, to_record
from crux.simulation.gate1 import stage
from crux.simulation.taskconfig import load_task_config
from crux.simulation.taskscene import build_task_scene

OUTPUT_PATH = Path("evidence-dev/qualification_heldout.jsonl")
RUN_ID = "dev-qualify-1"
BASELINE_VERSION = "baseline-v1"
REPAIRED_VERSION = "repaired-v1"
REPAIR_SELECTION_SEEDS = (101, 102, 103, 104, 105, 106)
HELDOUT_SEEDS = tuple(range(201, 221))
NOMINAL_SEED = REPAIR_SELECTION_SEEDS[0]
ENDPOINT = TaskStage.VERIFY_SEATED
CONFIDENCE = 0.95
REPAIR_CHAIN = (GRASP_AT_HEIGHT, SHORT_DANGLE_REGRASP)


def repaired_knobs(base: ControllerKnobs) -> ControllerKnobs:
    knobs = base
    for candidate in REPAIR_CHAIN:
        knobs = candidate.apply(knobs)
    return knobs


def main() -> int:
    assert_heldout_uncontaminated(HELDOUT_SEEDS, REPAIR_SELECTION_SEEDS)
    config = load_task_config()
    scene = stage("build task scene", lambda: build_task_scene(config))
    base_knobs = ControllerKnobs.baseline(config)
    chain = "+".join(candidate.name for candidate in REPAIR_CHAIN)
    print(f"held-out suite: {len(HELDOUT_SEEDS)} seeds, repaired controller = {chain}", flush=True)

    baseline_records: list[EpisodeRecord] = []
    repaired_records: list[EpisodeRecord] = []

    for seed in HELDOUT_SEEDS:
        params = sample_params(seed, config, NOMINAL_SEED)
        arms = (
            (BASELINE_VERSION, knobs_for(base_knobs, params), baseline_records),
            (REPAIRED_VERSION, repaired_knobs(knobs_for(base_knobs, params)), repaired_records),
        )
        for version, knobs, sink in arms:
            outcome = run_episode(scene, knobs, params)
            print(
                f"  seed {seed} {version}: {outcome.reason_code} at {outcome.task_stage} "
                f"after {outcome.steps} steps",
                flush=True,
            )
            sink.append(
                to_record(
                    outcome,
                    scene,
                    seed,
                    params,
                    RUN_ID,
                    f"{RUN_ID}-{seed}-{version}",
                    version,
                    suite=SuiteName.HELDOUT,
                )
            )

    write_episodes(OUTPUT_PATH, [*baseline_records, *repaired_records])

    print("\n=== held-out qualification ===")
    for records in (baseline_records, repaired_records):
        metrics = aggregate_suite(records)
        interval = metrics.success.wilson_interval(CONFIDENCE)
        print(
            f"  {metrics.controller_version}: success "
            f"{metrics.success.successes}/{metrics.success.total} "
            f"({metrics.success.percentage:.1f}%), Wilson {CONFIDENCE:.0%} CI "
            f"[{interval.lower * 100:.1f}, {interval.upper * 100:.1f}]%, "
            f"mean tension {metrics.mean_max_cable_tension:.1f} N"
        )
        print(f"    reason codes: {metrics.reason_code_counts}")

    success = compare_matched(baseline_records, repaired_records)
    print(
        f"\n  matched success: baseline {success.baseline_success.successes}/{success.pairs}, "
        f"repaired {success.repaired_success.successes}/{success.pairs}, "
        f"delta {success.delta_percentage_points:+.1f} pp, "
        f"McNemar p = {success.mcnemar_p_value:.4f}"
    )

    depth = compare_stage_reached(baseline_records, repaired_records, ENDPOINT)
    baseline_ci = depth.baseline_reached.wilson_interval(CONFIDENCE)
    repaired_ci = depth.repaired_reached.wilson_interval(CONFIDENCE)
    print(
        f"  reached {ENDPOINT}: baseline {depth.baseline_reached.successes}/{depth.pairs} "
        f"[{baseline_ci.lower * 100:.1f}, {baseline_ci.upper * 100:.1f}]%, "
        f"repaired {depth.repaired_reached.successes}/{depth.pairs} "
        f"[{repaired_ci.lower * 100:.1f}, {repaired_ci.upper * 100:.1f}]%, "
        f"delta {depth.delta_percentage_points:+.1f} pp, "
        f"McNemar p = {depth.mcnemar_p_value:.4f}"
    )
    print(
        f"  discordant pairs: repaired-only {depth.repaired_only}, "
        f"baseline-only {depth.baseline_only}"
    )
    print(
        f"  mean stage progress: baseline {depth.baseline_mean_progress:.3f}, "
        f"repaired {depth.repaired_mean_progress:.3f}"
    )
    print(f"\nepisodes written: {OUTPUT_PATH} ({len(baseline_records) + len(repaired_records)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
