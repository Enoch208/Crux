from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import genesis as gs

from crux.simulation.gate1 import (
    CONFIG_PATH,
    TIMESTEP_S,
    URDF_OUTPUT,
    Rows,
    load_spec,
    read_link_positions,
    stage,
    to_rows,
    write_urdf,
)

FRANKA_MJCF = "xml/franka_emika_panda/panda.xml"
ANCHOR_HEIGHT_M = 0.60
SETTLE_STEPS = 800
MIN_SAG_M = 0.05
MIN_JOINT_ANGLE_RAD = 0.01
MIN_CONTACT_FORCE_N = 1e-4


def height_spread(rows: Rows) -> float:
    heights = [row[2] for row in rows]
    return max(heights) - min(heights)


def largest_joint_angle(cable: object) -> float:
    reader = getattr(cable, "get_dofs_position", None)
    if not callable(reader):
        raise RuntimeError("cable entity exposes no get_dofs_position()")
    rows = to_rows(reader())
    return max(abs(value) for row in rows for value in row)


def largest_contact_force(entity: object) -> float:
    reader = getattr(entity, "get_links_net_contact_force", None)
    if not callable(reader):
        raise RuntimeError("entity exposes no get_links_net_contact_force()")
    rows = to_rows(reader())
    return max(abs(value) for row in rows for value in row)


def main() -> int:
    spec = load_spec(CONFIG_PATH)
    urdf_path = write_urdf(spec, URDF_OUTPUT).resolve()

    stage("gs.init(backend=gs.amdgpu)", lambda: gs.init(backend=gs.amdgpu))
    if gs.backend != gs.amdgpu:
        raise RuntimeError(f"Genesis resolved to {gs.backend!r}, not gs.amdgpu")

    scene = stage(
        "create scene",
        lambda: gs.Scene(sim_options=gs.options.SimOptions(dt=TIMESTEP_S), show_viewer=False),
    )
    stage("add plane", lambda: scene.add_entity(gs.morphs.Plane()))

    cable = stage(
        "add cable anchored in the air",
        lambda: scene.add_entity(
            gs.morphs.URDF(
                file=str(urdf_path),
                pos=(0.0, 0.0, ANCHOR_HEIGHT_M),
                fixed=True,
            )
        ),
    )

    franka = stage("add franka", lambda: load_franka(scene.add_entity))
    stage("scene.build", lambda: scene.build())

    if franka is not None:
        print(f"  franka {describe_franka(franka)}")

    straight = read_link_positions(cable)
    print(f"  before settling, height spread: {height_spread(straight) * 1000:.2f} mm")

    stage(
        f"hang under gravity, {SETTLE_STEPS} steps",
        lambda: run_steps(scene.step, SETTLE_STEPS),
    )

    positions = read_link_positions(cable)
    sag = height_spread(positions)
    joint_angle = largest_joint_angle(cable)
    cable_force = largest_contact_force(cable)

    print(f"\n  link heights spread : {sag * 1000:.2f} mm   (need > {MIN_SAG_M * 1000:.0f} mm)")
    print(f"  largest joint angle : {joint_angle:.4f} rad (need > {MIN_JOINT_ANGLE_RAD})")
    print(f"  cable contact force : {cable_force:.4f} N")
    print(f"  anchored link       : {positions[0][2] * 1000:+.1f} mm")
    print(f"  middle link         : {positions[len(positions) // 2][2] * 1000:+.1f} mm")
    print(f"  free end            : {positions[-1][2] * 1000:+.1f} mm")
    print(f"  free end horizontal : x={positions[-1][0] * 1000:+.1f} mm")

    failures: list[str] = []
    if sag <= MIN_SAG_M:
        failures.append(f"cable did not bend: height spread {sag:.5f} m")
    if joint_angle <= MIN_JOINT_ANGLE_RAD:
        failures.append(f"joints stayed straight: largest angle {joint_angle:.5f} rad")
    if failures:
        raise RuntimeError("; ".join(failures))

    print("\nCable hangs under gravity: the articulated chain bends as a cable.")
    return 0


def describe_franka(franka: object) -> str:
    return f"links={getattr(franka, 'n_links', None)} dofs={getattr(franka, 'n_dofs', None)}"


def load_franka(add_entity: Callable[..., object]) -> object:
    try:
        return add_entity(gs.morphs.MJCF(file=FRANKA_MJCF))
    except Exception as error:
        print(f"  franka load failed: {type(error).__name__}: {error}")
        assets = Path(gs.__file__).parent / "assets" / "xml"
        if assets.is_dir():
            print(f"  available xml assets: {sorted(p.name for p in assets.iterdir())[:20]}")
        return None


def run_steps(step: Callable[[], object], steps: int) -> int:
    for _ in range(steps):
        step()
    return steps


if __name__ == "__main__":
    raise SystemExit(main())
