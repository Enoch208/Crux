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

### Baseline frozen as `baseline-v1` — 2026-08-04 17:07 UTC

**Status: PARTIAL. Every stage has been demonstrated; no single episode has completed
end to end.** This is recorded as a limitation, not smoothed over, and it is disclosed
wherever baseline success rate is reported.

| Stage | Demonstrated | Evidence |
|---|---|---|
| Grasp the cable end | YES, 6/6 in the final run | `holding link 12 (gap 5.9 mm)`, `grasp verified` |
| Thread clip 1 | YES, 6/6 | `[VERIFY_CLIP_1] 1 crossing(s) in gate` |
| Regrasp mid-task | YES | `[VERIFY_CLIP_1] holding link 12 (gap 4.3 mm)` after release + settle |
| Thread clip 2 | YES | `[VERIFY_CLIP_2] 1 crossing(s) in gate` |
| Align over socket | YES | `[ALIGN_CONNECTOR] correction 1: connector offset (+25.0, +25.0) mm` |
| Insert and seat | NO | never reached with a live grasp |

Final baseline run, 6 seeds: `{'CABLE_SLIP': 3, 'MISSED_GRASP': 3}`. An earlier run of the
same controller produced `{'CABLE_SLIP': 1, 'OVER_TENSION': 1, 'INCOMPLETE_INSERTION': 1,
'MISSED_GRASP': 1, 'CLIP_2_MISSED': 2}` — five distinct families including one episode that
ran the whole pipeline and failed only the final seat measurement.

Physical findings behind the two surviving failure modes:

- **`CABLE_SLIP` at `ALIGN_CONNECTOR`.** The controller holds link 12 while the connector is
  link 15, so every alignment correction drags ~75 mm of already-threaded cable. Peak tension
  24–28 N against a 30 N budget, and the pinch walks off the link (35–46 mm from the
  fingertips). Clamping corrections to 25 mm slowed this down but did not remove it: the
  cause is the moment arm, not the step size.
- **`MISSED_GRASP` at the regrasp.** Converged pinch gap 0.8 mm — fully closed on air.
  Adding a 150-step quiet pause after release did not fix it, so the fingers are missing
  laterally rather than arriving early.

**Deliberate stopping point.** Both remaining failures are controller-parameter problems,
and hand-tuning them would make the baseline a product of my own search rather than a fixed
reference. They are instead encoded as the repair search space (`crux.repair.operators`),
where `short-dangle-regrasp` — hold one link from the connector before inserting — is the
first candidate proposed for `CABLE_SLIP@ALIGN_CONNECTOR`. If the search finds it, that is
the system working as designed; if it does not, that is reported as a negative result.

Baseline behavior is frozen: `ControllerKnobs.baseline()` sets `insert_link_from_end ==
grasp_link_from_end`, so `baseline-v1` is byte-identical in behavior to the controller that
produced the runs above, and every repair is expressed as a delta from it.

## Gate 3 — Parallel evaluation

**Status:** NOT STARTED

## Gate 4 — Failure reproduction

**Status:** PASSED (with disclosure) — first confirmed 2026-08-04 17:24 UTC

Seed 101 was run, its failure recorded, then re-run from the same seed and environment
parameters. Console evidence: `failure reproduction (seed 101): MATCH` — identical
`(reason_code, task_stage)` on replay. This upgrades Gate 1's static determinism result
(`0.000e+00` m deviation over 3 reset cycles) to a live failure reproduced end to end
through 4500+ steps of contact-rich manipulation. The replay episode is written to the
episode log tagged `reproduction-check`.

**Disclosure from the composing-search run (17:37 UTC):** the same within-process check
reported `DIVERGED` on a later suite, and seed 101's baseline failure itself shifted from
`CABLE_SLIP@ROUTE_CLIP_1` (round 1) to `MISSED_GRASP@VERIFY_CLIP_1` (round 2) across
process restarts. Gate 1 bit-exact reset remains intact for static settle; contact-rich
episode replay is not guaranteed bit-exact on this AMDGPU stack. Reproduction is therefore
treated as a strong signal when it matches, not as an invariant. Every repair still binds
to the exact seed and environment parameters of the failure it targeted.

## Gate 5 — Repair

**Status:** IN PROGRESS — composing search round 2 run 2026-08-04 17:37 UTC

**Round 1** (binary SUCCESS only): 0 of 6 repaired; discarded a real stage advance on
seed 103. Fix: progress-scored composing search (`crux.repair.search`).

**Round 2 result, reported as measured:**

| Seed | Baseline | Outcome |
|---|---|---|
| 101 | `MISSED_GRASP@VERIFY_CLIP_1` | unrepaired |
| 102 | `CABLE_SLIP@ROUTE_CLIP_1` | advanced to `TIMEOUT@INSERT_CONNECTOR` by `gentle-align` |
| 103 | `MISSED_GRASP@VERIFY_CLIP_1` | unrepaired |
| 104 | `MISSED_GRASP@VERIFY_CLIP_1` | unrepaired |
| 105 | `CABLE_SLIP@ALIGN_CONNECTOR` | advanced to `TIMEOUT@INSERT_CONNECTOR` by `short-dangle-regrasp` |
| 106 | `MISSED_GRASP@VERIFY_CLIP_1` | advanced to `OVER_TENSION@ROUTE_CLIP_2` by `shallower-settle` |

**Thesis confirmed on seed 105.** Holding link 14 instead of link 12 before insertion —
the repair deliberately left out of `baseline-v1` — moved the failure from alignment slip
to a late-stage timeout at `INSERT_CONNECTOR`. That is an attributable, named counterfactual
fix of the dominant insertion failure family. 29 episodes in
`evidence-dev/repair_search.jsonl`.

**Next gap the search exposed:** `TIMEOUT@INSERT_CONNECTOR` does not advance under a
strictly-later-stage rule when a candidate still times out at INSERT. Round 3 adds
`timeout_steps` as a repair knob and stage-specific operators (`more-budget`,
`fewer-corrections`, `faster-late-stage`, `deeper-insert`) so a composed chain like
`short-dangle-regrasp+more-budget` can finish the seating descent. `MAX_ROUNDS` raised to 4.

**Round 3 result, reported as measured (2026-08-04 18:02 UTC):**

| Seed | Outcome |
|---|---|
| 101 | unrepaired `CABLE_SLIP@ROUTE_CLIP_1` |
| 102 | advanced to `CABLE_SLIP@ALIGN_CONNECTOR` by `gentle-align` |
| 103, 104 | unrepaired `MISSED_GRASP@VERIFY_CLIP_1` |
| 105 | advanced to `CONNECTOR_MISALIGNED@VERIFY_SEATED` by `fewer-corrections` |
| 106 | advanced to `CONNECTOR_MISALIGNED@VERIFY_SEATED` by `shallower-settle+longer-quiet+faster-late-stage` |

Gate 4 reproduction MATCH again. Seeds 105 and 106 both reached seating verification —
past INSERT. Observed seating miss on one attempt: lateral 9.1 mm, tip z **47.8 mm**
(socket lip is ~30 mm): the plunge landed on/above the wall, then release left the
connector hanging. `deeper-insert` cannot fix a tip that never entered the aperture.

**Round 4 fix:** seating-metric hill-climb at `VERIFY_SEATED` (strict improvement on
`lateral + depth` counts as progress, since no stage is later except SUCCESS), plus
operators `lower-approach`, `precise-align`, and `tip-hold` aimed at the wall-landing
failure. `insert_carry_z_m` is now a knob; baseline remains 55 mm.

**Round 4 result, reported as measured (2026-08-04 18:21 UTC):**

| Seed | Outcome |
|---|---|
| 101 | advanced to `CONNECTOR_MISALIGNED@VERIFY_SEATED` by `shorter-pull+shallower-settle` |
| 102 | unrepaired `CABLE_SLIP@ROUTE_CLIP_1` |
| 103, 104, 106 | unrepaired `MISSED_GRASP@VERIFY_CLIP_1` |
| 105 | unrepaired `OVER_TENSION@ROUTE_CLIP_2` |

Gate 4 DIVERGED this run. Seed 101 still reached seating under a different baseline
failure (`OVER_TENSION@ROUTE_CLIP_1`), confirming composing works across shifting early
failures. Seeds that previously reached seating (105/106) did not this process —
contact-rich episode outcomes remain non-stationary across restarts. Dominant unrepaired
wall is the regrasp miss (pinch gap 0.3–0.8 mm = closed on air).

**Round 5 fix:** `reaim-pinch` — after hover, settle, re-read link XY/yaw, and correct
laterally at hover and at pinch height before closing. Baseline keeps `reaim_before_pinch=0`
so `baseline-v1` is unchanged. Also stage-specific `CABLE_SLIP@ROUTE_CLIP_1` and
`OVER_TENSION@ROUTE_CLIP_1` operators (firmer/slower/shorter) so early slips are not
fed alignment-only candidates.

**Round 5 result, reported as measured (2026-08-04 18:33 UTC):**

| Seed | Outcome |
|---|---|
| 101, 102 | unrepaired `CABLE_SLIP@ROUTE_CLIP_1` |
| 103, 104, 106 | unrepaired `MISSED_GRASP@VERIFY_CLIP_1` |
| 105 | advanced to `CONNECTOR_MISALIGNED@VERIFY_SEATED` by `faster-late-stage` |

Gate 4 MATCH. `reaim-pinch` did not clear the on-air miss (still 0.2–0.8 mm). Seed 105
again reached seating — the composing path to INSERT/VERIFY is repeatable under the
right early failure. The mid-task regrip itself is the dominant unrepaired mechanism.

**Round 6 fix (last Gate 5 operator pass tonight):** `skip-mid-regrip` and
`regrip-forward` for `MISSED_GRASP@VERIFY_CLIP_1`; seating progress accepts Pareto
improvement (lateral better without depth regression, or vice versa) so wall-to-hole
alignments can climb. After this run, Gate 5 freezes as partial with measured advances
to `VERIFY_SEATED` and we move to Gate 3 (batched `n_envs`).

## Gate 6 — Qualification

**Status:** NOT STARTED

## Gate 7 — Submission evidence

**Status:** NOT STARTED
