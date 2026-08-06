from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import genesis as gs

from crux.control.batch_driver import (
    EnvironmentTrack,
    active_tracks,
    finger_forces,
    held_links,
    ik_is_stale,
    settling_mask,
    start_track,
    targets,
)
from crux.control.directives import Directive, Finish, Observation
from crux.control.policy import EpisodePolicy, Plan
from crux.failures.taxonomy import ReasonCode, TaskStage
from crux.learning.trace import TraceStep, chunk_features, encode_action, write_trace
from crux.repair.candidates import V4_OVERRIDES
from crux.repair.knobs import ControllerKnobs
from crux.simulation.batchscene import build_batch_scene
from crux.simulation.episodes import sample_params
from crux.simulation.gate1 import stage
from crux.simulation.gate10_qualify import NOMINAL_SEED
from crux.simulation.taskconfig import load_task_config

OUTPUT_PATH = Path("evidence-dev/bc_traces.jsonl")
SEEDS = tuple(range(101, 133)) + tuple(range(301, 333)) + tuple(range(401, 433))
MAX_CHUNKS = 900


@dataclass(slots=True)
class TracingPolicy:
    """Wraps the scripted expert and logs (observation, directive) pairs it produces.

    The wrapper is invisible to the driver: it satisfies the same policy protocol and
    forwards every attribute the harness reads, so the traced episodes are ordinary
    candidate-v4 episodes in every respect.
    """

    inner: EpisodePolicy
    seed: int
    steps: list[TraceStep] = field(default_factory=list, init=False)
    last_yaw: float = field(default=0.0, init=False)

    @property
    def stage(self) -> TaskStage:
        return self.inner.stage

    @property
    def notes(self) -> list[str]:
        return self.inner.notes

    @property
    def held_link(self) -> int | None:
        return self.inner.held_link

    @property
    def max_cable_tension_n(self) -> float:
        return self.inner.max_cable_tension_n

    @property
    def max_arm_contact_n(self) -> float:
        return self.inner.max_arm_contact_n

    def record(self, observation: Observation, directive: Directive) -> None:
        if isinstance(directive, Finish):
            return
        action, self.last_yaw = encode_action(observation, directive, self.last_yaw)
        self.steps.append(
            TraceStep(seed=self.seed, features=chunk_features(observation), action=action)
        )

    def run(self, observation: Observation) -> Plan:
        plan = self.inner.run(observation)
        directive = next(plan)
        self.record(observation, directive)
        while not isinstance(directive, Finish):
            observation = yield directive
            directive = plan.send(observation)
            self.record(observation, directive)
        yield directive


def main() -> int:
    config = load_task_config()
    n_envs = len(SEEDS)
    scene = stage(
        f"build batched scene with {n_envs} envs", lambda: build_batch_scene(config, n_envs)
    )
    base = ControllerKnobs.baseline(config)

    assignments: list[tuple[int, ControllerKnobs, dict[str, float]]] = []
    for seed in SEEDS:
        params = sample_params(seed, config, NOMINAL_SEED)
        knobs = base.with_overrides({**V4_OVERRIDES, "route_z_m": params["route_z_m"]})
        assignments.append((seed, knobs, params))

    scene.reset_all([(p["cable_dx"], p["cable_dy"]) for _, _, p in assignments])
    observations = scene.observations(0, [None] * n_envs)
    hand = scene.hand_positions().detach().cpu()
    home = (float(hand[0][0]), float(hand[0][1]), float(hand[0][2]))

    tracers: list[TracingPolicy] = []
    tracks: list[EnvironmentTrack] = []
    for env, (seed, knobs, _) in enumerate(assignments):
        tracer = TracingPolicy(
            inner=EpisodePolicy(config, knobs, timestep_s=scene.timestep_s), seed=seed
        )
        tracers.append(tracer)
        tracks.append(start_track(tracer, observations[env], home))

    chunk = config.control.chunk_steps
    started = time.perf_counter()
    arm_targets = None
    for chunks_run in range(1, MAX_CHUNKS + 1):
        if active_tracks(tracks) == 0:
            break
        if arm_targets is None or ik_is_stale(tracks):
            positions, quats = targets(tracks)
            arm_targets = scene.solve_ik(positions, quats)
        scene.command(
            arm_targets, finger_forces(tracks, config.control.open_force_n), settling_mask(tracks)
        )
        try:
            scene.step(chunk)
        except gs.GenesisException as error:
            print(f"\nsolver exploded at chunk {chunks_run}: {error}", flush=True)
            break
        observations = scene.observations(chunks_run * chunk, held_links(tracks))
        for env, track in enumerate(tracks):
            track.resume(observations[env])
    elapsed = time.perf_counter() - started
    print(f"\n{n_envs} episodes in {elapsed:.1f} s", flush=True)

    OUTPUT_PATH.unlink(missing_ok=True)
    kept = 0
    kept_steps = 0
    for env, tracer in enumerate(tracers):
        outcome = tracks[env].outcome
        if outcome is None or outcome.reason_code is not ReasonCode.SUCCESS:
            continue
        write_trace(OUTPUT_PATH, tracer.steps)
        kept += 1
        kept_steps += len(tracer.steps)

    print("\n=== expert trace collection: candidate-v4 on selection seeds ===")
    print(f"  episodes run: {n_envs}  ·  successes kept: {kept}  ·  trace steps: {kept_steps}")
    print(f"  traces: {OUTPUT_PATH}")
    if kept == 0:
        print("  FAIL: no successful episodes to learn from")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
