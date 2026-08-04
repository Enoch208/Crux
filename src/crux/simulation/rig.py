from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from math import sqrt

from crux.control.tooling import TOOL_DOWN_QUAT, tool_down_yaw_quat
from crux.simulation.gate1 import Rows, to_rows

ARM_DOFS = 7
ARM_IDX = list(range(ARM_DOFS))
FINGER_IDX = [7, 8]
HOME_QPOS = (0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785, 0.04, 0.04)
HAND_LINK_CANDIDATES = ("hand", "panda_hand", "hand_tcp")
FINGER_LINK_NAMES = ("left_finger", "right_finger")
HOME_STEPS = 50

Monitor = Callable[[int], None]


def call_with_idx(method: Callable[..., object], values: list[float], idx: list[int]) -> object:
    try:
        return method(values, idx)
    except TypeError:
        pass
    try:
        return method(values, dofs_idx_local=idx)
    except TypeError:
        return method(values, dofs_idx=idx)


def flat_row(value: object) -> list[float]:
    rows = to_rows(value)
    return rows[0] if len(rows) == 1 else [row[0] for row in rows]


def link_position(entity: object, name: str) -> list[float]:
    return list(to_rows(getattr(entity, "get_link")(name).get_pos())[0])


def finger_gap_m(franka: object) -> float:
    left = link_position(franka, FINGER_LINK_NAMES[0])
    right = link_position(franka, FINGER_LINK_NAMES[1])
    return sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def per_link_contact(entity: object) -> list[float]:
    rows = to_rows(getattr(entity, "get_links_net_contact_force")())
    return [sqrt(sum(value * value for value in row)) for row in rows]


def contact_peak(entity: object) -> float:
    return max(per_link_contact(entity))


def hand_height(hand: object) -> float:
    return to_rows(getattr(hand, "get_pos")())[0][2]


def fmt(row: Sequence[float]) -> str:
    return "[" + ", ".join(f"{v:+.4f}" for v in row[:3]) + "]"


def find_hand_link(franka: object) -> object:
    names = [str(getattr(link, "name", "?")) for link in getattr(franka, "links")]
    for candidate in HAND_LINK_CANDIDATES:
        if candidate in names:
            return getattr(franka, "get_link")(candidate)
    raise RuntimeError(f"no hand link among {names}")


@dataclass(frozen=True, slots=True)
class Arm:
    step: Callable[[], object]
    control_position: Callable[..., object]
    control_force: Callable[..., object]
    set_qpos: Callable[[list[float]], object]
    get_qpos: Callable[[], object]
    ik: Callable[..., object]
    chunk_steps: int

    def run(self, steps: int, monitor: Monitor | None = None) -> None:
        done = 0
        while done < steps:
            burst = min(self.chunk_steps, steps - done)
            for _ in range(burst):
                self.step()
            done += burst
            if monitor is not None:
                monitor(done)

    def joint_targets(self, qpos_target: object) -> list[float]:
        rows = to_rows(qpos_target)
        flat = rows[0] if len(rows) == 1 else [row[0] for row in rows]
        return list(flat[:ARM_DOFS])

    def command(self, arm_targets: list[float], finger_force: float) -> None:
        call_with_idx(self.control_position, arm_targets, ARM_IDX)
        call_with_idx(self.control_force, [finger_force, finger_force], FINGER_IDX)

    def move_to(
        self,
        pos: Sequence[float],
        hand: object,
        finger_force: float,
        steps: int,
        monitor: Monitor | None = None,
        quat: Sequence[float] = TOOL_DOWN_QUAT,
    ) -> None:
        target = self.ik(link=hand, pos=list(pos), quat=list(quat))
        self.command(self.joint_targets(target), finger_force)
        self.run(steps, monitor)

    def hold_fingers(self, finger_force: float, steps: int, monitor: Monitor | None = None) -> None:
        self.command(self.joint_targets(self.get_qpos()), finger_force)
        self.run(steps, monitor)

    def home(self, open_force: float) -> None:
        self.set_qpos(list(HOME_QPOS))
        self.command(list(HOME_QPOS[:ARM_DOFS]), open_force)
        self.run(HOME_STEPS)


def build_rig_arm(scene: object, franka: object, chunk_steps: int) -> Arm:
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
        chunk_steps=chunk_steps,
    )


def rows_are_finite(rows: Rows) -> bool:
    return all(value == value and abs(value) < 1e6 for row in rows for value in row)


__all__ = ["TOOL_DOWN_QUAT", "tool_down_yaw_quat"]
