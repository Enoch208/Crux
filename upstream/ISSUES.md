# Genesis issues — FILED 2026-08-05 at github.com/Genesis-Embodied-AI/genesis-world

1. https://github.com/Genesis-Embodied-AI/genesis-world/issues/3177
2. https://github.com/Genesis-Embodied-AI/genesis-world/issues/3178
3. https://github.com/Genesis-Embodied-AI/genesis-world/issues/3179

Filed with verbatim console logs captured on the box (Ubuntu 24.04.4, ROCm 7.2.1,
Genesis 1.3.1); dup-checked against the upstream tracker first. Original drafts below.

## 1. `control_dofs_position` silently ignored on tendon-approximated joints

**Title:** Position control silently does nothing on tendon-approximated finger joints, and `get_dofs_kp` raises instead of reporting it

**Body:**
Genesis 1.3.1, ROCm 7.2.1 backend (`gs.amdgpu`), AMD Radeon PRO W7900.

Loading the bundled `xml/franka_emika_panda/panda.xml` prints
`(MJCF) Approximating tendon by joint actuator for finger_joint1/2`. The resulting
finger DOFs get a general gain/bias actuator, with two consequences that are invisible
at the call site:

1. `control_dofs_position` on those DOFs returns normally and moves nothing.
2. `get_dofs_kp` on those DOFs raises — so a caller cannot detect the situation by
   asking whether the joints are position-controllable.

A gripper written against the documented position API appears to work while the fingers
never move. `control_dofs_force` on the same DOFs works correctly.

Minimal repro attached (`genesis_finger_position_control.py`): commands close/open via
position (fingers move 0.0 mm, no exception), then +5 N force (fingers open ~80 mm).

Expected: either position control works on approximated joints, or the call (or at
minimum `get_dofs_kp`) reports that it cannot.

## 2. Failed `stop_recording(save_to_filename=...)` still writes a video elsewhere

**Title:** `Camera.stop_recording` rejects `save_to_filename` with TypeError but still flushes the video under an auto-generated name

**Body:**
Genesis 1.3.1. `Camera.stop_recording()` does not accept `save_to_filename`; calling it
with one raises `TypeError` — reasonable. But the recording is still written during
teardown, named after the entry-point module: for `python -m pkg.mod` that is literally
`<frozen runpy>_cam_0_<timestamp>.mp4`, in the current working directory.

So a caller whose save *failed with an exception* silently gets a video they did not
name, in a directory they did not choose, with angle brackets in the filename. A caller
that handles the TypeError never learns the file exists.

Minimal repro attached (`genesis_stop_recording_side_effect.py`).

Expected: either accept the keyword, or a failed call leaves no artifact.

## 3. No per-environment fault isolation under batched simulation

**Title:** One environment's constraint NaN raises for the whole batched scene — no way to quarantine or identify the failing environment

**Body:**
Genesis 1.3.1, `scene.build(n_envs=N)` on `gs.amdgpu`. When any single environment's
rigid solver produces invalid constraint forces, `scene.step()` raises
`GenesisException: Invalid constraint forces causing 'nan'` for the entire scene. At
n_envs=4096 one bad contact configuration destroys 4,095 healthy rollouts, and the
exception carries no environment index, so the failing rollout cannot even be identified
for exclusion or analysis.

Observed repeatedly in a contact-rich manipulation batch (16-link cable + Franka,
16–64 envs): a single environment's gripper/floor/cable interaction goes non-finite and
the full batch dies mid-step. Our workaround records the whole batch as failed-unstable
and salvages already-finished episodes, but per-env quarantine (or an errno per env)
would make large-batch evaluation far more robust.

Happy to provide the full scene setup; the failure is contact-dependent so the repro is
statistical rather than deterministic (which is itself part of the report: on this
stack, contact rollouts are not bit-reproducible even from bit-identical resets).
