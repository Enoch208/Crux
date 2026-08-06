"""Measure why position control does nothing on the tendon-approximated Franka fingers.

Genesis position mode computes, per DOF:

    force = act_gain * (ctrl_pos - pos)
          + act_bias[0]
          + (act_gain + act_bias[1]) * pos
          + act_bias[2] * (vel - ctrl_vel)

so a commanded position only reaches the joint through `act_gain`, and is clamped by
`force_range`. This prints those coefficients for the arm and finger DOFs so the cause
of the observed no-op can be named exactly rather than inferred.
"""

from __future__ import annotations

import genesis as gs

FRANKA_MJCF = "xml/franka_emika_panda/panda.xml"
FINGER_DOFS = (7, 8)


def main() -> int:
    gs.init(backend=gs.gpu)
    scene = gs.Scene(sim_options=gs.options.SimOptions(dt=0.005), show_viewer=False)
    scene.add_entity(gs.morphs.Plane())
    franka = scene.add_entity(gs.morphs.MJCF(file=FRANKA_MJCF))
    scene.build()

    gain = franka.get_dofs_act_gain()
    bias = franka.get_dofs_act_bias()
    force_range = franka.get_dofs_force_range()

    print("\ndof | act_gain | act_bias[0] | act_bias[1] | act_bias[2] | force_range")
    for dof in range(len(gain)):
        marker = "  <-- finger" if dof in FINGER_DOFS else ""
        print(
            f"{dof:3d} | {float(gain[dof]):8.3f} | {float(bias[0][dof]):11.3f} | "
            f"{float(bias[1][dof]):11.3f} | {float(bias[2][dof]):11.3f} | "
            f"[{float(force_range[0][dof]):.2f}, {float(force_range[1][dof]):.2f}]{marker}"
        )

    print("\nposition target reaches the joint only through act_gain:")
    for dof in FINGER_DOFS:
        print(f"  dof {dof}: act_gain = {float(gain[dof]):.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
