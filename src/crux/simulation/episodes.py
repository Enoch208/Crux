from __future__ import annotations

import random
from datetime import UTC, datetime

from crux.control.baseline import BaselineController, EpisodeOutcome
from crux.failures.records import EpisodeMetrics, EpisodeRecord
from crux.qualification.suites import SuiteName
from crux.repair.knobs import ControllerKnobs
from crux.simulation.taskconfig import TaskConfig
from crux.simulation.taskscene import TaskScene


def sample_params(seed: int, config: TaskConfig, nominal_seed: int) -> dict[str, float]:
    if seed == nominal_seed:
        return {
            "cable_dx": 0.0,
            "cable_dy": 0.0,
            "close_force_n": config.control.close_force_n,
            "route_z_m": config.control.route_z_m,
        }
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


def knobs_for(base: ControllerKnobs, params: dict[str, float]) -> ControllerKnobs:
    return base.with_overrides(
        {"close_force_n": params["close_force_n"], "route_z_m": params["route_z_m"]}
    )


def run_episode(
    scene: TaskScene,
    knobs: ControllerKnobs,
    params: dict[str, float],
) -> EpisodeOutcome:
    scene.reset((params["cable_dx"], params["cable_dy"]))
    return BaselineController(scene=scene, knobs=knobs).run_episode()


def to_record(
    outcome: EpisodeOutcome,
    scene: TaskScene,
    seed: int,
    params: dict[str, float],
    run_id: str,
    episode_id: str,
    controller_version: str,
    suite: SuiteName = SuiteName.PRIMARY,
    secondary_tags: tuple[str, ...] = (),
) -> EpisodeRecord:
    return EpisodeRecord(
        run_id=run_id,
        episode_id=episode_id,
        seed=seed,
        controller_version=controller_version,
        suite=suite,
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
        secondary_tags=secondary_tags,
    )
