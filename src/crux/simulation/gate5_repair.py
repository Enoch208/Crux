from __future__ import annotations

from pathlib import Path

from crux.control.baseline import EpisodeOutcome
from crux.failures.recorder import write_episodes
from crux.failures.records import EpisodeRecord
from crux.repair.knobs import ControllerKnobs
from crux.repair.operators import propose
from crux.repair.search import Attempt, advances, best_of
from crux.simulation.episodes import knobs_for, run_episode, sample_params, to_record
from crux.simulation.gate1 import stage
from crux.simulation.taskconfig import load_task_config
from crux.simulation.taskscene import build_task_scene

OUTPUT_PATH = Path("evidence-dev/repair_search.jsonl")
RUN_ID = "dev-repair-3"
BASELINE_VERSION = "baseline-v1"
SEEDS = (101, 102, 103, 104, 105, 106)
MAX_ROUNDS = 4


def describe(outcome: EpisodeOutcome, tension: float) -> str:
    return (
        f"{outcome.reason_code} at {outcome.task_stage} after {outcome.steps} steps "
        f"(peak tension {tension:.1f} N)"
    )


def main() -> int:
    config = load_task_config()
    scene = stage("build task scene", lambda: build_task_scene(config))
    base_knobs = ControllerKnobs.baseline(config)

    records: list[EpisodeRecord] = []
    outcomes: dict[int, str] = {}
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
            outcomes[seed] = "baseline already succeeds"
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

        applied: list[str] = []
        current = outcome
        for round_index in range(MAX_ROUNDS):
            candidates = tuple(
                c for c in propose(current.reason_code, current.task_stage) if c.name not in applied
            )
            if not candidates:
                break
            print(
                f"--- seed {seed} round {round_index + 1}: {current.reason_code}"
                f"@{current.task_stage}, {len(candidates)} candidate(s) ---",
                flush=True,
            )
            attempts: list[Attempt] = []
            results: dict[str, tuple[EpisodeOutcome, ControllerKnobs]] = {}
            for candidate in candidates:
                print(f"  trying {candidate.name}: {candidate.rationale}", flush=True)
                repaired = candidate.apply(knobs)
                attempt_outcome = run_episode(scene, repaired, params)
                print(f"  -> {describe(attempt_outcome, scene.peak_tension_n)}")
                records.append(
                    to_record(
                        attempt_outcome,
                        scene,
                        seed,
                        params,
                        RUN_ID,
                        f"{RUN_ID}-{seed}-r{round_index + 1}-{candidate.name}",
                        f"repair:{'+'.join([*applied, candidate.name])}",
                        secondary_tags=(
                            f"targets={current.reason_code}@{current.task_stage}",
                            *(f"{k}={v}" for k, v in candidate.overrides),
                        ),
                    )
                )
                attempts.append(
                    Attempt(
                        candidate_name=candidate.name,
                        reason_code=attempt_outcome.reason_code,
                        task_stage=attempt_outcome.task_stage,
                        steps=attempt_outcome.steps,
                    )
                )
                results[candidate.name] = (attempt_outcome, repaired)
                if not attempt_outcome.reason_code.is_failure:
                    break

            best = best_of(tuple(attempts))
            if best is None or not advances(best, current.task_stage):
                print(f"  no candidate advanced past {current.task_stage}", flush=True)
                break
            current, knobs = results[best.candidate_name]
            applied.append(best.candidate_name)
            print(
                f"  accepted {best.candidate_name}: now {current.reason_code}@{current.task_stage}",
                flush=True,
            )
            if not current.reason_code.is_failure:
                break

        chain = "+".join(applied) if applied else "none"
        if not current.reason_code.is_failure:
            outcomes[seed] = f"REPAIRED by {chain}"
        elif applied:
            outcomes[seed] = (
                f"advanced to {current.reason_code}@{current.task_stage} by {chain} "
                f"(from {outcome.reason_code}@{outcome.task_stage})"
            )
        else:
            outcomes[seed] = f"unrepaired {outcome.reason_code}@{outcome.task_stage}"

    write_episodes(OUTPUT_PATH, records)
    print("\n=== repair search summary ===")
    if reproduction is not None:
        seed, matched = reproduction
        print(f"failure reproduction (seed {seed}): {'MATCH' if matched else 'DIVERGED'}")
    for seed, summary in outcomes.items():
        print(f"  seed {seed}: {summary}")
    print(f"episodes written: {OUTPUT_PATH} ({len(records)} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
