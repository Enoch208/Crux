from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import genesis as gs

from crux.simulation.gate1 import (
    CONFIG_PATH,
    TIMESTEP_S,
    URDF_OUTPUT,
    load_spec,
    read_link_positions,
    stage,
    to_rows,
    write_urdf,
)

FRANKA_MJCF = "xml/franka_emika_panda/panda.xml"
HOME_QPOS = (0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785, 0.04, 0.04)
HAND_LINK_CANDIDATES = ("hand", "panda_hand", "hand_tcp")
TOOL_DOWN_QUAT = (0.0, 1.0, 0.0, 0.0)

CABLE_BASE_POS = (0.20, -0.25, 0.004)
GRASP_LINK_INDEX = 10
HAND_TO_FINGERTIP_M = 0.103
HOVER_HEIGHT_M = 0.15
GRASP_CLEARANCE_M = 0.004
LIFT_HEIGHT_M = 0.25

PHASE_STEPS = 300
GRIP_STEPS = 150
HOME_STEPS = 50
MIN_LIFT_M = 0.05
FINGER_OPEN_M = 0.04
FINGER_CLOSED_M = 0.0


@dataclass(frozen=True, slots=True)
class Arm:
    step: Callable[[], object]
    control: Callable[[list[float]], object]
    set_qpos: Callable[[list[float]], object]
    get_qpos: Callable[[], object]
    ik: Callable[..., object]

    def run(self, steps: int) -> None:
        for _ in range(steps):
            self.step()

    def joint_targets(self, qpos_target: object) -> list[float]:
        rows = to_rows(qpos_target)
        flat = rows[0] if len(rows) == 1 else [row[0] for row in rows]
        return list(flat[:7])

    def move_to(self, pos: Sequence[float], hand: object, finger_m: float, steps: int) -> None:
        target = self.ik(link=hand, pos=list(pos), quat=list(TOOL_DOWN_QUAT))
        self.control([*self.joint_targets(target), finger_m, finger_m])
        self.run(steps)

    def set_fingers(self, finger_m: float, steps: int) -> None:
        held = self.joint_targets(self.get_qpos())
        self.control([*held, finger_m, finger_m])
        self.run(steps)

    def home(self) -> None:
        self.set_qpos(list(HOME_QPOS))
        self.control(list(HOME_QPOS))
        self.run(HOME_STEPS)


def build_arm(scene: object, franka: object) -> Arm:
    solver = getattr(franka, "inverse_kinematics", None)
    if not callable(solver):
        raise RuntimeError(
            f"no inverse_kinematics on {type(franka).__name__}; "
            f"candidates: {[a for a in dir(franka) if 'kinematic' in a.lower()]}"
        )
    return Arm(
        step=getattr(scene, "step"),
        control=getattr(franka, "control_dofs_position"),
        set_qpos=getattr(franka, "set_qpos"),
        get_qpos=getattr(franka, "get_qpos"),
        ik=solver,
    )


def grasp_target_x(segment_length: float) -> float:
    return CABLE_BASE_POS[0] + GRASP_LINK_INDEX * segment_length


def find_hand_link(franka: object) -> object:
    names = [str(getattr(link, "name", "?")) for link in getattr(franka, "links")]
    print(f"  franka links: {names}")
    for candidate in HAND_LINK_CANDIDATES:
        if candidate in names:
            print(f"  hand link: {candidate}")
            return getattr(franka, "get_link")(candidate)
    raise RuntimeError(f"no hand link among {names}")


def contact_peak(entity: object) -> float:
    rows = to_rows(getattr(entity, "get_links_net_contact_force")())
    return max(abs(value) for row in rows for value in row)


def fmt(row: Sequence[float]) -> str:
    return "[" + ", ".join(f"{v:+.4f}" for v in row[:3]) + "]"


def report_hand(hand: object) -> None:
    getter = getattr(hand, "get_pos", None)
    if callable(getter):
        print(f"  hand at {fmt(to_rows(getter())[0])}")


def main() -> int:
    spec = load_spec(CONFIG_PATH)
    urdf_path = write_urdf(spec, URDF_OUTPUT).resolve()
    target_x = grasp_target_x(spec.segment_length_m)

    stage("gs.init(backend=gs.amdgpu)", lambda: gs.init(backend=gs.amdgpu))
    if gs.backend != gs.amdgpu:
        raise RuntimeError(f"Genesis resolved to {gs.backend!r}, not gs.amdgpu")

    scene = stage(
        "create scene",
        lambda: gs.Scene(sim_options=gs.options.SimOptions(dt=TIMESTEP_S), show_viewer=False),
    )
    stage("add plane", lambda: scene.add_entity(gs.morphs.Plane()))
    cable = stage(
        "add cable on floor",
        lambda: scene.add_entity(gs.morphs.URDF(file=str(urdf_path), pos=CABLE_BASE_POS)),
    )
    franka = stage(
        "add franka at origin",
        lambda: scene.add_entity(gs.morphs.MJCF(file=FRANKA_MJCF)),
    )
    stage("scene.build", lambda: scene.build())

    arm = build_arm(scene, franka)
    stage("home franka", arm.home)
    hand = find_hand_link(franka)

    grasp_x, grasp_y = target_x, CABLE_BASE_POS[1]
    hover = (grasp_x, grasp_y, HOVER_HEIGHT_M + HAND_TO_FINGERTIP_M)
    descend = (grasp_x, grasp_y, spec.radius_m + GRASP_CLEARANCE_M + HAND_TO_FINGERTIP_M)
    lift = (grasp_x, grasp_y, LIFT_HEIGHT_M + HAND_TO_FINGERTIP_M)

    before = list(read_link_positions(cable)[GRASP_LINK_INDEX])
    print(f"  grasp target x   : {grasp_x:+.4f}")
    print(f"  grasp link before: {fmt(before)}")

    stage("hover above cable", lambda: arm.move_to(hover, hand, FINGER_OPEN_M, PHASE_STEPS))
    report_hand(hand)

    stage("descend to cable", lambda: arm.move_to(descend, hand, FINGER_OPEN_M, PHASE_STEPS))
    report_hand(hand)
    print(f"  contact before close: {contact_peak(cable):.4f} N")

    stage("close gripper", lambda: arm.set_fingers(FINGER_CLOSED_M, GRIP_STEPS))
    print(f"  contact after close : {contact_peak(cable):.4f} N")

    stage("lift", lambda: arm.move_to(lift, hand, FINGER_CLOSED_M, PHASE_STEPS))
    report_hand(hand)

    after = list(read_link_positions(cable)[GRASP_LINK_INDEX])
    raised = after[2] - before[2]
    print(f"\n  grasp link after : {fmt(after)}")
    print(f"  link raised by   : {raised * 1000:+.1f} mm (need > {MIN_LIFT_M * 1000:.0f} mm)")
    print(f"  cable contact    : {contact_peak(cable):.4f} N")

    if raised <= MIN_LIFT_M:
        raise RuntimeError(
            f"grasp failed: link rose {raised * 1000:.1f} mm; the gripper did not hold the cable"
        )

    print("\nFranka grasped the cable and lifted it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
