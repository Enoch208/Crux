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

**Status:** PASSED — measured 2026-08-04 20:56 UTC

`crux.simulation.gate3_batch_probe`, 300 measured steps after 20 warmup, full task scene
(16-link cable URDF + Franka MJCF) on one Radeon PRO W7900. **Two independent runs**, both
reported — the probe was executed twice and the numbers differ by up to 11%, so quoting a
single figure would overstate precision:

| `n_envs` | run 1 env-steps/s | run 2 env-steps/s | spread |
|---:|---:|---:|---:|
| 1 | 344.5 | 340.0 | 1.3% |
| 64 | 19,524.6 | 18,730.1 | 4.1% |
| 256 | 75,870.6 | 67,480.3 | 11.1% |
| 1024 | 219,226.9 | 201,691.2 | 8.0% |
| 4096 | 293,288.8 | (run truncated) | — |

**Headline, stated conservatively: ~200,000–293,000 environment-steps per second on a
single Radeon**, against 344 for a single environment — roughly 590x to 851x. Per-environment
cost is essentially flat to 256 environments, degrades moderately at 1024, and falls to
~54–68 FPS at 4096, so 4096 maximises total throughput while 256–1024 is the efficient band.
Run-to-run spread is real and is reported rather than resolved by picking the better run.

Batched API surface confirmed by `crux.simulation.gate3_api_probe`: `get_links_pos` returns
`(n_envs, 16, 3)`, `get_qpos` returns `(n_envs, 9)`, `control_dofs_position` and `set_qpos`
accept `envs_idx`, `scene.reset(envs_idx=[0, 2])` is accepted, and `inverse_kinematics`
takes `envs_idx` with per-environment targets — as tensors, not Python lists, which is what
`'list' object has no attribute 'shape'` was telling us.

**Why this matters beyond the throughput number.** The held-out qualification returned
0/20 vs 0/20 with Wilson intervals spanning [0, 16]% — underpowered to detect any real
effect. Batching converts the same wall-clock into hundreds of matched pairs, so the
release gate's verdict starts carrying statistical weight instead of describing noise.

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

**Round 7 — the regrasp wall diagnosed, not tuned.** Six rounds of knob candidates
(`longer-quiet`, `shallower-settle`, `reaim-pinch`, `skip-mid-regrip`, `regrip-forward`)
failed to clear `MISSED_GRASP` at the mid-task regrip, which stayed pinned at 0.2–0.8 mm —
fully closed on air. The cause was already in the evidence, in a `CLIP_2_MISSED` link dump:

```
cable links mm: ... (459,58,34) (460,82,40) (458,106,45) (456,131,48) ...
                                   index 12 ──────────────┘  z = 48 mm
```

After threading, the grasp link hangs ~48 mm off the floor, suspended between the posts.
`grasp_link` descended to `cable.radius_m` = 4 mm — correct for the initial grasp on a
settled floor-lying cable (6/6 success) and wrong for every mid-task regrip, driving the
open fingers ~44 mm past the strand before closing. No scalar knob could express the fix
because the defect is in the approach geometry, not in a magnitude.

`grasp_at_link_height` now targets `max(radius, measured link z)` and is proposed first for
`MISSED_GRASP` at both regrip stages. `baseline-v1` keeps it at 0, so the frozen reference
is unchanged and the fix must be earned by the search.

## Gate 4 addendum — determinism MEASURED, earlier PASSED claim corrected

**Measured 2026-08-04 18:45 UTC** by `crux.simulation.gate4_determinism`, seed 101, 3 trials:

| Horizon | Result |
|---|---|
| Reset only | **bit-exact** (`reset is bit-exact: True`) |
| Full controlled episode, final cable state | **diverges**: max deviation vs trial 1 = `3.430e-03 m`, `2.560e-01 m` |
| Identical `(reason_code, task_stage)` across trials | **False** |

**Correction.** Gate 4 was recorded as PASSED on a single `MATCH`. That was over-claimed.
The truth is narrower: *reset is bit-exact; contact-rich rollouts are not reproducible on
this AMDGPU stack.* From an identical starting state, the same controller produced different
failures and a final cable state up to 256 mm apart — consistent with non-deterministic
atomic ordering in the parallel contact solver, not with anything in our reset path.

**Consequence, stated plainly: every single-episode baseline-vs-repair comparison in the
Gate 5 search is confounded.** A candidate that "advanced a stage" may have been sampling
noise. The physically-argued repairs (`short-dangle-regrasp`, `grasp-at-height`) are not
invalidated — their mechanism is independently established — but no repair claim can rest
on one episode. Gate 5 stands as a *search that generates named, mechanistically-justified
candidates*; the evidence that any of them works has to come from Gate 6.

Gate 1's bit-exact reset result stands unchanged and is now properly scoped to static settle.

## Gate 6 — Qualification

**Status:** MECHANISM READY, awaiting run

`crux.simulation.gate6_qualify` runs a matched held-out comparison:

- **20 held-out seeds (201–220)**, asserted disjoint from the repair-selection seeds
  (101–106) via `assert_heldout_uncontaminated` — the suite fails loudly on contamination.
- Both arms run the **same seed and the same environment parameters**; `pair_records`
  re-derives `conditions_key` per arm and refuses to compare if they differ.
- **Primary endpoint**: task success, Wilson 95% CI, exact McNemar on discordant pairs.
- **Secondary endpoint**: reaching `VERIFY_SEATED` or later, same statistics, plus mean
  stage progress. This exists because both arms are expected near 0% success, where the
  primary endpoint is uninformative; depth of progress is the honest measurable difference.

Repaired arm is `baseline-v1 + grasp-at-height + short-dangle-regrasp`, chosen because both
have a stated physical mechanism rather than a single lucky episode.

### Run 1 result — NEGATIVE, 2026-08-04 19:04 UTC

20 held-out seeds (201–220), 40 episodes, `evidence-dev/qualification_heldout.jsonl`.

| Measure | `baseline-v1` | `repaired-v1` | Delta | p |
|---|---|---|---|---|
| Success | 0/20 (0.0%), Wilson [0.0, 16.1]% | 0/20 (0.0%), Wilson [0.0, 16.1]% | +0.0 pp | 1.0000 |
| Reached `VERIFY_SEATED` | 4/20, Wilson [8.1, 41.6]% | 1/20, Wilson [0.9, 23.6]% | **−15.0 pp** | 0.3750 |
| Mean stage progress | 0.655 | 0.570 | −0.085 | — |
| `MISSED_GRASP` episodes | 7 | 11 | +4 | — |

Baseline reason codes: `OVER_TENSION 1, CABLE_SLIP 6, MISSED_GRASP 7, CONNECTOR_MISALIGNED 4,
TIMEOUT 2`. Repaired: `OVER_TENSION 2, CABLE_SLIP 5, MISSED_GRASP 11, CONNECTOR_MISALIGNED 1,
TIMEOUT 1`.

**The repair chain shows no benefit on held-out conditions and trends worse.** With 5
discordant pairs and p = 0.375 the honest statement is *no evidence of improvement, weak and
non-significant signal of harm* — not "the repair makes it worse". The stage advances the
Gate 5 search measured on seeds 101–106 did not generalize, which is the outcome the
held-out suite exists to detect. Reported as measured; nothing here is re-run to look better.

### Two confounds identified, both being measured rather than assumed

**1. Bundled repairs cannot be attributed.** `grasp-at-height` and `short-dangle-regrasp`
were applied together. `crux.simulation.gate5_ablate` runs four arms (baseline, each repair
alone, both) across 12 dev seeds — **on dev seeds, never on the held-out suite**, so that
selecting a winner does not contaminate the confirmatory comparison.

**2. `MISSED_GRASP` may be a verifier artifact for end links.** The last repaired episode
failed with `pinch gap 3.8 mm on link 14 outside [4, 20] mm`. Measured reference values from
this project: closed-on-air reads **0.2–1.5 mm**; holding cable reads **4.3–5.9 mm**. 3.8 mm
sits well above the air band — consistent with a firm grip compressing an 8 mm cable on a
lightly-supported end link, not with a miss. `short-dangle-regrasp` targets link 14
specifically, so it may be systematically tripping a threshold calibrated on mid-cable
grasps, inflating exactly the failure family where it lost.

The `MISSED_GRASP` message now also reports the held link's contact force. Near-zero force
with a sub-threshold gap means a genuine miss; substantial force means the verifier is
rejecting a real grasp and `pinch_min_m` is mis-calibrated. That evidence decides whether
the threshold changes — for **both** arms, with a re-run and re-freeze, never for one.


## Gate 7 — Submission evidence

**Status:** NOT STARTED


## Capability campaign — CLOSED 2026-08-05, 11 matched sweep rounds, 0 successes

**Stopping rule declared in advance and honored: round 11 was the last capability round.**
Roughly 300 batched episodes across 11 sweeps isolated six distinct failure mechanisms,
each by a matched experiment, each with the falsified alternative recorded:

| # | Mechanism | Established by | Countermeasure |
|---|---|---|---|
| 1 | Grip force does not limit routing slip (-28 to -72 N identical) | sweep 1, 8 | none needed |
| 2 | Transport speed does not limit routing slip (0.06-0.60 m/s identical) | sweep 2 | none needed |
| 3 | Diagonal transport wedges the strand at the gate below post tops | instrumented episode: link pinned at z 35 mm, tip at 29 mm | lift-then-translate (fixed; frontier moved 5/11 -> 11/11) |
| 4 | Release recoil flings a dangling connector 50-80 mm | offset narration: (-3,-1) pre-release -> (-55,-17) post | tip-hold grip (recoil eliminated: offset stable through release) |
| 5 | The pinch slides axially under two-gate drag; corrections read converged while the cable stays | seat push: hand +23 mm, connector -3 mm | -56 N clamp (alignment reached sub-mm for the first time) |
| 6 | The open gripper (~20 mm span) cannot pass the 24 mm channel walls; every gripped push stalls at exactly -22 mm | force ladder -44/-56/-72 all stall at the same line | mouth entry + fingertip nudge (round 11: nudge displaced the free head; creep from unregripped transport reasserted upstream) |

Terminal state: alignment 1-3 mm (solved), depth 4-8 mm (solved), but the six
countermeasures cannot all be applied at once — creep demands regrips, regrips miss,
clamping fixes slide but the gripper cannot enter the channel, and the free head is
displaced by the pusher that must seat it. **The residual failure is a geometric
incompatibility between this parallel-jaw gripper and this channel, not a parameter.**

**Retention disclosure:** the sweep runner overwrote `knob_sweep.jsonl` each round, so
only round 11's raw episodes survive as records; rounds 1-10 exist as per-arm summaries
and console transcripts only. That violates our own retain-everything rule and is
recorded here as a process error. The qualification suites (`qualification_standard`,
`qualification_powered`) — the basis of every statistical claim — are fully retained
and shipped in the bundle.

The campaign is itself the primary demonstration of the CRUX loop: failure -> matched
batched experiment -> named mechanism -> targeted repair -> next failure, at ~4 minutes
per cycle on one Radeon versus ~2 hours single-environment.


## Gate 6 — Qualification, POWERED RESULT 2026-08-05 23:36 UTC

`crux.simulation.gate10_qualify`: 64 environments in one batched scene, `baseline-v1` vs
`candidate-v2` on 32 fresh held-out seeds each (301-332), asserted disjoint from every
sweep-selection seed, matched conditions per pair. 93.1 s wall-clock (6,599 env-steps/s).

| Endpoint | `baseline-v1` | `candidate-v2` | Delta | Exact McNemar |
|---|---|---|---|---|
| Task success | 0/32, Wilson [0.0, 10.7]% | 0/32, Wilson [0.0, 10.7]% | +0.0 pp | — |
| Reached `VERIFY_SEATED` | **0/32** [0.0, 10.7]% | **12/32** [22.9, 54.7]% | **+37.5 pp** | **p = 0.0005** |
| Mean stage progress | 0.675 | 0.759 | +0.084 | — |

Failure codes — baseline: `MISSED_GRASP 23, CABLE_SLIP 9` (never past routing/regrasp).
Candidate: `MISSED_GRASP 17, CONNECTOR_MISALIGNED 10, INCOMPLETE_INSERTION 2, CABLE_SLIP 3`
— the distribution moved to the endgame, including two episodes that achieved sub-10 mm
lateral alignment on unseen conditions.

**Claim, stated exactly:** the repair chain selected by the batched discovery campaign
(`drag 0.30 m/s + lift-transport + tip-hold + -56 N clamp + precise align + grasp-at-height`)
raises seating-stage arrival from 0% to 37.5% on held-out conditions with p = 0.0005.
Task success remains 0% for both controllers and is reported as such; the terminal
gripper-channel geometric incompatibility is documented in the campaign closure above.

`candidate-v2` is FROZEN as the overrides listed in `gate10_qualify.CANDIDATE_OVERRIDES`.
Raw episodes: `evidence-dev/qualification_powered.jsonl` (64 records).


## Gate 6 addendum — standard-suite replication and the release-gate verdict (2026-08-05 23:57 UTC)

Standard suite (`gate12_standard`, selection-era seeds 101-132, 64 envs, 116.7 s):
baseline 1/32 vs candidate 9/32 reached seating — **+25.0 pp, exact McNemar p = 0.0215**.
Together with the held-out +37.5 pp (p = 0.0005), the effect replicates across two
independent 64-episode suites, with the held-out effect the larger of the two.

**Release gate: REJECTED**, and recorded as such. The gate's primary endpoint is task
success, which is 0/32 for both arms, so `NO_IMPROVEMENT_DEMONSTRATED` fires exactly as
configured. The seating-stage improvement is a secondary-endpoint finding and is always
labelled as one. The gate refusing to certify our own headline candidate is the system
working as designed.

## Gate 7 — Submission evidence: bundle BUILT and VALIDATED

`crux bundle` assembled `evidence/` (per-arm episode files, configs, `candidate-v2`
spec, Radeon device evidence, two full-pipeline replay videos) and `crux validate`
passed **9/9 checks**, including recomputation of the receipt's aggregate counts and
the standard-suite regression from the raw episode files. Run `crux-final-1` at the
recorded commit.

## Gate 7 addendum — matched-pair renders and a live replication of the non-reproducibility finding (2026-08-06)

Rendering matched pairs on the current scene (`gate11_render`, 1 env + camera) produced
a direct, on-camera confirmation of the Gate 4 finding that contact rollouts are not
reproducible on this stack:

| Seed | Arm | Qualification outcome (64-env scene) | Render outcome (1-env scene) |
|---|---|---|---|
| 301 | baseline-v1 | MISSED_GRASP at VERIFY_CLIP_2 | MISSED_GRASP at VERIFY_CLIP_2 (match) |
| 313 | baseline-v1 | CABLE_SLIP at ROUTE_CLIP_2 | CABLE_SLIP at ROUTE_CLIP_2 (match) |
| 301 | candidate-v2 | INCOMPLETE_INSERTION at VERIFY_SEATED | MISSED_GRASP at VERIFY_CLIP_1 (diverged, 2 attempts) |
| 313 | candidate-v2 | CONNECTOR_MISALIGNED at VERIFY_SEATED | MISSED_GRASP at VERIFY_CLIP_2 (diverged) |

The baseline's early failures reproduce exactly; the candidate's long contact-rich
trajectories diverge. Consequence, applied: demo renders are fresh rollouts sampled
across the qualification's 12 seating-arrival seeds, never presented as replays of
recorded episodes. Fresh-rollout tally: **2/7 renders reached VERIFY_SEATED**
(seed 303: INCOMPLETE_INSERTION, seed 312: CONNECTOR_MISALIGNED), consistent with the
suite rate of 12/32. All 7 clips retained in `evidence-dev/render/`, including the
five failures.

## Upstream contribution — three Genesis issues filed (2026-08-06)

Dup-checked against the upstream tracker, then filed with verbatim console logs from the
box (Ubuntu 24.04.4 LTS, ROCm 7.2.1, Genesis 1.3.1, `gs.amdgpu`), each with a minimal
reproduction from `upstream/`:

1. [genesis-world#3177](https://github.com/Genesis-Embodied-AI/genesis-world/issues/3177)
   — `control_dofs_position` silent no-op on tendon-approximated finger joints
   (repro output: position 0.0 mm over 400 steps, force +5 N opens 80.8 mm).
2. [genesis-world#3178](https://github.com/Genesis-Embodied-AI/genesis-world/issues/3178)
   — failed `stop_recording(save_to_filename=...)` still writes
   `<frozen runpy>_cam_0_*.mp4` to the working directory.
3. [genesis-world#3179](https://github.com/Genesis-Embodied-AI/genesis-world/issues/3179)
   — one env's constraint NaN kills the whole batched scene; no failing-env index.

## Gate 14 — regrasp post-mortem: the mechanism behind 18/32 MISSED_GRASP (2026-08-06)

Instrumented run of candidate-v2 on all 32 selection seeds with full note retention
(`evidence-dev/regrasp_postmortem.jsonl`). Findings:

- **18/32 episodes die at a routing regrip** (8 at the mid regrip on link 12, 10 at the
  connector regrip on link 15), every one with pinch gap 0.3-3.3 mm — the fingers close
  fully past the 4 mm minimum, i.e. the link is not between them at closing time.
- **Instrumentation correction:** the abort message's "link contact 0.00 N" was an
  artifact — `held_link_contact_n` reads the *held* link, which is None during any
  grasp attempt, so the field is definitionally zero there. The message no longer
  prints it. The gap values and render frames carry the diagnosis on their own.
- Frame review of the failed renders (seeds 304, 305) shows the regrip descent landing
  where the cable crosses the gate hardware (link 12) and at the connector tip where
  link origin and cable end diverge (link 15).
- One candidate-v2 close = one chance: the policy had no retry. `grasp_attempts` is now
  a knob (default 1 = v2 behaviour, CPU-tested: a retry recovers a transient miss).

Wide-scene note (gate 13): outcomes in the env-spaced 16-env recording scene regress
systematically (10/16 initial-grasp failures on seeds that pass in the standard scene) —
consistent with the documented scene-build sensitivity. Wide-shot footage is used for
visualisation only and never for metrics; its telemetry sampled the GPU between step
batches (reading 0% busy) and is superseded by the in-flight sampler in gate 15.

## Gate 15 — candidate-v3 selection: two matched sweep rounds (2026-08-06)

Round 1 (4 arms x 32 selection seeds, 128 envs, 97 s): retries cut regrip misses
14 -> 5 and eliminated the mid-regrip failure class entirely (8 -> 0); both
regrip-link-move arms regressed badly (moving off the connector link un-fixes the
release-recoil mechanism). Round 2 (2 arms x 32, 104 s): `v3-retry` seated 16/32
with 2 regrip misses; the tip-pinch-bias arm (12 mm outward) collapsed to 2/32 —
**hypothesis falsified and retained** (`v3_selection_sweep_r2.jsonl`).

**FROZEN: candidate-v3 = candidate-v2 + `grasp_attempts = 3`** (the only change).
Selection-era seating across runs: v2 9-10/32 vs v3 12-16/32. The 5 persistent
connector-regrip misses and the CONNECTOR_MISALIGNED endgame remain the open failure
budget. Telemetry under live sweep load: GPU busy 97-100% in 10+ samples
(`telemetry_sweep*.log`), replacing the between-steps 0% artifact from gate 13.

Qualification for v3 uses virgin seeds 401-432 (asserted disjoint from 101-132 and
301-332 in `gate16_qualify_v3`); 301-332 remains candidate-v2's evaluation suite.

## Gate 16 — candidate-v3 qualification on virgin seeds 401-432 (2026-08-06)

96 matched episodes (3 arms x 32 seeds), 88.2 s, 8,784 env-steps/s with live control.
Seeds 401-432 asserted disjoint in code from 101-132 and 301-332 before the run.

| Comparison | Reached VERIFY_SEATED | Delta | Exact McNemar |
|---|---|---|---|
| baseline-v1 vs candidate-v3 | 0/32 vs **17/32** [36.4, 69.1]% | **+53.1 pp** | **p = 1.5e-05** |
| candidate-v2 vs candidate-v3 | 8/32 vs 17/32 | +28.1 pp | p = 0.0225 |
| baseline-v1 vs candidate-v2 | 0/32 vs 8/32 | +25.0 pp | p = 0.0078 |

Mean stage progress 0.628 / 0.688 / 0.819. Task success 0/32 for all arms. MISSED_GRASP
across arms: 19 -> 18 -> 3 — the retry repair generalised to unseen conditions. The
baseline-vs-v2 effect now replicates on a third independent seed range (3-for-3).
v3's failure mass moved to the endgame: CONNECTOR_MISALIGNED 17, CABLE_SLIP 9.
Raw episodes: `evidence-dev/qualification_v3.jsonl` (96 records, retained).

**candidate-v3 is the headline candidate.** Report and README updated to the measured
numbers; bundle rebuild (v3 standard suite + spec + replays) queued as gate 17.

## Gate 17 — v3 standard suite, bundle rebuild, revalidation (2026-08-06)

Standard suite (seeds 101-132, 64 matched episodes): baseline-v1 0/32 vs candidate-v3
**11/32** reached seating — **+34.4 pp, exact McNemar p = 0.0010**. v3 therefore
replicates independently on both of its suites (virgin +53.1 pp, standard +34.4 pp).
Baseline failure mass: MISSED_GRASP 24, CABLE_SLIP 8; v3 moved to the endgame:
CONNECTOR_MISALIGNED 10, CABLE_SLIP 11, MISSED_GRASP 6, CLIP_2_MISSED 4.

Bundle **crux-final-2** rebuilt at commit dd1d1bc: heldout = virgin 401-432
(baseline vs v3), standard = 101-132 (baseline vs v3), controller spec =
`candidate_v3.json` (v2 + grasp_attempts = 3, frozen), replays = the seed-402 and
seed-403 seating episodes (fresh rollouts, labelled as such). Release gate:
**REJECTED** (primary endpoint task success 0/32 — recorded, not hidden).
`crux validate evidence/manifest.json` -> **9/9 checks passed**. Superseded v2
replays removed from the working tree; the full crux-final-1 bundle remains in git
history. Renders: 2/2 fresh rollouts reached seating on camera, including the
project's first same-seed matched pair (seed 402: baseline MISSED_GRASP at
VERIFY_CLIP_2 vs v3 CONNECTOR_MISALIGNED at VERIFY_SEATED).

## Final clean-clone dry-run at the v3 state (2026-08-06)

Fresh `git clone` from GitHub at 1740cd1, judge path executed verbatim:
`uv sync` exit 0; `uv run pytest` **207 passed** (3.3 s); `uv run crux validate
evidence/manifest.json` **9/9 checks passed**; demo video present and probes at
209.1 s / 18.6 MB; all relative links in README, report, gate log and ISSUES.md
resolve (0 broken). One defect found and fixed: the README's `crux report` example
was a non-runnable placeholder — replaced with the exact command, verified in the
clone to reproduce +34.4 pp (p = 0.0010) and +53.1 pp from raw JSONL.

## Gate 15 addendum — the seating endgame is pusher-limited; success campaign closed (2026-08-06)

Three further matched sweep rounds (r3-r5, 384 episodes, seeds 101-132) attacked the
CONNECTOR_MISALIGNED endgame. Findings, all with retained records:

- The dormant `nudge_seat` fingertip push was enabled and instrumented: it moves the
  connector but stalls at ~13 mm lateral — **identically at a commanded stop-short of
  6 mm, 1 mm, and 0 mm** (r3/r4). The stall is a physical collision of the finger
  assembly with the socket structure, not a targeting choice.
- Re-observed second rounds add ~0 mm and occasionally eject the connector (5 episodes
  worsened to 40+ mm).
- A 0.6 m/s momentum stroke (r5 `v4-fast`): 0 successes.
- A 90° cross-grip wrist rotation (r5 `v4-cross`): 0 successes (seated 18/32, best of
  round, within run-variance of v3's 13-17).
- The combination (r5 `v4-cross-fast`): regressed (12/32 seated, 8 regrip misses).

**Stop rule applied as pre-stated: candidate-v3 is FINAL.** Task success remains 0/32
for every arm ever tested; the seating threshold (lateral < 10 mm) sits ~3.5 mm beyond
the measured pusher stall, and four physically distinct fix families are falsified.
Mechanism 8 ships as a documented limitation with matched-experiment receipts.
Campaign totals: 16 matched sweep rounds + 1 instrumented post-mortem, ~900 batched
episodes, 8 mechanisms isolated.

## Gate 18 — the success metric was geometrically unsatisfiable; corrected and re-qualified (2026-08-06)

The tow round (r6) completed the convergence: five physically independent seating
methods (gripped push, fingertip nudge at three depths, momentum stroke, cross-grip,
cable tow) all stalled at 12.0-13.4 mm origin-lateral, with the tow adding OVER_TENSION
against a hard stop. The invariant equals the scene geometry exactly: back wall inner
face at socket_y + 12 mm, connector segment 25 mm, so a fully seated connector's link
origin sits 13.0 mm from the socket centre — outside the 10 mm tolerance. **The old
metric measured the trailing joint of a 25 mm connector; task success was impossible
by construction, for every controller, from day one.** Same origin-vs-body bug class
as the corrected grasp targeting; discovered by the falsification campaign
triangulating its own spec.

Fix: `seat_metrics` now measures the connector body centre; the 10 mm / 18 mm
thresholds are unchanged; a CPU test pins the impossibility proof
(`test_the_origin_seat_metric_was_geometrically_unsatisfiable`) and a calibration test
confirms a seated body passes and a 20 mm-out body fails. Old episode files retained
under the old run IDs.

Re-qualification under the corrected metric (fresh rollouts, runs dev-qualify-4*):

| Suite | Endpoint | baseline-v1 | candidate-v2 | candidate-v3 |
|---|---|---|---|---|
| virgin 401-432 | success | 0/32 | 1/32 | 1/32 |
| virgin 401-432 | reached seating | 0/32 | 9/32 | **12/32 (+37.5 pp, p = 0.0005)** |
| standard 101-132 | success | 0/32 | — | 1/32 |
| standard 101-132 | reached seating | 0/32 | — | **12/32 (+37.5 pp, p = 0.0005)** |

The first completed episodes in the project's history: v2 seed 413, v3 seeds 428 and
114 — three successes, reported as statistically indistinguishable from zero
(Wilson [0.6, 15.7]%).

**RETRACTION:** the v3-over-v2 increment previously reported as significant
(+28.1 pp, p = 0.0225, old-metric run) did not replicate under re-qualification
(+9.4 pp, p = 0.58). The increment claim is withdrawn; v3's retained, replicated
effect is the MISSED_GRASP mechanism repair (v2 19 vs v3 6 on the virgin suite).

## Gate 18 addendum — bundle crux-final-3: the first APPROVED (2026-08-06)

Bundle rebuilt from the corrected-metric suites (heldout = virgin 401-432, standard =
101-132, baseline-v1 vs candidate-v3, replays retained). `crux validate` -> **9/9
checks passed**. Release gate: **APPROVED** — the first approval in the project's
history — on its pre-registered rule: generalization improvement +3.1 pp on the
primary endpoint (success 0/32 -> 1/32), standard regression -3.1 pp (the candidate is
better there too), additional standard failures -1, small-sample rule applied. Stated
plainly alongside it: the success difference alone is not statistically significant;
the approval is the configured decision rule operating on real evidence, exactly as it
refused to do for repaired-v1 and for every candidate scored under the broken metric.

## Final clean-clone dry-run at the approved-era state (2026-08-06)

Fresh clone at ce87069, full judge path: `uv sync` exit 0; **212 tests passed**;
`crux validate` **9/9**; `crux report` on the corrected-metric suites prints
**Release gate: APPROVED** and every headline number from raw JSONL; demo video
present (3:40, ends on the uncut seed-428 SUCCESS); 0 broken relative links; the
public evidence page (https://enoch208.github.io/Crux/) is live and serving the same
numbers. Judge-UX package complete: evidence page, one-page poster (docs/poster.pdf),
architecture diagram in the README, follow-up engagement posted on upstream #3178.

## History note — tooling co-author trailers removed (2026-08-06)

Four early commit messages carried `Co-authored-by: Cursor` tooling trailers,
predating the project's no-trailer rule. The trailers were stripped with a
message-only rewrite (`git filter-branch --msg-filter`): commit contents, authorship
and order are unchanged; the author list is and was solely Enoch208. Because the
rewrite renames descendant commit ids, SHAs quoted in earlier entries refer to the
pre-rewrite history; the evidence bundle was rebuilt as **crux-final-5** at the
post-rewrite HEAD and `crux validate` passed **9/9**.

## Gate 19 — corrected-metric endgame post-mortem, and a stale-instrument bug it exposed (2026-08-06)

Instrumented run of candidate-v3 on the 32 selection seeds under the corrected seat
metric. The printed structured field disagreed with the verdicts (a seed at 9.35 mm
coded CONNECTOR_MISALIGNED, one at 24.34 mm coded SUCCESS), which exposed a real
instrumentation bug: `run()` recomputed the seat metrics from *its own* last
observation, which is stale by the time a delegated stage (`insert`) has consumed
newer ones. **Verdicts, reason codes and every qualification number were unaffected**
— they come from the in-place decision inside `finish_seated`, and the metrics fields
were never part of `EpisodeRecord` or the evidence bundle. Fixed: `finish_seated`
stores the exact metrics its judgement used and `run()` reports those; a CPU test now
asserts the reported metrics agree with the verdict and with the narrated note.

True endgame distribution (recovered from the decision notes, tolerance 10.0 mm):

| Band | Episodes |
|---|---|
| inside tolerance (SUCCESS) | 2 |
| 10-12 mm (within 2 mm) | 4 |
| 12-15 mm | 8 |
| >= 15 mm | 3 |
| reached the endgame at all | 17/32 |

Consequence: the endgame is a **1.5-4 mm alignment problem**, not a wall — four
episodes sit within 2 mm of tolerance and eight more within 5 mm. Success is
limited by residual alignment error, and the fixture's 24 mm channel is the geometry
that error is measured against, which motivates the design sweep (gate 20).
