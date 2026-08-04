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
FINGER_LINK_NAMES = ("left_finger", "right_finger")
TOOL_DOWN_QUAT = (0.0, 1.0, 0.0, 0.0)

CABLE_BASE_POS = (0.20, -0.25, 0.004)
GRASP_LINK_INDEX = 10
HOVER_HEIGHT_M = 0.15
LIFT_HEIGHT_M = 0.25

PROBE_XY = (0.35, 0.05)
PROBE_START_Z = 0.150
PROBE_STEP_M = 0.002
PROBE_FLOOR_Z = 0.095
PROBE_STEPS = 40
TOUCH_FORCE_N = 1.0

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


def link_position(entity: object, name: str) -> list[float]:
    return list(to_rows(getattr(getattr(entity, "get_link")(name), "get_pos")())[0])


def finger_link_indices(franka: object) -> list[int]:
    names = [str(getattr(link, "name", "?")) for link in getattr(franka, "links")]
    return [index for index, name in enumerate(names) if name in FINGER_LINK_NAMES]


def finger_contact(franka: object, indices: list[int]) -> float:
    rows = to_rows(getattr(franka, "get_links_net_contact_force")())
    return max(abs(value) for index in indices for value in rows[index])


def hand_height(hand: object) -> float:
    return to_rows(getattr(hand, "get_pos")())[0][2]


def finger_gap_mm(franka: object) -> float:
    left = link_position(franka, FINGER_LINK_NAMES[0])
    right = link_position(franka, FINGER_LINK_NAMES[1])
    return 1000.0 * abs(left[1] - right[1])


def calibrate_hand_to_tip(arm: Arm, franka: object, hand: object, indices: list[int]) -> float:
    target_z = PROBE_START_Z
    while target_z >= PROBE_FLOOR_Z:
        arm.move_to((*PROBE_XY, target_z), hand, FINGER_OPEN_M, PROBE_STEPS)
        force = finger_contact(franka, indices)
        if force > TOUCH_FORCE_N:
            measured = hand_height(hand)
            print(
                f"  touch at hand z {measured * 1000:.1f} mm, finger force {force:.2f} N "
                f"-> hand-to-tip {measured * 1000:.1f} mm"
            )
            return measured
        target_z -= PROBE_STEP_M
    raise RuntimeError(
        f"fingers never touched the floor above hand z {PROBE_FLOOR_Z} m; "
        f"finger contact stayed below {TOUCH_FORCE_N} N"
    )


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
    indices = finger_link_indices(franka)

    hand_to_tip = stage(
        "calibrate hand-to-tip by touching the floor",
        lambda: calibrate_hand_to_tip(arm, franka, hand, indices),
    )
    stage("re-home", arm.home)

    grasp_x, grasp_y = target_x, CABLE_BASE_POS[1]
    hover = (grasp_x, grasp_y, HOVER_HEIGHT_M + hand_to_tip)
    descend = (grasp_x, grasp_y, spec.radius_m + hand_to_tip)
    lift = (grasp_x, grasp_y, LIFT_HEIGHT_M + hand_to_tip)

    before = list(read_link_positions(cable)[GRASP_LINK_INDEX])
    print(f"  grasp target x   : {grasp_x:+.4f}")
    print(f"  grasp link before: {fmt(before)}")
    print(f"  descend hand to z: {descend[2]:+.4f} (tips at cable centre)")

    stage("hover above cable", lambda: arm.move_to(hover, hand, FINGER_OPEN_M, PHASE_STEPS))
    report_hand(hand)

    stage("descend to cable", lambda: arm.move_to(descend, hand, FINGER_OPEN_M, PHASE_STEPS))
    report_hand(hand)
    print(f"  finger gap          : {finger_gap_mm(franka):.1f} mm")
    print(f"  contact before close: {contact_peak(cable):.4f} N")

    stage("close gripper", lambda: arm.set_fingers(FINGER_CLOSED_M, GRIP_STEPS))
    print(f"  finger gap          : {finger_gap_mm(franka):.1f} mm")
    print(f"  finger force        : {finger_contact(franka, indices):.4f} N")
    print(f"  contact after close : {contact_peak(cable):.4f} N")

    stage("lift", lambda: arm.move_to(lift, hand, FINGER_CLOSED_M, PHASE_STEPS))
    report_hand(hand)
    print(f"  finger gap          : {finger_gap_mm(franka):.1f} mm")

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
