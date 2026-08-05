# CRUX — Failure-Discovery and Qualification for Contact-Rich Manipulation on one AMD Radeon

**Track 3 · Physical AI · AMD AI DevMaster Hackathon 2026**

CRUX is a reliability harness for a contact-rich robot task: a Franka arm routes a
40 cm articulated cable through two clip gates and seats its connector in a channel
retainer, simulated in Genesis 1.3.1 on a single AMD Radeon PRO W7900 (gfx1100,
ROCm 7.2.1, `torch 2.13.0+rocm7.2`, backend `gs.amdgpu`). The system discovers how a
controller fails, isolates the mechanism with matched batched experiments, applies
named repairs, and qualifies the result on held-out conditions with real statistics —
then packages every number in a tamper-evident evidence bundle a judge can verify on
CPU in minutes.

## Headline result

On 32 virgin held-out seeds per arm (401–432, asserted disjoint in code from every
seed any selection experiment ever touched), matched conditions per pair, 96
environments in one batched scene, 114 seconds of wall-clock, under the corrected
seat metric (§4):

| Endpoint | `baseline-v1` | `candidate-v3` | Delta | Exact McNemar |
|---|---|---|---|---|
| Task success | 0/32, Wilson 95% [0.0, 10.7]% | 1/32, [0.6, 15.7]% | +3.1 pp | n.s. |
| Reached seating verification | 0/32, [0.0, 10.7]% | **12/32, [22.9, 54.7]%** | **+37.5 pp** | **p = 0.0005** |
| Mean stage progress (0–1) | 0.650 | 0.766 | +0.116 | — |

**The seating effect replicates exactly.** On the standard suite (seeds 101–132) the
same comparison reads 0/32 vs 12/32 — the identical +37.5 pp at the identical
p = 0.0005 — and earlier qualification runs measured the same comparison at
+25.0 to +53.1 pp across two further seed ranges. `candidate-v3` differs from
`candidate-v2` by exactly one mechanism-backed repair (up to three re-observed grasp
attempts); its replicated effect is on the failure mechanism itself — MISSED_GRASP
19 → 6 on the virgin suite. A v3-over-v2 *seating* increment measured significant in
one earlier run (+28.1 pp, p = 0.0225) **did not replicate** under re-qualification
(+9.4 pp, p = 0.58) and is withdrawn (§4).

The three SUCCESS episodes (v2 seed 413; v3 seeds 428 and 114) are the first
completed end-to-end episodes in the project — and became visible only after the
discovery campaign exposed that the original success metric was geometrically
unsatisfiable (§4). On this evidence the release gate returns **APPROVED** for
`candidate-v3` — its first approval ever, after rejecting `repaired-v1` and rejecting
every candidate scored under the broken metric — on its pre-registered rule: a
generalization improvement on the primary endpoint (+3.1 pp) with zero standard-suite
regression, under the small-sample provision. We state plainly that the success
difference alone (1/32 vs 0/32) is not statistically significant; the approval
reflects the gate's configured decision rule, and both the rule and the raw episodes
ship in the receipt. The seating improvement remains a secondary-endpoint finding,
labelled as one everywhere.

## 1. System

- **Task scene** — 16-link articulated cable (URDF generated from config; Genesis 1.3.1
  has no 1-D deformable — verified by introspection, §5), two clip gates, an open-entry
  channel retainer, Franka MJCF. Everything parametric in `configs/task.yaml`.
- **Controller** — a pure-Python generator policy (`crux.control.policy`) that yields
  one control chunk at a time and receives observations; testable on CPU without a GPU
  (212 tests, 0.4 s). A batch driver runs N independent policies against one batched
  scene: one batched IK call per waypoint change, per-environment knobs, per-environment
  reset, solver explosions recorded as `UNSTABLE_SIMULATION` instead of crashing.
- **Failure taxonomy** — 12 reason codes × 11 task stages, machine-readable episode
  records (JSONL) for every trial ever run, failures never deleted.
- **Repair space** — 24 typed knobs; named repair operators with stated mechanisms;
  a composing search that scores candidates by stage progress.
- **Qualification** — Wilson intervals, exact McNemar on matched pairs, a release gate
  that APPROVES/REJECTS a candidate (it rejected our first one), held-out contamination
  asserted in code.
- **Evidence** — `crux bundle` writes hashed episode files, configs, controller spec,
  device evidence and replays with a manifest + receipt; `crux validate` re-verifies
  all of it on CPU, recomputing headline numbers from raw episodes. Tampering with one
  byte fails the check (tested).

## 2. Radeon / ROCm utilisation

Measured batched throughput on the full task scene (cable + Franka), 300 steps after
warmup, two independent runs both reported (spread up to 11%):

| n_envs | env-steps/s (run 1 / run 2) |
|---:|---:|
| 1 | 344 / 340 |
| 64 | 19,525 / 18,730 |
| 256 | 75,871 / 67,480 |
| 1024 | 219,227 / 201,691 |
| 4096 | 293,289 / (truncated) |

**~200k–293k environment-steps per second on one GPU** — 590–851× the single
environment. The powered qualification (64 envs) ran at 6,599 env-steps/s with live
per-environment control and IK; the same suite single-environment would take >3 hours
instead of 93 s. Sweep cycles ran at ~4 minutes for 32 simultaneous episodes.

## 3. The discovery campaign — 17 matched sweeps + an instrumented post-mortem, 8 mechanisms

Each round eliminated a hypothesis class or isolated a mechanism. Retention disclosure:
the sweep runner overwrote its episode file per round, so raw records survive only for
round 11; earlier rounds are documented as per-arm summaries and transcripts (a process
error, recorded in the gate log). Both qualification suites behind the statistical
claims are fully retained and hash-verified in the bundle.

1. **Grip force is not the routing-slip limit** (−28…−72 N identical outcomes).
2. **Transport speed is not the limit** (0.06–0.60 m/s identical).
3. **Diagonal transport wedges the strand at the gate** — one instrumented episode
   showed the held link pinned at z 35 mm with the grip crossing at 29 mm, below the
   40 mm post tops. Fix: lift-then-translate transport. Frontier moved from stage 5/11
   to 11/11 in one run.
4. **Release recoil** — a dangling connector, aligned to 3 mm, was thrown 50–80 mm by
   the stored bend energy at finger opening. Fix: grip the connector link (offset then
   stable through release).
5. **Axial grip slide** — alignment corrections read converged while the cable slid
   through the pinch (hand +23 mm, connector −3 mm). Fix: −56 N clamp; first sub-mm
   alignment of the project.
6. **Gripper–channel interference** — every gripped push stalls at exactly −22 mm,
   where the ~20 mm open finger span meets the 24 mm channel walls, at every force
   tested. Countered with mouth entry and a closed-fingertip nudge; residual failure
   is geometric, and closed as a documented limitation.
7. **Single-shot regrips close on air** — an instrumented post-mortem retained full
   note trails for all 32 selection episodes: 18 died at a routing regrip with the
   pinch closing to 0.3–3.3 mm on nothing. Two matched sweep rounds showed re-observed
   retries eliminate the mid-route miss entirely (8 → 0) while regrip-link moves and a
   12 mm tip-pinch bias both regressed badly (falsified, records retained). Fix:
   `grasp_attempts = 3` — the only difference between v2 and v3.
8. **The success metric itself was broken — and the campaign proved it.** Five
   physically independent seating methods (gripped push, fingertip nudge at three
   commanded depths, a 0.6 m/s momentum stroke, a 90° cross-grip, and towing the cable
   from behind) all converged on the same 12.0–13.4 mm floor across 512 matched
   episodes, with the tow ending in OVER_TENSION against a hard stop. That invariant
   equals the scene geometry exactly: a fully seated connector's *link origin* sits
   13.0 mm from the socket centre — outside the 10 mm tolerance — because the metric
   measured the trailing joint of a 25 mm connector instead of its body. Task success
   had been impossible by construction for every controller. Fix: measure the
   connector body centre (thresholds unchanged); a CPU test pins the impossibility
   proof so it cannot regress. The residual, real limitation: most endgames still
   stall just outside tolerance — success is 1/32, not 0, and not yet more.

The campaign is the CRUX loop operating as designed: failure → matched batched
experiment → named mechanism → targeted repair → next failure, at ~4 min/cycle.

## 4. Honesty findings (these are results, not caveats)

- **Our own success metric was geometrically unsatisfiable — the harness caught it.**
  The original seat check measured the connector's trailing joint origin against a
  10 mm ball whose best physically achievable value was 13.0 mm (provable from the
  scene constants; pinned as a CPU test). It was discovered not by inspection but by
  falsification: five independent repair families triangulated the same impossible
  floor. This is precisely the class of spec bug that ships broken robots, and
  finding it is the strongest argument in this report for evidence-first robotics.
  All qualification suites were re-run under the corrected metric within the hour;
  the pre-correction records are retained under their original run IDs.
- **A significant result failed to replicate and is withdrawn.** The v3-over-v2
  seating increment measured +28.1 pp (p = 0.0225) in one qualification run and
  +9.4 pp (p = 0.58) under re-qualification. We report the replication failure and
  drop the claim; v3's mechanism-level effect (MISSED_GRASP 19 → 6) is what
  replicates.
- **Contact rollouts are not reproducible on this stack.** Reset is bit-exact
  (0.000e+00 m over 3 cycles); full episodes from identical state diverged up to
  256 mm in final cable position with different failure codes. We had recorded a
  reproduction gate as PASSED on one matching replay — **that claim was retracted**
  and re-scoped once measured. Consequence: no claim in this project rests on a single
  episode; everything judge-facing comes from matched suites.
- **The release gate rejected our first repair.** `repaired-v1` showed no held-out
  improvement (0/20 vs 0/20, seating −15 pp n.s.) and was refused. The negative run
  is in the evidence next to the positive one.
- **A fictional config parameter.** `drag_speed_mps` never governed motion in the
  original controller (it only set dwell time); implementing it faithfully broke
  routing and led to mechanism #3. Config-vs-reality drift is itself a reliability
  failure mode worth reporting.
- **One NaN kills 4,096 environments.** Genesis provides no per-environment quarantine;
  our runner records the blast as per-environment `UNSTABLE_SIMULATION` and salvages
  finished episodes (upstream issue drafted).

## 5. Upstream findings for Genesis (minimal repros in `upstream/`, all filed)

1. `control_dofs_position` on tendon-approximated finger joints silently does nothing,
   while `get_dofs_kp` (the way to detect it) raises. Force control works.
   Filed: [genesis-world#3177](https://github.com/Genesis-Embodied-AI/genesis-world/issues/3177).
2. A `Camera.stop_recording(save_to_filename=...)` call that raises `TypeError` still
   writes the video during teardown under an entry-point-derived name
   (`<frozen runpy>_cam_0_*.mp4`) in the working directory.
   Filed: [genesis-world#3178](https://github.com/Genesis-Embodied-AI/genesis-world/issues/3178).
3. No per-environment fault isolation under batching: one environment's constraint NaN
   raises for the entire scene.
   Filed: [genesis-world#3179](https://github.com/Genesis-Embodied-AI/genesis-world/issues/3179).

## 6. Limitations

- Task success is 1/32 for the best controller — statistically indistinguishable from
  zero, and labelled that way. The endgame is fully mapped (mechanism 8): after the
  metric correction, most episodes still stall with the connector body just outside
  the 10 mm tolerance. v3 turns most failures into near-misses at the seating check,
  which is progress, not success.
- The cable is a rigid articulated chain (Genesis 1.3.1 has no 1-D deformable; the
  PRD's original claim of a String/Fiber solver was corrected against the installed
  package). No sim-to-real claims are made anywhere.
- Simulation non-determinism (§4) bounds what any single-episode analysis can claim
  on this stack; all statistics here are suite-level.
- Batched throughput was measured twice with up to 11% spread; ranges are reported
  rather than best-run figures.

## 7. What CRUX is for — beyond this controller

CRUX is controller-agnostic qualification infrastructure. The policy interface is a
generator that receives observations and yields control chunks — the exact shape of a
VLA or RL policy's action loop — and every downstream stage (failure taxonomy, matched
suites, McNemar qualification, release gate, evidence bundle) is independent of how
the policy computes its actions. The field's bottleneck is not training policies; it
is that nobody can say whether the new checkpoint is safe to promote. CRUX is built to
answer exactly that question, for scripted and learned controllers alike: freeze two
policies, run matched suites on one Radeon, and let the release gate decide on
evidence a reviewer can re-verify on CPU. The scripted controller in this submission
is the first policy the harness qualified — deliberately the simplest one, so every
number in this report is attributable to the harness, not to a model.

## 8. Reproduce / verify

```bash
uv run pytest -q                      # 212 CPU tests, no GPU needed
uv run crux validate evidence/manifest.json   # re-verify the bundle on CPU
uv run crux report evidence-dev/qualification_v3_standard_fixedmetric.jsonl \
  evidence-dev/qualification_v3_fixedmetric.jsonl \
  --baseline-version baseline-v1 --repaired-version candidate-v3 \
  --config configs/qualification.yaml           # every headline number from raw JSONL
# GPU experiments: src/crux/simulation/gate*.py, in gate order, on ROCm
```

Every number in this report is computed from `evidence-dev/*.jsonl` by code in this
repository; none is hand-maintained.
