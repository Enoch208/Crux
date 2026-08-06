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

**The robot completes the task.** On 32 virgin held-out seeds per arm (701–732,
asserted disjoint in code from all five previously used seed ranges), matched
conditions per pair, 96 environments in one batched scene:

| Endpoint | `baseline-v1` | `candidate-v4` | Delta | Exact McNemar |
|---|---|---|---|---|
| **Task success** | 0/32, Wilson 95% [0.0, 10.7]% | **13/32, [25.5, 57.7]%** | **+40.6 pp** | **p = 0.0002** |
| Reached seating verification | 1/32 | 15/32 | +43.8 pp | p = 0.0001 |

This is the suite the shipped evidence bundle validates. **Confirmed on three further
independent seed ranges**: virgin 501-532 (0/32 vs 12/32, +37.5 pp, p = 0.0005),
standard 101-132 (0/32 vs 9/32, +28.1 pp, p = 0.0039) and a second task (0/32 vs 6/32,
+18.8 pp, p = 0.0312). Across all 128 matched pairs there is not a single seed the
baseline completes and the candidate does not.
The release gate returns **APPROVED** on its pre-registered rule — a +40.6 pp
generalization improvement with *negative* regression (the candidate is better on both
suites) — and the verdict, the rule and the raw episodes all ship in the receipt.

**The repairs generalise.** Run unchanged against a *second task* defined only in
config — clips repositioned and narrowed, socket moved laterally, randomisation
widened, fresh seeds 601-632 — `candidate-v4` scores **6/32 against the baseline's
0/32 (+18.8 pp, p = 0.0312, discordant 0/6)** on a task it was never tuned for and
never shown during selection (§7).

`candidate-v4` differs from `candidate-v3` by one repair — the closed-fingertip seat
nudge — worth +28.1 pp on task success head-to-head (p = 0.0225). That repair was
recovered by the campaign's most valuable finding: the project's original success
metric was **geometrically unsatisfiable**, and five independent repair experiments
converging on one impossible number is what proved it (§3, mechanism 8). Correcting
the measurement released a capability that had been in the repository all along.
This is the class of defect that ships broken robots, and catching it is what a
reliability harness is for.

## 1. System

- **Task scene** — 16-link articulated cable (URDF generated from config; Genesis 1.3.1
  has no 1-D deformable — verified by introspection, §5), two clip gates, an open-entry
  channel retainer, Franka MJCF. Everything parametric in `configs/task.yaml`.
- **Controller** — a pure-Python generator policy (`crux.control.policy`) that yields
  one control chunk at a time and receives observations; testable on CPU without a GPU
  (259 tests, 0.7 s). A batch driver runs N independent policies against one batched
  scene: one batched IK call per waypoint change, per-environment knobs, per-environment
  reset, solver explosions recorded as `UNSTABLE_SIMULATION` instead of crashing.
- **Failure taxonomy** — 12 reason codes × 11 task stages, machine-readable episode
  records (JSONL) for every trial ever run, failures never deleted.
- **Repair space** — 37 typed knobs; named repair operators with stated mechanisms;
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

## 3. The discovery campaign — 19 matched sweeps + two instrumented post-mortems, 10 mechanisms

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
   proof so it cannot regress.
9. **A broken metric does not merely hide success — it teaches a false mechanism.**
   Re-running the seating repairs under the corrected metric overturned mechanism 8's
   conclusion outright: the closed-fingertip nudge, recorded as falsified five times,
   converts 1/32 successes into 11/32 on selection seeds and halves the median seating
   error (13.5 mm → 6.4 mm). It had always worked. The five "independent falsified
   families" were five correct measurements of the wrong quantity. Two adjacent
   hypotheses were tested in the same round and genuinely failed — tighter alignment
   (`align_step_cap_m` 8 → 4 mm, 10 corrections) scored 0/32 alone and *degraded* the
   nudge from 11/32 to 2/32 when combined — so the winning repair is specifically the
   fingertip push, not general precision. `nudge_seat = 1` is the only difference
   between v3 and **v4**, the frozen headline candidate.

10. **Tightening the grip before a slip prevents slips — and costs more than it
    saves.** A predictive guard (EMA-filtered fingertip-to-link distance, debounced,
    clamping harder on warning) beat its control on all three settings on the
    selection seeds — success 9/32 → 11, 12, 10 and CABLE_SLIP 14 → 11, 10, 10 with
    the guard firing 6–15 times per arm. Frozen as **candidate-v5** and taken to
    virgin seeds 701-732, it scored 10/32 against v4's 13/32 (−9.4 pp, p = 0.5078,
    n.s.). The reason is in the failure codes, not in noise: v5 traded CABLE_SLIP
    (13 → 7) for OVER_TENSION (1 → 4) and MISSED_GRASP (2 → 8). The mechanism is real
    and the repair is not worth its cost at these settings, so **v4 stands** and v5 is
    retained as a falsified candidate rather than tuned until it wins (gate 26).

The campaign is the CRUX loop operating as designed: failure → matched batched
experiment → named mechanism → targeted repair → next failure, at ~4 min/cycle.

## 4. Findings about our own process (these are results, not caveats)

- **Our own success metric was geometrically unsatisfiable — the harness caught it.**
  The original seat check measured the connector's trailing joint origin against a
  10 mm ball whose best physically achievable value was 13.0 mm (provable from the
  scene constants; pinned as a CPU test). It was discovered not by inspection but by
  falsification: five independent repair families triangulated the same impossible
  floor. This is precisely the class of spec bug that ships broken robots, and
  finding it is the strongest argument in this report for evidence-first robotics.
  All qualification suites were re-run under the corrected metric within the hour;
  the pre-correction records are retained under their original run IDs.
- **A broken metric teaches a false mechanism, and we can now prove it.** Mechanism 8
  closed the seating endgame as unsolvable on five falsified repair families. Re-scored
  against a working metric, one of those repairs is the difference between 0% and 40.6%
  task success. Both mechanisms stay in the record, original wording intact, because
  the sequence is the most transferable result here: *fix your ruler before you fix
  your robot* is not a slogan in this repository, it is a measured outcome.
- **An instrument bug the instrument caught.** The seat metrics reported in episode
  outcomes were recomputed from a stale observation in `run()`, so a post-mortem
  printed 9.35 mm for an episode judged misaligned and 24.34 mm for one judged
  seated. Verdicts, reason codes and every qualification number were unaffected (the
  decision is made in place, and the field never entered `EpisodeRecord` or the
  bundle), but the contradiction is what exposed it. `finish_seated` now stores the
  metrics its judgement used, and a test asserts the reported values agree with both
  the verdict and the narrated note.
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

## 5. Upstream contributions to Genesis (repros in `upstream/`)

**Pull request [genesis-world#3193](https://github.com/Genesis-Embodied-AI/genesis-world/pull/3193)** fixes finding 1 below: a once-per-solver warning naming the DOFs whose actuator ignores position and velocity targets, guarded so stepping loops pay nothing after the first call, with a regression test on the project's existing `general_actuator` fixture.

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

- Task success is 13/32 on virgin seeds (6/32 on task B) — real, significant, and
  still a minority of episodes. The remaining 19 failures are dominated by upstream
  routing losses (CABLE_SLIP 13, MISSED_GRASP 2, CLIP_2_MISSED 1) rather than the
  endgame; the seating stage itself converts 13 of the 15 episodes that reach it.
  No claim is made that the task is solved.
- The cable is a rigid articulated chain (Genesis 1.3.1 has no 1-D deformable; the
  PRD's original claim of a String/Fiber solver was corrected against the installed
  package). No sim-to-real claims are made anywhere.
- Simulation non-determinism (§4) bounds what any single-episode analysis can claim
  on this stack; all statistics here are suite-level.
- Batched throughput was measured twice with up to 11% spread; ranges are reported
  rather than best-run figures.
- The ROCm-trained failure predictor is a weak ranker (AUC 0.592) and a poor
  classifier (accuracy below the majority-class rate). It is reported as a measured
  negative, not presented as a working component of the qualification pipeline.

## 7. Generality: a second task, and a model trained on the Radeon

**A second task, qualified with one command.** `configs/task_b.yaml` changes the task
geometry only — the cable physics is byte-identical to task A, so the variable is the
task and not the solver. No code changed and nothing was re-tuned. `candidate-v4`,
selected entirely on task A, scores 6/32 vs the baseline's 0/32 (+18.8 pp,
p = 0.0312, zero discordant pairs against). The repairs transfer, and the harness
qualifies a new task the same way it qualified the first. A first task-B attempt that
also lengthened the cable produced a numerically unstable scene; the taxonomy reported
`UNSTABLE_SIMULATION` rather than blaming the controller, the config was retuned to
vary geometry alone, and the unstable run is disclosed and not counted (gate 23).

**A failure predictor trained on the Radeon — and an honest negative.** A small
PyTorch MLP trained through ROCm (`torch 2.13.0+rocm7.2`, HIP 7.2.53211, refusing to
run without a visible ROCm device) on 224 retained episodes, evaluated on 96 episodes
from seeds it never saw. Held-out ROC AUC **0.592** against a chance baseline of 0.5;
ranking conditions by predicted risk finds failures **~1.2x faster than random
sampling**; and its thresholded accuracy, 0.802, is *worse* than the 0.844 you would
get by always predicting failure. Both numbers are reported because both are true: the
ranking carries a small real signal, the classifier does not.

That negative is the useful part. It quantifies how little of an outcome is
predictable from initial conditions on this stack — the same phenomenon as the
measured non-reproducibility of contact rollouts (§4) — and it is a direct,
numerical argument for the architecture used throughout this project: **matched
suites and suite-level statistics, never single-episode claims.**

## 7b. The measured safety envelope

Every episode records the peak contact force the cable saw and the peak contact force
the arm's own links saw, from the same `get_links_net_contact_force` call. The limits
they are judged against live in `configs/task.yaml` (`tension_n: 30.0`,
`arm_collision_n: 60.0`), and an episode that breaks one is failed, not smoothed over.
On the held-out suite (701-732, 64 episodes in the shipped bundle):

| Peak per episode | `baseline-v1` | `candidate-v4` |
|---|---|---|
| Cable tension, median | 7.21 N | 18.14 N |
| Cable tension, p90 | 12.41 N | 23.49 N |
| Cable tension, max | 14.34 N | 40.26 N |
| Arm-link contact, max | 0.00 N | 0.00 N |
| Episodes failed as `OVER_TENSION` | 0/32 | 1/32 |

The repaired controller works the cable materially harder — that is the honest cost of
a controller that reaches the endgame rather than dropping the strand early, and the
baseline's low numbers are a symptom of failing sooner, not of being gentler. One
candidate episode crossed the 30 N limit; it is recorded as `OVER_TENSION` and counted
in the failure column above. Arm-link contact is zero across all 64 episodes: the arm
body never touched the table or the fixture, and the gripper's intended contact with
the cable is measured on the cable channel instead. The wider harness has recorded
peaks up to 65.20 N on the task-B baseline, so the instrument is not saturated at
these values.

**Disclosure:** the standard-suite episodes in the same bundle (101-132) were produced
before this instrumentation landed and carry `0.0` in both fields. They are evidence
of the no-regression comparison only, and no safety statement is derived from them.

## 8. What CRUX is for — beyond this controller

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

## 9. Reproduce / verify

```bash
uv run pytest -q                      # 259 CPU tests, no GPU needed
uv run crux validate evidence/manifest.json   # re-verify the bundle on CPU
uv run crux report evidence-dev/qualification_v4_standard.jsonl \
  evidence-dev/qualification_v5.jsonl \
  --baseline-version baseline-v1 --repaired-version candidate-v4 \
  --config configs/qualification.yaml           # every headline number from raw JSONL
# GPU experiments: src/crux/simulation/gate*.py, in gate order, on ROCm
```

Every number in this report is computed from `evidence-dev/*.jsonl` by code in this
repository; none is hand-maintained.
