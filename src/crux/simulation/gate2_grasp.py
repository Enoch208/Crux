from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from math import sqrt

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
ARM_DOFS = 7

CABLE_BASE_POS = (0.20, -0.25, 0.004)
GRASP_LINK_INDEX = 10

FINGER_IDX = [7, 8]
OPEN_FORCE_N = 5.0
CLOSE_FORCE_N = -15.0
OPEN_GAP_MIN_M = 0.05

PROBE_START_Z = 0.16
PROBE_STEP_M = 0.0015
PROBE_MIN_Z = 0.07
PROBE_STEPS = 25
TOUCH_MARGIN_N = 0.4

HOVER_HEIGHT_M = 0.20
RETREAT_M = 0.06
TIP_TO_CENTRE_M = 0.004
LIFT_STAGE1_M = 0.05
LIFT_HEIGHT_M = 0.25

PHASE_STEPS = 300
GRIP_STEPS = 200
HOME_STEPS = 50
MIN_LIFT_M = 0.05

ARM_IDX = list(range(ARM_DOFS))


def call_with_idx(method: Callable[..., object], values: list[float], idx: list[int]) -> object:
    try:
        return method(values, idx)
    except TypeError:
        pass
    try:
        return method(values, dofs_idx_local=idx)
    except TypeError:
        return method(values, dofs_idx=idx)


@dataclass(frozen=True, slots=True)
class Arm:
    step: Callable[[], object]
    control_position: Callable[..., object]
    control_force: Callable[..., object]
    set_qpos: Callable[[list[float]], object]
    get_qpos: Callable[[], object]
    ik: Callable[..., object]

    def run(self, steps: int) -> None:
        for _ in range(steps):
            self.step()

    def joint_targets(self, qpos_target: object) -> list[float]:
        rows = to_rows(qpos_target)
        flat = rows[0] if len(rows) == 1 else [row[0] for row in rows]
        return list(flat[:ARM_DOFS])

    def command(self, arm_targets: list[float], finger_force: float) -> None:
        call_with_idx(self.control_position, arm_targets, ARM_IDX)
        call_with_idx(self.control_force, [finger_force, finger_force], FINGER_IDX)

    def move_to(self, pos: Sequence[float], hand: object, finger_force: float, steps: int) -> None:
        target = self.ik(link=hand, pos=list(pos), quat=list(TOOL_DOWN_QUAT))
        self.command(self.joint_targets(target), finger_force)
        self.run(steps)

    def set_fingers(self, finger_force: float, steps: int) -> None:
        self.command(self.joint_targets(self.get_qpos()), finger_force)
        self.run(steps)

    def home(self) -> None:
        self.set_qpos(list(HOME_QPOS))
        self.command(list(HOME_QPOS[:ARM_DOFS]), OPEN_FORCE_N)
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
        control_position=getattr(franka, "control_dofs_position"),
        control_force=getattr(franka, "control_dofs_force"),
        set_qpos=getattr(franka, "set_qpos"),
        get_qpos=getattr(franka, "get_qpos"),
        ik=solver,
    )


def find_hand_link(franka: object) -> object:
    names = [str(getattr(link, "name", "?")) for link in getattr(franka, "links")]
    print(f"  franka links: {names}")
    for candidate in HAND_LINK_CANDIDATES:
        if candidate in names:
            return getattr(franka, "get_link")(candidate)
    raise RuntimeError(f"no hand link among {names}")


def flat_row(value: object) -> list[float]:
    rows = to_rows(value)
    return rows[0] if len(rows) == 1 else [row[0] for row in rows]


def dof_report(franka: object) -> None:
    accessors = (
        "get_dofs_limit",
        "get_dofs_force_range",
        "get_dofs_act_gain",
        "get_dofs_act_bias",
    )
    for accessor in accessors:
        reader = getattr(franka, accessor, None)
        if not callable(reader):
            print(f"  {accessor}: absent")
            continue
        try:
            value = reader()
            if isinstance(value, tuple):
                printable = tuple(flat_row(part) for part in value)
            else:
                printable = (flat_row(value),)
            for part in printable:
                print(f"  {accessor}: {[round(v, 3) for v in part]}")
        except Exception as error:
            print(f"  {accessor}: failed with {type(error).__name__}: {error}")


def link_position(entity: object, name: str) -> list[float]:
    return list(to_rows(getattr(getattr(entity, "get_link")(name), "get_pos")())[0])


def finger_gap_m(franka: object) -> float:
    left = link_position(franka, FINGER_LINK_NAMES[0])
    right = link_position(franka, FINGER_LINK_NAMES[1])
    return sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def hand_height(hand: object) -> float:
    return to_rows(getattr(hand, "get_pos")())[0][2]


def contact_peak(entity: object) -> float:
    rows = to_rows(getattr(entity, "get_links_net_contact_force")())
    return max(abs(value) for row in rows for value in row)


def fmt(row: Sequence[float]) -> str:
    return "[" + ", ".join(f"{v:+.4f}" for v in row[:3]) + "]"


def assert_fingers_open(arm: Arm, franka: object) -> float:
    arm.set_fingers(OPEN_FORCE_N, GRIP_STEPS)
    gap = finger_gap_m(franka)
    print(f"  finger gap open: {gap * 1000:.1f} mm (need > {OPEN_GAP_MIN_M * 1000:.0f} mm)")
    if gap < OPEN_GAP_MIN_M:
        raise RuntimeError(
            f"fingers did not open: gap {gap * 1000:.1f} mm under {OPEN_FORCE_N} N of "
            f"outward force per finger"
        )
    return gap


def touch_cable(arm: Arm, hand: object, cable: object, grasp_xy: tuple[float, float]) -> float:
    baseline = contact_peak(cable)
    trigger = baseline + TOUCH_MARGIN_N
    print(f"  cable resting contact {baseline:.3f} N, touch trigger {trigger:.3f} N")
    target_z = PROBE_START_Z
    while target_z >= PROBE_MIN_Z:
        arm.move_to((*grasp_xy, target_z), hand, CLOSE_FORCE_N, PROBE_STEPS)
        force = contact_peak(cable)
        if force > trigger:
            touched = hand_height(hand)
            print(f"  touched cable at hand z {touched * 1000:.1f} mm, force {force:.3f} N")
            return touched
        target_z -= PROBE_STEP_M
    raise RuntimeError(f"never felt the cable above hand z {PROBE_MIN_Z} m")


def main() -> int:
    spec = load_spec(CONFIG_PATH)
    urdf_path = write_urdf(spec, URDF_OUTPUT).resolve()
    grasp_xy = (
        CABLE_BASE_POS[0] + GRASP_LINK_INDEX * spec.segment_length_m,
        CABLE_BASE_POS[1],
    )

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
    hand = find_hand_link(franka)
    stage("dof report", lambda: dof_report(franka))
    stage("home franka", arm.home)
    stage("verify fingers open under force control", lambda: assert_fingers_open(arm, franka))

    before = list(read_link_positions(cable)[GRASP_LINK_INDEX])
    print(f"  grasp point      : ({grasp_xy[0]:+.4f}, {grasp_xy[1]:+.4f})")
    print(f"  grasp link before: {fmt(before)}")

    stage(
        "hover above grasp point",
        lambda: arm.move_to((*grasp_xy, HOVER_HEIGHT_M), hand, CLOSE_FORCE_N, PHASE_STEPS),
    )
    touched_z = stage(
        "probe down to cable top",
        lambda: touch_cable(arm, hand, cable, grasp_xy),
    )
    hand_to_tip = touched_z - 2.0 * spec.radius_m
    grasp_z = touched_z - TIP_TO_CENTRE_M
    print(f"  hand-to-tip {hand_to_tip * 1000:.1f} mm, grasp hand z {grasp_z * 1000:.1f} mm")

    stage(
        "retreat and open",
        lambda: arm.move_to((*grasp_xy, touched_z + RETREAT_M), hand, OPEN_FORCE_N, PHASE_STEPS),
    )
    print(f"  finger gap: {finger_gap_m(franka) * 1000:.1f} mm")

    stage(
        "descend around cable",
        lambda: arm.move_to((*grasp_xy, grasp_z), hand, OPEN_FORCE_N, PHASE_STEPS),
    )
    print(f"  hand z {hand_height(hand) * 1000:.1f} mm (target {grasp_z * 1000:.1f})")
    print(f"  finger gap: {finger_gap_m(franka) * 1000:.1f} mm")
    print(f"  cable contact: {contact_peak(cable):.3f} N")

    stage("close gripper", lambda: arm.set_fingers(CLOSE_FORCE_N, GRIP_STEPS))
    closed_gap = finger_gap_m(franka)
    print(f"  finger gap closed on cable: {closed_gap * 1000:.1f} mm")
    print(f"  cable contact: {contact_peak(cable):.3f} N")

    stage(
        "lift stage 1",
        lambda: arm.move_to((*grasp_xy, grasp_z + LIFT_STAGE1_M), hand, CLOSE_FORCE_N, PHASE_STEPS),
    )
    stage(
        "lift stage 2",
        lambda: arm.move_to(
            (*grasp_xy, hand_to_tip + LIFT_HEIGHT_M), hand, CLOSE_FORCE_N, PHASE_STEPS
        ),
    )

    after = list(read_link_positions(cable)[GRASP_LINK_INDEX])
    raised = after[2] - before[2]
    print(f"\n  grasp link after : {fmt(after)}")
    print(f"  link raised by   : {raised * 1000:+.1f} mm (need > {MIN_LIFT_M * 1000:.0f} mm)")
    print(f"  finger gap       : {finger_gap_m(franka) * 1000:.1f} mm")
    print(f"  cable contact    : {contact_peak(cable):.3f} N")

    if raised <= MIN_LIFT_M:
        raise RuntimeError(
            f"grasp failed: link rose {raised * 1000:.1f} mm; the gripper did not hold the cable"
        )

    print("\nFranka grasped the cable and lifted it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
