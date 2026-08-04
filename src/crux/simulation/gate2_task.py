from __future__ import annotations

from pathlib import Path

from crux.failures.recorder import write_episodes
from crux.failures.records import EpisodeRecord
from crux.repair.knobs import ControllerKnobs
from crux.simulation.episodes import knobs_for, run_episode, sample_params, to_record
from crux.simulation.gate1 import stage
from crux.simulation.taskconfig import load_task_config
from crux.simulation.taskscene import build_task_scene

OUTPUT_PATH = Path("evidence-dev/baseline_episodes.jsonl")
RUN_ID = "dev-baseline-1"
CONTROLLER_VERSION = "baseline-v1"
SEEDS = (101, 102, 103, 104, 105, 106)


def main() -> int:
    config = load_task_config()
    scene = stage("build task scene", lambda: build_task_scene(config))
    base_knobs = ControllerKnobs.baseline(config)

    records: list[EpisodeRecord] = []
    tally: dict[str, int] = {}
    for seed in SEEDS:
        params = sample_params(seed, config, SEEDS[0])
        shown = {key: round(value, 4) for key, value in params.items()}
        print(f"\n=== episode seed {seed} {shown} ===", flush=True)
        outcome = run_episode(scene, knobs_for(base_knobs, params), params)
        tally[str(outcome.reason_code)] = tally.get(str(outcome.reason_code), 0) + 1
        print(
            f"  -> {outcome.reason_code} at {outcome.task_stage} after {outcome.steps} steps "
            f"(peak tension {scene.peak_tension_n:.1f} N)"
        )
        records.append(
            to_record(
                outcome,
                scene,
                seed,
                params,
                RUN_ID,
                f"{RUN_ID}-{seed}",
                CONTROLLER_VERSION,
            )
        )

    write_episodes(OUTPUT_PATH, records)
    print(f"\nreason codes: {tally}")
    print(f"raw episodes: {OUTPUT_PATH} ({len(records)} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
