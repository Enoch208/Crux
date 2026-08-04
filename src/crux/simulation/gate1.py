from __future__ import annotations

import traceback
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import genesis as gs
import yaml

from crux.simulation.cable import CableSpec, build_cable_urdf

CONFIG_PATH = Path("configs/cable.yaml")
URDF_OUTPUT = Path("build/cable.urdf")
SETTLE_STEPS = 200
REPEAT_RUNS = 3
POSITION_TOLERANCE_M = 1e-6
DROP_HEIGHT_M = 0.3
TIMESTEP_S = 0.005

T = TypeVar("T")

Rows = list[list[float]]


def load_spec(path: Path) -> CableSpec:
    return CableSpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def write_urdf(spec: CableSpec, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_cable_urdf(spec), encoding="utf-8")
    return path


def stage(name: str, action: Callable[[], T]) -> T:
    print(f"\n--- {name} ---", flush=True)
    try:
        result = action()
    except Exception:
        print(f"FAIL {name}", flush=True)
        traceback.print_exc()
        raise
    print(f"PASS {name}", flush=True)
    return result


def describe(label: str, value: object) -> None:
    names = [a for a in dir(value) if not a.startswith("_")]
    keys = ("pos", "state", "link", "dof")
    interesting = sorted(a for a in names if any(k in a.lower() for k in keys))
    print(f"{label}: {type(value).__name__}")
    print(f"  position/state API: {interesting}")


def to_rows(value: object) -> Rows:
    tensor = value
    cpu = getattr(tensor, "cpu", None)
    if callable(cpu):
        tensor = cpu()
    tolist = getattr(tensor, "tolist", None)
    if not callable(tolist):
        raise RuntimeError(f"cannot read {type(value).__name__} as a numeric array")
    rows = tolist()
    if not isinstance(rows, list) or not rows:
        raise RuntimeError(f"state accessor returned {rows!r}")
    if not isinstance(rows[0], list):
        return [[float(v) for v in rows]]
    return [[float(v) for v in row] for row in rows]


def read_link_positions(cable: object) -> Rows:
    for method in ("get_links_pos", "get_pos", "get_dofs_position"):
        reader = getattr(cable, method, None)
        if not callable(reader):
            continue
        print(f"  read state via {method}()")
        return to_rows(reader())
    raise RuntimeError(
        f"no known position accessor on {type(cable).__name__}; "
        f"candidates: {[a for a in dir(cable) if 'pos' in a.lower()]}"
    )


def settle_and_read(step: Callable[[], object], cable: object, steps: int) -> Rows:
    for _ in range(steps):
        step()
    return read_link_positions(cable)


def format_row(rows: Rows, index: int) -> str:
    return "[" + ", ".join(f"{v:+.6f}" for v in rows[index][:3]) + "]"


def max_deviation(left: Rows, right: Rows) -> float:
    if len(left) != len(right):
        raise RuntimeError(f"state shape changed across reset: {len(left)} vs {len(right)} rows")
    return max(
        abs(x - y)
        for row_a, row_b in zip(left, right, strict=True)
        for x, y in zip(row_a, row_b, strict=True)
    )


def check_repeatable(
    step: Callable[[], object],
    reset: Callable[[], object],
    cable: object,
    reference: Rows,
) -> list[float]:
    deviations: list[float] = []
    for run in range(REPEAT_RUNS):
        reset()
        repeated = settle_and_read(step, cable, SETTLE_STEPS)
        deviation = max_deviation(reference, repeated)
        deviations.append(deviation)
        verdict = "OK" if deviation <= POSITION_TOLERANCE_M else "DIVERGED"
        print(f"  run {run + 1}: max deviation {deviation:.3e} m  {verdict}")
    worst = max(deviations)
    if worst > POSITION_TOLERANCE_M:
        raise RuntimeError(
            f"reset is not repeatable: worst deviation {worst:.3e} m exceeds "
            f"{POSITION_TOLERANCE_M:.1e} m"
        )
    return deviations


def main() -> int:
    spec = load_spec(CONFIG_PATH)
    print(
        f"cable: {spec.segments} links, {spec.segment_length_m * 1000:.1f} mm each, "
        f"{spec.total_mass_kg * 1000:.1f} g total"
    )
    urdf_path = write_urdf(spec, URDF_OUTPUT).resolve()
    print(f"urdf: {urdf_path} ({urdf_path.stat().st_size} bytes)")

    stage("gs.init(backend=gs.amdgpu)", lambda: gs.init(backend=gs.amdgpu))
    if gs.backend != gs.amdgpu:
        raise RuntimeError(f"Genesis resolved to {gs.backend!r}, not gs.amdgpu")

    scene = stage(
        "create scene",
        lambda: gs.Scene(sim_options=gs.options.SimOptions(dt=TIMESTEP_S), show_viewer=False),
    )
    stage("add plane", lambda: scene.add_entity(gs.morphs.Plane()))
    cable = stage(
        "add cable",
        lambda: scene.add_entity(
            gs.morphs.URDF(file=str(urdf_path), pos=(0.0, 0.0, DROP_HEIGHT_M))
        ),
    )
    stage("scene.build", lambda: scene.build())

    describe("cable entity", cable)

    positions = stage(
        f"settle {SETTLE_STEPS} steps",
        lambda: settle_and_read(scene.step, cable, SETTLE_STEPS),
    )
    print(f"  links read: {len(positions)}")
    print(f"  first link: {format_row(positions, 0)}")
    print(f"  last  link: {format_row(positions, -1)}")

    stage(
        f"reset repeatability over {REPEAT_RUNS} runs",
        lambda: check_repeatable(scene.step, scene.reset, cable, positions),
    )
    print("\nGate 1 scene checks completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
