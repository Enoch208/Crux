"""Minimal reproduction: position control is silently ignored on tendon-approximated joints.

Genesis 1.3.1, AMD Radeon PRO W7900 (gfx1100), ROCm 7.2.1, torch 2.13.0+rocm7.2.

The bundled Franka MJCF declares its two finger joints through a tendon. Genesis warns that
it is "Approximating tendon by joint actuator", and the resulting DOFs get a general
gain/bias actuator rather than a PD one. Two consequences, neither of them signalled to the
caller at the point of use:

1. `control_dofs_position` on those DOFs does nothing at all, and returns normally.
2. `get_dofs_kp` on those DOFs raises, so a caller cannot detect the situation by asking
   whether the joints are position-controllable.

The practical effect is that a gripper written against the documented position-control API
appears to work - no exception, no warning - while the fingers never move. Force control on
the same DOFs works correctly, which is the workaround this script demonstrates.
"""

from __future__ import annotations

import genesis as gs

FRANKA_MJCF = "xml/franka_emika_panda/panda.xml"
FINGER_DOFS = [7, 8]
OPEN_TARGET = [0.04, 0.04]
CLOSE_TARGET = [0.0, 0.0]
OPEN_FORCE = [5.0, 5.0]
STEPS = 400


def finger_gap(franka: object) -> float:
    left = franka.get_link("left_finger").get_pos()
    right = franka.get_link("right_finger").get_pos()
    return float(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)) ** 0.5)


def main() -> int:
    gs.init(backend=gs.gpu)
    scene = gs.Scene(sim_options=gs.options.SimOptions(dt=0.005), show_viewer=False)
    scene.add_entity(gs.morphs.Plane())
    franka = scene.add_entity(gs.morphs.MJCF(file=FRANKA_MJCF))
    scene.build()

    print("\n1. can the caller detect that these DOFs are not position-controllable?")
    try:
        print(f"   get_dofs_kp -> {franka.get_dofs_kp(FINGER_DOFS)}")
    except Exception as error:
        print(f"   get_dofs_kp raised {type(error).__name__}: {error}")

    print("\n2. position control, the documented API")
    franka.control_dofs_position(CLOSE_TARGET, FINGER_DOFS)
    for _ in range(STEPS):
        scene.step()
    closed_gap = finger_gap(franka)
    franka.control_dofs_position(OPEN_TARGET, FINGER_DOFS)
    for _ in range(STEPS):
        scene.step()
    opened_gap = finger_gap(franka)
    print(
        f"   commanded close then open: gap {closed_gap * 1000:.1f} -> {opened_gap * 1000:.1f} mm"
    )
    print(
        f"   no exception raised, and the fingers moved {abs(opened_gap - closed_gap) * 1000:.2f} mm"
    )

    print("\n3. force control on the same DOFs")
    franka.control_dofs_force(OPEN_FORCE, FINGER_DOFS)
    for _ in range(STEPS):
        scene.step()
    forced_gap = finger_gap(franka)
    print(f"   commanded +5 N per finger: gap -> {forced_gap * 1000:.1f} mm")
    print(f"   the fingers moved {abs(forced_gap - opened_gap) * 1000:.2f} mm")

    print(
        "\nExpected: either position control works, or it reports that it cannot. "
        "Observed: it silently does nothing while force control works."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
