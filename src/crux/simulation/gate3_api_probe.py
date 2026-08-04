from __future__ import annotations

import inspect

import genesis as gs

from crux.simulation.cable import build_cable_urdf
from crux.simulation.gate1 import TIMESTEP_S
from crux.simulation.taskconfig import load_task_config
from crux.simulation.taskscene import TASK_URDF_PATH

N_ENVS = 4
FRANKA_MJCF = "xml/franka_emika_panda/panda.xml"


def shape_of(value: object) -> str:
    shape = getattr(value, "shape", None)
    return str(tuple(shape)) if shape is not None else f"{type(value).__name__} (no shape)"


def report(label: str, value: object) -> None:
    print(f"  {label}: {shape_of(value)}", flush=True)


def main() -> int:
    config = load_task_config()
    TASK_URDF_PATH.parent.mkdir(parents=True, exist_ok=True)
    TASK_URDF_PATH.write_text(build_cable_urdf(config.cable), encoding="utf-8")

    gs.init(backend=gs.amdgpu)
    scene = gs.Scene(sim_options=gs.options.SimOptions(dt=TIMESTEP_S), show_viewer=False)
    scene.add_entity(gs.morphs.Plane())
    cable = scene.add_entity(
        gs.morphs.URDF(
            file=str(TASK_URDF_PATH.resolve()),
            pos=config.layout.cable_base,
            euler=(0.0, 0.0, config.layout.cable_yaw_deg),
        )
    )
    franka = scene.add_entity(gs.morphs.MJCF(file=FRANKA_MJCF))
    scene.build(n_envs=N_ENVS)
    scene.step()

    print(f"\n=== batched state shapes at n_envs={N_ENVS} ===", flush=True)
    report("cable.get_links_pos()", cable.get_links_pos())
    report("franka.get_qpos()", franka.get_qpos())
    report("franka.get_links_net_contact_force()", franka.get_links_net_contact_force())

    print("\n=== per-environment control ===", flush=True)
    print(f"  control_dofs_position{inspect.signature(franka.control_dofs_position)}", flush=True)
    print(f"  set_qpos{inspect.signature(franka.set_qpos)}", flush=True)
    print(f"  scene.reset{inspect.signature(scene.reset)}", flush=True)
    print(f"  cable.set_pos{inspect.signature(cable.set_pos)}", flush=True)

    print("\n=== inverse kinematics under batching ===", flush=True)
    solver = franka.inverse_kinematics
    print(f"  inverse_kinematics{inspect.signature(solver)}", flush=True)
    hand = franka.get_link("hand")
    try:
        single = solver(link=hand, pos=[0.46, -0.2, 0.2], quat=[0.0, 1.0, 0.0, 0.0])
        report("ik with one target", single)
    except Exception as error:
        print(f"  ik with one target raised {type(error).__name__}: {error}", flush=True)
    try:
        batched = solver(
            link=hand,
            pos=[[0.46, -0.2, 0.2]] * N_ENVS,
            quat=[[0.0, 1.0, 0.0, 0.0]] * N_ENVS,
        )
        report("ik with per-env targets", batched)
    except Exception as error:
        print(f"  ik with per-env targets raised {type(error).__name__}: {error}", flush=True)

    print("\n=== per-environment reset ===", flush=True)
    try:
        scene.reset(envs_idx=[0, 2])
        print("  scene.reset(envs_idx=[0, 2]) accepted", flush=True)
    except Exception as error:
        print(f"  scene.reset(envs_idx=...) raised {type(error).__name__}: {error}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
