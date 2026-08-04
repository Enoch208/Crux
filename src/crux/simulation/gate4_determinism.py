from __future__ import annotations

from crux.repair.knobs import ControllerKnobs
from crux.simulation.determinism import (
    TrialSignature,
    max_deviation,
    outcomes_agree,
    signatures_agree,
    step_spread,
)
from crux.simulation.episodes import knobs_for, run_episode, sample_params
from crux.simulation.gate1 import Rows, stage
from crux.simulation.taskconfig import load_task_config
from crux.simulation.taskscene import TaskScene, build_task_scene

SEED = 101
TRIALS = 3
FREE_RUN_STEPS = 1000


def deviations(samples: list[Rows]) -> list[float]:
    return [max_deviation(samples[0], other) for other in samples[1:]]


def report(label: str, values: list[float]) -> None:
    formatted = ", ".join(f"{value:.3e}" for value in values)
    verdict = "BIT-EXACT" if all(value == 0.0 for value in values) else "DIVERGES"
    print(f"  {label}: max deviation vs trial 1 [{formatted}] m -> {verdict}", flush=True)


def probe_reset(scene: TaskScene, offset: tuple[float, float]) -> list[Rows]:
    samples: list[Rows] = []
    for _ in range(TRIALS):
        scene.reset(offset)
        samples.append(scene.cable_rows())
    return samples


def probe_free_run(scene: TaskScene, offset: tuple[float, float]) -> list[Rows]:
    samples: list[Rows] = []
    for _ in range(TRIALS):
        scene.reset(offset)
        scene.arm.run(FREE_RUN_STEPS)
        samples.append(scene.cable_rows())
    return samples


def main() -> int:
    config = load_task_config()
    scene = stage("build task scene", lambda: build_task_scene(config))
    params = sample_params(SEED, config, SEED)
    knobs = knobs_for(ControllerKnobs.baseline(config), params)
    offset = (params["cable_dx"], params["cable_dy"])

    print(f"\n=== determinism probe, seed {SEED}, {TRIALS} trials ===", flush=True)

    print("\n[1] reset only", flush=True)
    report("reset", deviations(probe_reset(scene, offset)))

    print(f"\n[2] reset + {FREE_RUN_STEPS} free physics steps", flush=True)
    report("free-run", deviations(probe_free_run(scene, offset)))

    print("\n[3] full controlled episode", flush=True)
    signatures: list[TrialSignature] = []
    finals: list[Rows] = []
    for trial in range(TRIALS):
        outcome = run_episode(scene, knobs, params)
        signatures.append(
            TrialSignature(
                reason_code=outcome.reason_code,
                task_stage=outcome.task_stage,
                steps=outcome.steps,
            )
        )
        finals.append(scene.cable_rows())
        print(
            f"  trial {trial + 1}: {outcome.reason_code} at {outcome.task_stage} "
            f"after {outcome.steps} steps",
            flush=True,
        )
    report("episode-final-state", deviations(finals))

    trials = tuple(signatures)
    print("\n=== verdict ===")
    print(f"  reset is bit-exact: {all(v == 0.0 for v in deviations(probe_reset(scene, offset)))}")
    print(f"  identical failure and stage across trials: {outcomes_agree(trials)}")
    print(f"  identical step counts across trials: {signatures_agree(trials)}")
    print(f"  step spread: {step_spread(trials)} steps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
