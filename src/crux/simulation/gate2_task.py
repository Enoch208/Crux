from __future__ import annotations

import random
from datetime import UTC, datetime
from pathlib import Path

from crux.control.baseline import BaselineController
from crux.failures.recorder import write_episodes
from crux.failures.records import EpisodeMetrics, EpisodeRecord
from crux.qualification.suites import SuiteName
from crux.simulation.gate1 import stage
from crux.simulation.taskconfig import TaskConfig, load_task_config
from crux.simulation.taskscene import build_task_scene

OUTPUT_PATH = Path("evidence-dev/baseline_episodes.jsonl")
RUN_ID = "dev-baseline-1"
CONTROLLER_VERSION = "baseline-v0"
SEEDS = (101, 102, 103, 104, 105, 106)


def sample_params(seed: int, config: TaskConfig) -> dict[str, float]:
    nominal = {
        "cable_dx": 0.0,
        "cable_dy": 0.0,
        "close_force_n": config.control.close_force_n,
        "route_z_m": config.control.route_z_m,
    }
    if seed == SEEDS[0]:
        return nominal
    rng = random.Random(seed)
    ranges = config.randomization
    return {
        "cable_dx": rng.uniform(-ranges.cable_dx_m, ranges.cable_dx_m),
        "cable_dy": rng.uniform(-ranges.cable_dy_m, ranges.cable_dy_m),
        "close_force_n": config.control.close_force_n
        + rng.uniform(-ranges.close_force_jitter_n, ranges.close_force_jitter_n),
        "route_z_m": config.control.route_z_m
        + rng.uniform(-ranges.route_z_jitter_m, ranges.route_z_jitter_m),
    }


def main() -> int:
    config = load_task_config()
    scene = stage("build task scene", lambda: build_task_scene(config))

    records: list[EpisodeRecord] = []
    tally: dict[str, int] = {}
    for seed in SEEDS:
        params = sample_params(seed, config)
        shown = {key: round(value, 4) for key, value in params.items()}
        print(f"\n=== episode seed {seed} {shown} ===", flush=True)
        scene.reset((params["cable_dx"], params["cable_dy"]))
        controller = BaselineController(
            scene=scene,
            close_force_n=params["close_force_n"],
            route_z_m=params["route_z_m"],
        )
        outcome = controller.run_episode()
        tally[str(outcome.reason_code)] = tally.get(str(outcome.reason_code), 0) + 1
        print(
            f"  -> {outcome.reason_code} at {outcome.task_stage} after {outcome.steps} steps "
            f"(peak tension {scene.peak_tension_n:.1f} N)"
        )
        records.append(
            EpisodeRecord(
                run_id=RUN_ID,
                episode_id=f"{RUN_ID}-{seed}",
                seed=seed,
                controller_version=CONTROLLER_VERSION,
                suite=SuiteName.PRIMARY,
                reason_code=outcome.reason_code,
                task_stage=outcome.task_stage,
                simulation_step=outcome.steps,
                timestamp=datetime.now(UTC),
                environment_parameters={k: float(v) for k, v in params.items()},
                metrics=EpisodeMetrics(
                    completion_steps=outcome.steps,
                    completion_seconds=outcome.steps * scene.timestep_s,
                    max_cable_tension=scene.peak_tension_n,
                    max_collision_impulse=scene.peak_arm_contact_n,
                ),
            )
        )

    write_episodes(OUTPUT_PATH, records)
    print(f"\nreason codes: {tally}")
    print(f"raw episodes: {OUTPUT_PATH} ({len(records)} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
