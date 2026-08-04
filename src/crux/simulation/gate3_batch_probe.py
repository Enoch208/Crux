from __future__ import annotations

import inspect
import time

import genesis as gs

from crux.simulation.cable import build_cable_urdf
from crux.simulation.gate1 import TIMESTEP_S
from crux.simulation.taskconfig import load_task_config
from crux.simulation.taskscene import TASK_URDF_PATH

BATCH_SIZES = (1, 64, 256, 1024, 4096)
MEASURED_STEPS = 300
WARMUP_STEPS = 20


def describe_build() -> None:
    print("\n=== scene.build signature ===", flush=True)
    scene = gs.Scene(sim_options=gs.options.SimOptions(dt=TIMESTEP_S), show_viewer=False)
    print(f"  {inspect.signature(scene.build)}", flush=True)
    supports = "n_envs" in inspect.signature(scene.build).parameters
    print(f"  batched envs supported: {supports}", flush=True)
    if not supports:
        raise SystemExit("this Genesis build cannot batch environments")


def measure(n_envs: int) -> tuple[float, float]:
    config = load_task_config()
    TASK_URDF_PATH.parent.mkdir(parents=True, exist_ok=True)
    TASK_URDF_PATH.write_text(build_cable_urdf(config.cable), encoding="utf-8")

    scene = gs.Scene(sim_options=gs.options.SimOptions(dt=TIMESTEP_S), show_viewer=False)
    scene.add_entity(gs.morphs.Plane())
    scene.add_entity(
        gs.morphs.URDF(
            file=str(TASK_URDF_PATH.resolve()),
            pos=config.layout.cable_base,
            euler=(0.0, 0.0, config.layout.cable_yaw_deg),
        )
    )
    scene.add_entity(gs.morphs.MJCF(file="xml/franka_emika_panda/panda.xml"))
    scene.build(n_envs=n_envs)

    for _ in range(WARMUP_STEPS):
        scene.step()
    started = time.perf_counter()
    for _ in range(MEASURED_STEPS):
        scene.step()
    elapsed = time.perf_counter() - started
    steps_per_second = MEASURED_STEPS / elapsed
    return steps_per_second, steps_per_second * n_envs


def main() -> int:
    gs.init(backend=gs.amdgpu)
    if gs.backend != gs.amdgpu:
        raise SystemExit(f"Genesis resolved to {gs.backend!r}, not gs.amdgpu")
    describe_build()

    print(f"\n=== throughput, {MEASURED_STEPS} steps after {WARMUP_STEPS} warmup ===", flush=True)
    print(f"  {'n_envs':>8} {'scene steps/s':>15} {'env-steps/s':>15}", flush=True)
    for n_envs in BATCH_SIZES:
        scene_rate, env_rate = measure(n_envs)
        print(f"  {n_envs:>8} {scene_rate:>15.1f} {env_rate:>15.1f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
