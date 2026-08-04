# Acceptance Gates (PRD §29)

Each gate is recorded the moment it passes, with the raw evidence that justified it.

## Gate 0 — Hardware

**Status:** PASSED — 2026-08-04 12:16 UTC

| Requirement | Evidence |
|---|---|
| Radeon GPU visible | `rocm-smi`: GPU[0] AMD Radeon Graphics, model `0x744b`, GFX version `gfx1100` |
| VRAM | 51,522,830,336 B (47.98 GB) |
| ROCm operational | `/opt/rocm/.info/version` → `7.2.1` |
| PyTorch on Radeon | `torch 2.13.0+rocm7.2`, `torch.version.hip = 7.2.53211`, `torch.version.cuda = None`, device `AMD Radeon Graphics` |
| Genesis resolves to `gs.amdgpu` | `Running on [AMD Radeon Graphics] with backend gs.amdgpu. Device memory: 47.98 GB.` |
| Genesis version | 1.3.1 (quadrants 1.2.0) |
| No core-stage CPU fallback | Genesis reported the amdgpu backend directly; no fallback warning emitted |

Host: `u-11389-f00f5508`, 128 CPU cores, 503 GB RAM, `/workspace` 98 GB local SSD,
`/persistent` 100 GB NFS (SFS Turbo). Environment installed at `/persistent/venv`.

`genesis-world` pulled `nvidia-cuda-nvrtc-cu12` and `nvidia-nvjitlink-cu12` as transitive
dependencies but did not reinstall torch. Verified after the install completed:
`torch.version.cuda` is `None` while `torch.version.hip` is set, so the ROCm build is intact
and the CUDA wheels are inert.

## §11 Cable representation — RESOLVED 2026-08-04

**Decision: Option B, rigid articulated capsule chain.** Option A is not implementable.

Genesis 1.3.1 exposes no one-dimensional deformable primitive. Introspected on the instance:

```text
gs.materials  FEM -> Base, Cloth, Elastic, Muscle
              MPM -> Base, Elastic, ElastoPlastic, Liquid, Muscle, Sand, Snow
              PBD -> Base, Cloth, Elastic, Liquid, Particle
              SF  -> Base, Smoke          <- Stable Fluid, not String/Fiber
              SPH -> Base, Liquid

gs.morphs     Box, Cylinder, Sphere, Mesh, MeshSet, Plane, Primitive,
              Terrain, URDF, MJCF, USD, Drone, Nowhere
```

A `rope|cable|fiber` search across the package returned only matches on the substring in
"p**rope**rties". The PRD's original claim of a "String/Fiber solver" was false for this
version and has been corrected in §2, §11, §23, §33 and §35.

Consequence for claims: the cable is an articulated multi-body chain, never a soft or
deformable body. Every judge-facing statement about cable behavior carries that disclosure.

## Gate 1 — Physical scene

**Status:** PASSED (one row deferred to Gate 2) — 2026-08-04 15:09 UTC

Cable dynamics tuning: initial `bend_damping 0.002` left the chain sloshing at
0.03–0.08 m/s after 30 s sim (energy decaying but far too slowly for a jacketed cable).
Raised 10× (`bend 0.02, twist 0.04, friction 0.002`); the chain then settled to
0.0028 m/s in 30 s with an unchanged static rest shape (~500 mm spread both before and
after), confirming the damping change affects settling speed only. Max joint angle
0.543 rad against the 0.5236 rad limit — ~3% soft-constraint overshoot, normal for a
penalty solver.

| Requirement | Status | Evidence |
|---|---|---|
| Cable loads | PASS | 24-link generated URDF loads as `RigidEntity` on `gs.amdgpu` |
| Reset works | PASS | `scene.reset()` returns to the initial state |
| Fixed-seed replay repeatable | PASS | max deviation `0.000e+00` m over 3 reset/re-settle runs — bit-exact, stronger than §14.5's 4-of-5 tolerance |
| Franka loads | PASS | MJCF `franka_emika_panda/panda.xml`, 11 links / 9 DOF, tendon fingers approximated by joint actuators |
| Cable articulates | PASS | anchored-hang test: joints reach 0.543 rad, height spread 504 mm, settles to 0.0028 m/s in 30 s sim, free end 504 mm below anchor |
| Cable registers contact | PASS | `get_links_net_contact_force` returned 0.1507 N in the floor-contact run |
| Cable interacts with gripper and clips | NOT TESTED | contact mechanics proven against plane/box; gripper- and clip-specific interaction lands with Gate 2 |

Confirmed Genesis 1.3.1 API surface on `RigidEntity`, used by later components:

- `get_links_pos`, `get_links_quat`, `get_links_vel` — cable state export (§14.4)
- `get_qpos` / `set_qpos` / `get_state` — checkpoint capture and restore (§14.5)
- `get_links_net_contact_force` — contact flags, `ROBOT_COLLISION`, tension proxy (§14.4)
- `inverse_kinematics_multilink` — Cartesian control for the baseline (§14.2)
- `control_dofs_position` / `set_dofs_position` — actuation and residual corrections

**Throughput note:** ~300–520 FPS at `n_envs=1`, `dt=0.005`, and drifting downward across
runs. Roughly 5–10 s wall-clock per episode single-environment; §19.1's minimum suites are
660 episodes across both controllers. Batched `n_envs` is therefore load-bearing for Gate 3,
and the FPS drift needs a proper measurement rather than the logger's rolling average.

Kernel compilation cost ~113 s on first build; Genesis caches compiled kernels afterwards.

## Gate 2 — Baseline capability

**Status:** IN PROGRESS — grasp primitive PROVEN 2026-08-04 15:41 UTC

The Franka grasped the 8 mm articulated cable and lifted it 239.6 mm, retaining a
6.5→5.8 mm pinch throughout. Sequence: home → hover → touch-probe the cable top
(hand-to-tip measured **110.6 mm**) → straddle at cable-centre height → force-close
until the gap converges → two-stage lift.

Hard-won findings that shape the baseline controller:

- **Finger actuators are non-PD.** The MJCF tendon approximation leaves DOFs 7–8 with a
  general gain/bias actuator (`act_gain 0.016`, `act_bias [0, -100, -10]`);
  `control_dofs_position` on them is a silent no-op and `get_dofs_kp` raises.
  Fingers must be force-controlled: +5 N/finger opens (80.8 mm gap), −15 N closes.
  Candidate §23 upstream report: position control silently dead on tendon-approximated
  fingers.
- **Fingers close at ~8 mm/s per finger** under 15 N (damping is 1.0, so not damping);
  closing takes ~2.3 s and must run to convergence, not a fixed step count.
- **Pinch verification before lift**: converged gap in [4, 20] mm proves the cable is
  between the pads (closed-on-air reads 1.5 mm; on-cable reads ~6.5 mm). This is the
  physical basis for `VERIFY_GRASP` and for `CABLE_SLIP` detection (gap collapse).
- Touch-probe calibration: descend with closed fingers until cable contact exceeds
  resting baseline (0.018 N) + 0.4 N; hand height at touch minus cable diameter gives
  hand-to-tip against the actual collision meshes.

Remaining for Gate 2: full task scene (clips, socket), routing + insertion stages,
stage verification with reason codes, one complete episode.


## Gate 3 — Parallel evaluation

**Status:** NOT STARTED

## Gate 4 — Failure reproduction

**Status:** NOT STARTED

## Gate 5 — Repair

**Status:** NOT STARTED

## Gate 6 — Qualification

**Status:** NOT STARTED

## Gate 7 — Submission evidence

**Status:** NOT STARTED
