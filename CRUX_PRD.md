# CRUX

## Product Requirements Document

**Tagline:** Find the crux. Forge the fix. Prove the repair.

**Track:** AMD AI DevMaster Hackathon 2026 — Track 3: Physical AI  
**Product category:** Robotic simulation, failure discovery, controller repair, and qualification  
**Primary embodiment:** Franka robotic arm  
**Primary task:** Flexible cable routing and connector insertion  
**Compute target:** One AMD Radeon GPU on Radeon Cloud using ROCm  
**Preferred simulator:** Genesis World using `gs.amdgpu`  
**Document version:** 1.0  
**Date:** August 4, 2026  
**Product owner:** Enoch Idowu  
**Submission deadline:** August 6, 2026, 4:59 PM WAT  
**Recommended internal submission cutoff:** August 6, 2026, 1:00 PM WAT

---

## 1. Executive Summary

CRUX is a self-improving Physical AI reliability system for contact-rich robotic assembly.

The initial application is robotic cable installation. A Franka arm must grasp a flexible cable, route it through two clips, align its connector, and insert it into a socket. The environment varies cable stiffness, friction, starting shape, clip position, socket orientation, visual conditions, and gripper properties.

A normal robotics project would train a controller and report its success rate.

CRUX goes further:

1. Runs the baseline controller across hundreds of physical worlds.
2. Detects and classifies the exact reasons for failure.
3. Restores the robot immediately before each failure.
4. Explores alternative physical futures in parallel on AMD Radeon.
5. Converts successful alternatives into a targeted repair dataset.
6. Fine-tunes a lightweight residual controller.
7. Tests the repaired controller on untouched held-out conditions.
8. Rejects the repair when it improves adversarial performance by sacrificing normal performance.
9. Produces a verifiable evidence receipt connecting every claim to raw results, seeds, replays, and hardware telemetry.

The central product claim is:

> Other systems train, control, or test a robot. CRUX discovers where it fails, repairs the controller, and proves that the repair generalizes.

CRUX must be presented as a simulation-only engineering prototype. It must not claim physical-robot safety, certification, or proven simulation-to-reality transfer.

---

## 2. Why This Product Can Win

The strongest Track 3 projects already occupy several obvious categories:

- GuardianSim owns large-scale parallel safety screening and auditable action selection.
- Chaal owns rapid end-to-end reinforcement learning and detailed Radeon scaling.
- FlightGuard owns adversarial controller qualification and rigorous matched-condition evidence.
- RadeonHome owns natural-language-guided mobile manipulation and failure recovery.
- Other entries already cover fruit sorting, locomotion, marine simulation, and vision-based control.

Therefore, CRUX must not compete as:

- another pick-and-place application;
- another chatbot controlling a robot;
- another raw simulation-throughput benchmark;
- another safety filter;
- another basic PPO training demonstration;
- another fruit-sorting system.

Its unclaimed territory is the complete **failure-to-repair-to-proof loop** applied to a difficult flexible-object task.

Genesis exposes an AMD ROCm backend through `gs.amdgpu`, verified working on this project's Radeon PRO W7900 (see §11).

Genesis 1.3.1 provides **no one-dimensional deformable primitive**. Its material groups are FEM (Cloth, Elastic, Muscle), MPM (Elastic, ElastoPlastic, Liquid, Muscle, Sand, Snow), PBD (Cloth, Elastic, Liquid, Particle), SPH (Liquid), and SF (Smoke) — where `SF` is *Stable Fluid*, not String/Fiber. No morph exposes a line, strand, or curve. The cable is therefore built as a rigid articulated chain (§11 Option B), and that representation is disclosed wherever cable behavior is claimed.

This absence is itself an opportunity: a working ROCm-verified cable example is a substantive upstream contribution under §23 rather than a token issue.

Useful sources:

- [AMD Radeon Hackathon Repository](https://github.com/AMD-DEV-CONTEST/Radeon-hackathon-2026-07)
- [Genesis World](https://github.com/Genesis-Embodied-AI/genesis-world)

---

## 3. Product Vision

Robotic policies usually fail outside the exact conditions under which they were designed or trained.

Engineers then spend significant time:

- reproducing the failure;
- identifying which condition caused it;
- deciding which scenarios should be added to training;
- retraining the controller;
- checking whether the repair created regressions elsewhere;
- preparing evidence that the new version is genuinely better.

CRUX turns that manual process into a repeatable pipeline.

The long-term vision is a reliability layer that can sit around any robotic controller:

```text
Existing controller
        ↓
Parallel failure discovery
        ↓
Failure explanation
        ↓
Targeted repair generation
        ↓
Controller improvement
        ↓
Held-out qualification
        ↓
Approved controller release or explicit rejection
```

The hackathon version demonstrates this vision through cable assembly because flexible cables expose failures that simple rigid-object manipulation does not:

- continuously changing geometry;
- snagging;
- bending and twisting;
- grasp instability;
- tension constraints;
- visual self-occlusion;
- contact-rich routing;
- precise final insertion.

---

## 4. Product Principles

### 4.1 Evidence before spectacle

Every headline result must come from a frozen machine-readable benchmark.

Selected videos may illustrate results, but they must not determine aggregate metrics.

### 4.2 Matched comparisons

Baseline and repaired controllers must be evaluated using identical:

- initial robot state;
- cable configuration;
- physical parameters;
- object positions;
- sensor noise;
- random seed;
- episode timeout.

### 4.3 No hidden baseline weakening

The baseline must be a reasonable frozen controller, not an intentionally broken system created to make the repaired controller appear impressive.

### 4.4 Held-out proof

Conditions used for repair generation must remain separate from final qualification conditions.

### 4.5 No-regression release gate

A controller repair is not accepted merely because it improves difficult cases. It must preserve performance in standard cases.

### 4.6 Radeon must perform meaningful work

AMD Radeon cannot be a badge attached to CPU-controlled logic. It must execute the central workload:

- physics simulation;
- parallel counterfactual evaluation;
- camera or keypoint inference;
- residual-policy training;
- residual-policy inference;
- final benchmark evaluation.

### 4.7 Honest claim boundaries

No fabricated metrics, hidden failed trials, or unsupported safety claims are permitted.

Unfinished or failed experiments should be documented as limitations.

---

## 5. Target Users

### Primary users

#### Robotics reliability engineer

Needs to understand why a controller fails and whether a proposed repair is trustworthy.

#### Simulation and controls engineer

Needs to reproduce failures, explore alternative controls, and compare controller versions.

#### Robotics machine-learning engineer

Needs useful counterexamples and targeted training data rather than more random episodes.

#### Manufacturing automation team

Needs to qualify robotic assembly behavior before expensive hardware trials.

### Initial industries

- Automotive wire-harness assembly
- Electronics manufacturing
- EV battery-pack wiring
- Appliance manufacturing
- Data-center cable installation
- Robotic maintenance
- Aerospace electrical assembly

---

## 6. Primary User Story

> As a robotics engineer, I want to evaluate my cable-assembly controller across varied physical conditions, automatically discover its failure families, generate targeted repairs, and verify the repaired controller on unseen conditions so I can decide whether the new controller is ready to advance to hardware testing.

---

## 7. Hero Demonstration

A Franka arm receives the task:

> Route the orange cable through both clips and fully insert it into the blue socket.

The baseline controller:

1. Locates the cable.
2. Grasps it.
3. Passes it through the first clip.
4. Approaches the second clip.
5. Catches the cable against an obstacle.
6. Produces excessive tension.
7. Releases or fails the task.

CRUX then:

1. Marks the event as `CABLE_SNAG`.
2. Identifies the last safe checkpoint.
3. Restores that same state across multiple parallel worlds.
4. Tests alternative approach directions, heights, grip positions, and motion speeds.
5. Finds successful alternatives.
6. Distills those alternatives into the repair controller.
7. Reruns the previously failed condition.
8. Completes the routing and insertion.
9. Shows improvement across the full held-out benchmark.
10. Produces an evidence receipt.

A second live demonstration intentionally causes the cable to slip. The robot must detect the slip, locate the cable end, regrip it, and resume from the last verified clip instead of restarting the entire task.

---

## 8. Goals

### G1. Demonstrate a difficult robot capability

Complete a contact-rich cable-routing and connector-insertion task involving a many-degree-of-freedom articulated cable whose shape changes continuously under contact.

### G2. Demonstrate automatic failure discovery

Run a frozen controller across randomized physical environments and classify failures using explicit reason codes.

### G3. Demonstrate controller repair

Convert failure states into targeted physical counterexamples and train a residual correction controller.

### G4. Demonstrate generalization

Show that the repaired controller improves on untouched held-out conditions.

### G5. Demonstrate no-regression qualification

Reject repairs that cause unacceptable deterioration on standard conditions.

### G6. Demonstrate meaningful Radeon acceleration

Run simulation, counterfactual search, training, and inference on one AMD Radeon GPU through ROCm.

### G7. Produce judge-verifiable evidence

Connect each metric to raw trials, replay files, source revision, environment details, and checksums.

### G8. Make a genuine upstream contribution

Contribute a tested fix, benchmark, example, or documentation improvement to an upstream robotics project, preferably Genesis.

---

## 9. Non-Goals

The hackathon version will not attempt:

- physical robot deployment;
- certified safety claims;
- full simulation-to-real transfer;
- dual-arm manipulation;
- multiple robot embodiments;
- arbitrary natural-language robot programming;
- a large vision-language-action model;
- photorealistic industrial digital twins;
- a general-purpose robotics operating system;
- unlimited cable topology;
- an unbounded action search;
- autonomous modification of production robot software.

Natural-language input may exist as a small convenience feature, but it is not a core innovation or a major part of the demo.

---

## 10. Scope Priorities

### P0 — Submission-critical

- Radeon/ROCm preflight
- Franka scene
- Cable or cable-equivalent simulation
- Two routing clips
- Connector and socket
- Frozen baseline controller
- Physical randomization
- Failure taxonomy
- Parallel evaluation
- At least one repair cycle
- Held-out comparison
- No-regression gate
- Raw benchmark output
- GPU telemetry
- Replay generation
- Reproducibility README
- Technical report
- Demo video
- Upstream contribution attempt

### P1 — Strong differentiators

- Counterfactual recovery search
- Residual-policy distillation
- Live slip recovery
- Failure heatmap
- Side-by-side matched replay
- Evidence receipt
- Public judge arena
- Ablation study
- Confidence intervals
- One-command evidence validator

### P2 — Only after submission is secure

- Typed natural-language task command
- RGB-D visualization
- Multiple cables
- Three or more clips
- Additional socket types
- Voice input
- Full interactive scene editor
- Policy plugin marketplace

---

## 11. Technical Feasibility Gate

**Status: RESOLVED — Option B selected, 2026-08-04.**

### Option A — Native String/Fiber cable — REJECTED

The premise did not survive contact with the installed simulator. Genesis 1.3.1 has no
String/Fiber solver and no 1D deformable primitive of any kind.

Evidence, gathered on the Radeon instance running Genesis 1.3.1 (ROCm 7.2.1, gfx1100):

```text
gs.materials  FEM -> Base, Cloth, Elastic, Muscle
              MPM -> Base, Elastic, ElastoPlastic, Liquid, Muscle, Sand, Snow
              PBD -> Base, Cloth, Elastic, Liquid, Particle
              SF  -> Base, Smoke          <- Stable Fluid, not String/Fiber
              SPH -> Base, Liquid

gs.morphs     Box, Cylinder, Sphere, Mesh, MeshSet, Plane, Primitive,
              Terrain, URDF, MJCF, USD, Drone, Nowhere    <- no line/strand/curve
```

A source search for `rope|cable|fiber` across the Genesis package returned only
false positives on the substring inside the word "p**rope**rties".

Every material is 2D (Cloth), volumetric (Elastic, ElastoPlastic), or particle/fluid.
None represents a one-dimensional structure.

### Option B — Rigid articulated cable — SELECTED

Represent the cable as a chain of short capsule links connected by constrained joints,
with a rigid Franka, rigid clips, and rigid socket.

This is not a degraded consolation. Rigid-body dynamics is the best-supported and most
numerically stable path on ROCm, so the selected representation is likely more reliable
for producing defensible evidence than any deformable solver would have been.

Acceptance requirements (inherited from the original Option A gate):

- runs using `gs.init(backend=gs.amdgpu)`;
- supports repeatable reset;
- supports contact with gripper and clips;
- supports multiple environments or sufficiently fast repeated execution;
- exports cable state for failure detection;
- does not silently fall back to CPU.

The representation must preserve:

- bend behavior;
- approximate twist behavior;
- snagging;
- contact;
- tension estimation;
- self-occlusion;
- grasp and routing difficulty.

The product claim must disclose which representation was used.

The submission must not spend most of the remaining build time debugging a simulator feature that cannot produce reliable evidence.

---

## 12. End-to-End Workflow

```text
Task configuration
      ↓
Radeon environment preflight
      ↓
Frozen baseline evaluation
      ↓
Failure detection and classification
      ↓
Failure-state checkpointing
      ↓
Parallel counterfactual repair search
      ↓
Repair dataset construction
      ↓
Residual-policy training
      ↓
Primary matched re-evaluation
      ↓
Held-out qualification
      ↓
No-regression decision
      ↓
Evidence receipt and replay publication
```

---

## 13. System Architecture

```text
┌────────────────────────────────────────────────────────────┐
│                         CRUX ARENA                         │
│ Next.js judge UI                                           │
│ Baseline vs repaired replay · failure map · ROCm telemetry │
└──────────────────────────────┬─────────────────────────────┘
                               │
                               ▼
┌────────────────────────────────────────────────────────────┐
│                  FASTAPI ORCHESTRATOR                      │
│ Run creation · lifecycle · manifests · WebSocket progress  │
└───────┬─────────────────┬──────────────────┬───────────────┘
        │                 │                  │
        ▼                 ▼                  ▼
┌──────────────┐  ┌────────────────┐  ┌────────────────────┐
│ Simulation   │  │ Repair Engine  │  │ Evidence Registry  │
│ Genesis      │  │ Search         │  │ JSON/JSONL         │
│ gs.amdgpu    │  │ Distillation   │  │ SHA-256 manifest   │
│ Franka+cable │  │ Qualification  │  │ replay references  │
└──────┬───────┘  └───────┬────────┘  └────────────────────┘
       │                  │
       ▼                  ▼
┌──────────────┐  ┌────────────────┐
│ Perception   │  │ Residual Policy│
│ RGB/keypoint │  │ Small MLP      │
│ geometry     │  │ PyTorch ROCm   │
└──────────────┘  └────────────────┘
```

---

## 14. Core Components

### 14.1 Simulation Engine

Responsibilities:

- load the robot and environment;
- build cable representation;
- apply randomized physical parameters;
- step physics;
- expose observations;
- apply controller actions;
- detect contact;
- capture checkpoints;
- restore checkpoints;
- render evaluation replays;
- report resolved backend and device.

Required physical objects:

- Franka Panda arm and gripper;
- workbench;
- flexible cable;
- two clips;
- connector;
- socket;
- optional snag obstacle;
- overhead or wrist camera.

### 14.2 Baseline Controller

The baseline must be deterministic and understandable.

Recommended structure:

```text
Observe
  ↓
Approach cable
  ↓
Close gripper
  ↓
Verify grasp
  ↓
Route through clip 1
  ↓
Verify clip 1
  ↓
Route through clip 2
  ↓
Verify clip 2
  ↓
Align connector
  ↓
Compliant insertion
  ↓
Verify seated connector
```

Control methods:

- inverse kinematics for Cartesian movement;
- joint-space interpolation;
- impedance-like low-speed insertion;
- fixed safety constraints;
- geometric cable keypoints;
- state-machine transitions.

The baseline must expose the point at which the residual policy can modify:

- Cartesian offset;
- waypoint height;
- approach direction;
- gripper force;
- movement speed;
- regrasp location;
- insertion angle.

### 14.3 Residual Repair Controller

The learned model does not replace the baseline.

It predicts bounded corrections:

```text
Δx, Δy, Δz
Δroll, Δpitch, Δyaw
Δspeed
Δgrip
regrasp probability
```

Recommended model:

- small multilayer perceptron;
- two or three hidden layers;
- approximately 50,000–500,000 parameters;
- observation normalization;
- bounded output activation;
- PyTorch ROCm training and inference.

Inputs:

- robot joint state;
- end-effector pose;
- cable keypoints;
- cable tension estimate;
- clip-relative geometry;
- connector-relative geometry;
- contact flags;
- current task stage;
- previous action;
- failure-risk indicators.

### 14.4 Failure Detector

Failure detection must be based on explicit physical conditions.

#### Required reason codes

| Reason code | Trigger |
|---|---|
| `MISSED_GRASP` | Gripper closes without verified cable contact |
| `CABLE_SLIP` | Verified grasp is lost before release stage |
| `CLIP_1_MISSED` | Cable fails clip-one geometric verification |
| `CLIP_2_MISSED` | Cable fails clip-two geometric verification |
| `CABLE_SNAG` | Cable movement stalls while contact or tension rises |
| `OVER_TENSION` | Tension proxy exceeds maximum threshold |
| `ROBOT_COLLISION` | Non-permitted robot-environment impulse exceeds threshold |
| `CONNECTOR_MISALIGNED` | Connector pose lies outside insertion tolerance |
| `INCOMPLETE_INSERTION` | Connector does not achieve required insertion depth |
| `TIMEOUT` | Episode exceeds maximum steps |
| `UNSTABLE_SIMULATION` | NaN, Inf, or impossible state detected |
| `SUCCESS` | Every task-stage verification passes |

Each failure event must include:

- `run_id`
- `episode_id`
- `seed`
- `controller_version`
- `reason_code`
- `task_stage`
- `simulation_step`
- `timestamp`
- `environment_parameters`
- `robot_state`
- `cable_state`
- `last_safe_checkpoint`
- `risk_metrics`
- `replay_path`

### 14.5 Checkpoint Manager

The system must capture recoverable states:

- before grasp;
- after verified grasp;
- after clip one;
- after clip two;
- before insertion;
- at failure precursor;
- at failure event.

A checkpoint must include enough state to reproduce the same event under the same controller.

Reproduction tolerance:

- same outcome in at least 4 of 5 reruns;
- preferably deterministic under a fixed seed;
- any nondeterminism must be disclosed.

### 14.6 Counterfactual Repair Search

At a failure checkpoint, CRUX generates bounded candidate corrections.

Example candidate dimensions:

- end-effector offset;
- waypoint height;
- approach angle;
- motion speed;
- grip force;
- cable grasp position;
- recovery stage;
- insertion compliance.

Search strategies:

1. Coarse structured grid around the baseline action.
2. Randomized candidates within safe bounds.
3. Optional cross-entropy-method refinement.
4. Optional policy-proposed candidates.

Each candidate is evaluated across uncertainty variants rather than a single exact world.

A candidate repair should be considered useful only when it:

- completes the local subtask;
- does not exceed the tension limit;
- avoids prohibited collision;
- preserves stability;
- progresses toward final completion;
- succeeds across a minimum fraction of uncertainty worlds.

### 14.7 Repair Dataset Builder

Successful counterfactuals become supervised repair examples.

Each example contains:

```text
observation
baseline action
successful corrective action
failure family
task stage
environment parameters
safety metrics
future task outcome
```

Examples must be balanced so one common failure type does not dominate training.

### 14.8 Repair Trainer

Minimum required training method:

- supervised distillation of successful corrective actions;
- held-out validation split;
- early stopping;
- checkpointing;
- fixed random seed;
- training telemetry;
- Radeon device assertion.

Optional refinement:

- PPO or another reinforcement-learning stage initialized from the distilled controller.

PPO must not be added when it risks destabilizing an already functioning repair pipeline.

### 14.9 Qualification Engine

The engine compares:

- frozen baseline;
- repaired controller;
- optional rule-only recovery controller;
- optional repair search without distillation.

Required evaluation suites:

#### Standard suite

Conditions close to intended operation.

Purpose: detect regression.

#### Primary randomized suite

Varied conditions from the declared development distribution.

Purpose: measure general task performance.

#### Adversarial suite

Difficult but bounded physical conditions.

Purpose: expose failure handling and robustness.

#### Retention held-out suite

Conditions not used during repair generation or model selection.

Purpose: measure generalization.

#### Forced-failure recovery suite

Episodes in which a slip, displacement, or obstruction is intentionally introduced.

Purpose: measure closed-loop recovery.

---

## 15. Environment Randomization

Each episode should record the exact sampled values.

### Cable parameters

- length
- thickness
- mass
- bend stiffness
- twist stiffness
- damping
- contact friction
- initial curve
- initial endpoint position

### Robot parameters

- gripper friction
- gripper closing-force scale
- joint damping
- control latency
- end-effector pose noise

### Scene parameters

- clip-one position
- clip-two position
- clip orientation
- socket position
- socket orientation
- obstacle position
- workbench friction

### Sensor parameters

- camera position
- camera rotation
- brightness
- contrast
- mild visual noise
- keypoint noise
- depth noise when depth is used

### Disturbances

- cable endpoint displacement
- temporary grip loss
- socket offset
- obstacle introduction
- one-frame or multi-frame observation delay

---

## 16. Perception Requirements

The minimum viable product may use simulator-ground-truth geometry for control, but this must be clearly disclosed.

The strongest accepted implementation uses a lightweight perception model for at least one meaningful observation, such as:

- cable endpoint detection;
- cable keypoint prediction;
- connector pose estimation;
- clip localization.

### Recommended staged approach

#### Stage 1

Use simulator state to complete the full physical and repair pipeline.

#### Stage 2

Generate labeled camera images automatically.

#### Stage 3

Train a lightweight cable-keypoint or endpoint model on Radeon.

#### Stage 4

Replace one ground-truth observation with model inference.

#### Stage 5

Compare oracle perception and learned perception.

The project must not allow perception work to prevent the complete failure-repair-proof loop from functioning.

---

## 17. Functional Requirements

### FR-001: Radeon backend verification

The application must fail loudly unless the resolved simulation backend is AMD GPU.

Displayed evidence must include:

- GPU name;
- architecture;
- ROCm/HIP version;
- PyTorch version;
- Genesis version;
- resolved Genesis backend;
- visible GPU count;
- VRAM;
- source commit.

### FR-002: Scenario configuration

A user must be able to select:

- controller version;
- suite;
- episode count;
- seeds;
- randomization profile;
- rendering mode;
- output directory.

### FR-003: Baseline run

The system must execute the frozen baseline and save every episode result.

### FR-004: Failure classification

Every unsuccessful episode must receive exactly one primary reason code and may receive secondary diagnostic tags.

### FR-005: Replay

Every representative failure family must have at least one reproducible replay.

### FR-006: Failure checkpoint restoration

A selected failure must be restorable from its last safe checkpoint.

### FR-007: Counterfactual evaluation

The system must evaluate multiple corrective candidates from the same restored state.

### FR-008: Repair dataset generation

The system must export successful correction examples in a versioned dataset.

### FR-009: Radeon training

The residual controller must be trained with device assertions proving execution on Radeon.

### FR-010: Frozen repaired checkpoint

The final controller must be stored with:

- checkpoint hash;
- training-data hash;
- configuration hash;
- source commit;
- environment manifest.

### FR-011: Held-out qualification

The repaired checkpoint must run on a suite whose seeds and parameter configurations were not used for training or repair selection.

### FR-012: No-regression gate

The repair must be rejected when standard-suite success deteriorates beyond the configured tolerance.

Recommended maximum allowed regression:

- two percentage points in success rate; or
- no more than one additional failure when sample size is small.

### FR-013: Evidence receipt

Every formal run must produce a receipt that can be validated without rerunning the GPU experiment.

### FR-014: Judge smoke test

A single CPU-only command must validate:

- file existence;
- schema correctness;
- hashes;
- result aggregates;
- suite separation;
- device evidence;
- checkpoint identity;
- video metadata;
- headline metrics.

### FR-015: Public judge arena

A no-login page must display the project’s main evidence in under 60 seconds.

---

## 18. Non-Functional Requirements

### Performance

- Control inference should target P50 below 10 ms.
- Control inference must remain below the simulation control interval.
- Formal benchmark runs must not silently use CPU fallback.
- Batch size must be selected from measured scaling rather than maximum VRAM usage alone.

### Reliability

- Formal runs must use pinned dependencies.
- Failed episodes must remain in the output.
- Interrupted runs must resume or clearly restart without mixing evidence.
- Partial results must not be treated as complete suites.

### Reproducibility

- Every formal result must include the source commit.
- Every suite must have a frozen configuration.
- Seeds must be declared before formal execution.
- The README must reproduce at least a small real Genesis/Radeon smoke test.

### Transparency

- Separate physics steps, episodes, candidate futures, and training samples.
- Do not combine different units into one inflated number.
- Label all targets as targets until measured.
- Report confidence intervals where meaningful.
- Disclose simulator representation and limitations.

---

## 19. Formal Evaluation Design

### 19.1 Suite sizes

#### Submission minimum

- Standard: 60 episodes
- Primary randomized: 120 episodes
- Adversarial: 60 episodes
- Held-out: 60 episodes
- Forced recovery: 30 episodes

#### Competitive target

- Standard: 192 episodes
- Primary randomized: 384 episodes
- Adversarial: 192 episodes
- Held-out: 192 episodes
- Forced recovery: 60 episodes

The competitive target should only be used when formal runs finish reliably and enough time remains to validate all outputs.

### 19.2 Primary metrics

- Full task success rate
- Grasp success
- Clip-one routing success
- Clip-two routing success
- Connector insertion success
- Recovery success
- Over-tension episode rate
- Prohibited-collision rate
- Mean completion time
- P95 completion time
- Mean insertion position error
- Mean insertion orientation error
- Mean maximum cable tension
- Timeout rate

### 19.3 Repair metrics

- Number of mined failure episodes
- Number of unique failure families
- Number of restored checkpoints
- Candidate futures evaluated
- Candidate repairs accepted
- Repair examples generated
- Repair-training duration
- Improvement on previously failed matched episodes
- Improvement on held-out episodes
- Standard-suite regression
- Remaining unresolved failure families

### 19.4 Radeon metrics

- Parallel environments
- Physics steps per second
- Complete episodes per minute
- Candidate futures per second
- Repair examples generated per minute
- Training samples per second
- P50/P95 control inference
- Mean GPU utilization
- Peak GPU utilization
- Peak VRAM
- Mean power where available
- Total formal GPU runtime

### 19.5 Statistical reporting

For success proportions:

- report numerator and denominator;
- report percentage;
- report 95% Wilson confidence interval.

For latency and throughput:

- warm up before measurement;
- run at least three repetitions;
- report median, minimum, and maximum;
- use the same scene and configuration.

For controller comparison:

- use matched episodes;
- report baseline-only wins;
- report repaired-only wins;
- report both-fail and both-succeed counts;
- optionally use McNemar’s test when sample size permits.

---

## 20. Performance Targets

These are engineering targets, not claims.

| Metric | Minimum acceptable | Competitive target |
|---|---:|---:|
| Baseline full-task success | Measured honestly | Measured honestly |
| Repaired held-out improvement | +15 percentage points | +25 percentage points |
| Forced-failure recovery | 70% | 85%+ |
| Over-tension reduction | 50% | 80%+ |
| Prohibited-collision reduction | 50% | 80%+ |
| Standard-suite regression | ≤2 percentage points | 0 regression |
| Reproduced failure rate | 80% | 95%+ |
| Evidence validator | 100% pass | 100% pass |
| Formal episode records retained | 100% | 100% |
| GPU-required stages on Radeon | All core stages | All core stages |
| Upstream contribution | Valid issue with reproduction | Tested pull request |

No result may be entered into the submission until it has been produced by the frozen benchmark.

---

## 21. Innovation Requirements

CRUX must prove innovation through implementation, not language.

The minimum innovation package is:

1. Failure-state restoration.
2. Physical counterfactual repair search.
3. Automatic repair-data generation.
4. Residual-controller distillation.
5. Frozen held-out qualification.
6. No-regression release gate.
7. Evidence-linked controller versioning.

The innovation should be described as:

> Counterexample-guided robotic controller repair using Radeon-parallel physical futures.

The system should not claim to invent:

- reinforcement learning;
- domain randomization;
- behavior cloning;
- simulation testing;
- residual control.

The originality comes from joining these techniques into an automated reliability loop that starts with real failure evidence and ends with an independently qualified controller release.

---

## 22. Application-Value Requirements

The technical report must connect the prototype to a realistic industrial workflow.

### Existing workflow

1. Deploy candidate robot controller in simulation.
2. Engineers manually inspect failures.
3. Engineers guess which scenarios to add.
4. Engineers retrain.
5. Engineers manually retest.
6. Failures are difficult to reproduce and compare.

### CRUX workflow

1. Run declared qualification suite.
2. Automatically cluster failure families.
3. Reproduce each failure from a checkpoint.
4. Search for corrective physical actions.
5. Build a targeted repair dataset.
6. Train a bounded residual controller.
7. Qualify the new version.
8. Release or reject it with evidence.

### Value proposition

- Shorter failure-analysis cycles
- Less random data collection
- Better reproduction
- More focused training
- Explicit regression detection
- Stronger evidence before hardware testing
- Lower risk of hiding rare physical failure modes

The report must avoid unsupported financial savings figures.

---

## 23. Upstream Open-Source Contribution

Track 3 reserves 10 points for upstream contributions, particularly contributions that improve AMD support.

### Preferred contribution order

#### Tier 1 — Tested code contribution

Examples:

- contribute a ROCm-verified articulated-cable example, addressing the absence of any 1D structure primitive (§11);
- add a missing ROCm-compatible cable example;
- fix batched cable-state reset;
- improve contact-state access on AMD;
- improve deterministic checkpoint restoration;
- add regression tests for AMD cable interaction;
- improve Radeon Docker or EGL setup.

#### Tier 2 — Benchmark or example

- publish a reproducible cable-manipulation benchmark;
- add a minimal Franka-plus-cable AMD example;
- contribute a performance test comparing environment counts.

#### Tier 3 — High-quality bug report

Must include:

- exact version;
- environment;
- minimal reproduction;
- expected behavior;
- actual behavior;
- stack trace or incorrect output;
- AMD-specific evidence;
- proposed cause where known;
- potential fix direction.

A low-effort issue filed solely for points must not be used.

---

## 24. Evidence Architecture

### Required directory layout

```text
evidence/
  manifest.json
  environment/
    hardware.json
    software.json
    rocm_smi.txt
    pip_freeze.txt
    source_commit.txt
  configs/
    baseline.yaml
    repair.yaml
    standard_suite.yaml
    primary_suite.yaml
    adversarial_suite.yaml
    heldout_suite.yaml
    recovery_suite.yaml
  raw/
    baseline_episodes.jsonl
    repaired_episodes.jsonl
    recovery_episodes.jsonl
    counterfactual_candidates.jsonl
    training_metrics.jsonl
    gpu_telemetry.csv
  summaries/
    capability_summary.json
    repair_summary.json
    radeon_summary.json
    comparison_summary.json
  checkpoints/
    baseline_controller.json
    repaired_policy.pt
    repaired_policy_metadata.json
  replays/
    baseline_failure.mp4
    repaired_same_seed.mp4
    slip_recovery.mp4
  checksums/
    SHA256SUMS
```

### Evidence receipt

Example:

```json
{
  "receipt_version": "1.0",
  "controller_version": "repair-v1",
  "source_commit": "<commit>",
  "checkpoint_sha256": "<hash>",
  "training_dataset_sha256": "<hash>",
  "suite_config_sha256": "<hash>",
  "hardware_manifest_sha256": "<hash>",
  "baseline": {
    "successes": 0,
    "episodes": 0
  },
  "repaired": {
    "successes": 0,
    "episodes": 0
  },
  "standard_regression_pp": 0,
  "decision": "APPROVED_OR_REJECTED",
  "reason_codes": [],
  "created_at": "<timestamp>"
}
```

Values remain zero or absent until generated from formal evidence.

---

## 25. User Interface Requirements

The UI should feel like an industrial qualification console rather than a generic SaaS dashboard.

### Screen 1 — Judge Overview

Must answer within ten seconds:

- What does CRUX do?
- What failed?
- What changed?
- Did the repair generalize?
- What work ran on Radeon?

Hero line:

> One Radeon discovered the failures, forged the repair, and proved the new controller.

Headline cards:

- Baseline success
- Repaired held-out success
- Failure reduction
- Recovery success
- Candidate physical futures
- GPU utilization

### Screen 2 — Matched Replay

Side-by-side display:

- same seed;
- same cable;
- same physical conditions;
- baseline controller;
- repaired controller;
- synchronized timeline;
- current task stage;
- tension;
- collision indicator;
- reason code.

### Screen 3 — Failure Map

Displays:

- failure-family distribution;
- failure by cable stiffness;
- failure by friction;
- failure by clip offset;
- failure by task stage;
- representative replay for each family.

### Screen 4 — Repair Loop

Displays:

```text
failed states
→ restored checkpoints
→ candidate futures
→ accepted corrections
→ repair examples
→ trained checkpoint
```

### Screen 5 — Qualification

Displays:

- standard suite;
- adversarial suite;
- held-out suite;
- recovery suite;
- baseline-only wins;
- repaired-only wins;
- no-regression decision.

### Screen 6 — Radeon Evidence

Displays:

- Radeon model;
- ROCm version;
- backend assertion;
- GPU telemetry;
- scaling curve;
- inference latency;
- training throughput;
- peak VRAM.

### Screen 7 — Evidence Receipt

Displays:

- source commit;
- checkpoint hash;
- dataset hash;
- suite hash;
- downloadable JSON;
- validator command;
- limitations.

---

## 26. API Requirements

### `POST /api/runs`

Creates a benchmark or repair run.

Request:

```json
{
  "run_type": "baseline|repair_search|training|qualification",
  "controller_version": "baseline-v1",
  "suite": "primary",
  "episode_count": 120,
  "seeds": [101, 102, 103],
  "render": false
}
```

### `GET /api/runs/{run_id}`

Returns:

- status;
- progress;
- completed episodes;
- failures;
- throughput;
- GPU telemetry summary;
- artifact paths.

### `GET /api/runs/{run_id}/episodes`

Supports filters:

- outcome;
- reason code;
- stage;
- seed;
- controller.

### `GET /api/comparisons/{comparison_id}`

Returns baseline-versus-repaired matched results.

### `GET /api/evidence/{receipt_id}`

Returns the evidence receipt and linked artifacts.

### `WS /api/runs/{run_id}/stream`

Streams:

- progress;
- completed episode;
- failure event;
- accepted counterfactual;
- training update;
- qualification update.

---

## 27. Repository Structure

```text
crux/
  README.md
  LICENSE
  Dockerfile
  pyproject.toml
  Makefile
  configs/
  src/
    crux/
      cli.py
      config.py
      simulation/
        scene.py
        cable.py
        robot.py
        randomization.py
        checkpoints.py
      control/
        baseline.py
        residual.py
        safety.py
        state_machine.py
      perception/
        keypoints.py
        dataset.py
      failures/
        detector.py
        taxonomy.py
        recorder.py
      repair/
        candidate_generator.py
        evaluator.py
        dataset_builder.py
        trainer.py
      qualification/
        suites.py
        metrics.py
        compare.py
        release_gate.py
      evidence/
        manifest.py
        hashing.py
        validator.py
        replay.py
      telemetry/
        rocm.py
  apps/
    arena/
  scripts/
    preflight.sh
    run_smoke.sh
    run_baseline.sh
    run_repair.sh
    run_formal_eval.sh
    validate_evidence.py
  tests/
  docs/
    technical-report.md
    architecture.md
    reproduction.md
    limitations.md
    upstream.md
  evidence/
```

---

## 28. CLI Requirements

```bash
crux doctor
```

Validates Radeon, ROCm, simulator, rendering, and output directories.

```bash
crux smoke
```

Runs one cable-assembly episode and proves the real simulation path.

```bash
crux evaluate --controller baseline-v1 --suite primary
```

Runs a formal controller evaluation.

```bash
crux mine-failures --run <run-id>
```

Creates the failure corpus.

```bash
crux repair --failures <run-id>
```

Executes counterfactual search and builds the repair dataset.

```bash
crux train --dataset <dataset-id>
```

Trains the residual controller on Radeon.

```bash
crux qualify --baseline baseline-v1 --candidate repair-v1
```

Runs matched and held-out qualification.

```bash
crux validate evidence/manifest.json
```

Performs a CPU-only evidence check.

---

## 29. Acceptance Gates

### Gate 0 — Hardware

Pass when:

- Radeon GPU is visible;
- ROCm is operational;
- PyTorch tensors run on Radeon;
- Genesis resolves to `gs.amdgpu`;
- no core-stage CPU fallback exists.

### Gate 1 — Physical scene

Pass when:

- Franka loads;
- cable loads;
- cable interacts with gripper and clips;
- reset works;
- fixed-seed replay is sufficiently repeatable.

### Gate 2 — Baseline capability

Pass when:

- the robot can complete the full task under at least one normal configuration;
- each stage has a verification condition;
- failures produce reason codes.

### Gate 3 — Parallel evaluation

Pass when:

- multiple environments or repeated workers run reliably;
- raw episodes are recorded;
- throughput is measured;
- GPU telemetry is captured.

### Gate 4 — Failure reproduction

Pass when:

- at least three meaningful failure families are reproduced;
- last-safe checkpoints restore correctly;
- matched baseline reruns reproduce the failure.

### Gate 5 — Repair

Pass when:

- counterfactual search finds successful corrections;
- repair examples are generated;
- a residual checkpoint is trained;
- the repaired controller changes physical behavior.

### Gate 6 — Qualification

Pass when:

- repaired performance improves on primary or adversarial conditions;
- held-out results are available;
- standard regression remains within tolerance;
- all failed trials remain visible.

### Gate 7 — Submission evidence

Pass when:

- validator passes;
- hashes pass;
- report and README agree with raw results;
- video numbers agree with summaries;
- public links work while logged out.

---

## 30. Ablation Studies

At least two should be completed.

### Ablation A — Baseline versus repaired

Proves whether repair improves performance.

### Ablation B — Random retraining versus targeted repair

Compares:

- random additional training scenarios;
- failure-targeted training scenarios.

This is the strongest ablation because it tests the product thesis directly.

### Ablation C — Repair without no-regression gate

Shows why improvement on adversarial cases alone is insufficient.

### Ablation D — Oracle perception versus learned perception

Shows the effect of camera-based perception.

### Ablation E — Counterfactual search versus rule-only recovery

Shows whether parallel physical search contributes beyond a handcrafted retry.

---

## 31. Four-Minute Demo Script

### 0:00–0:20 — Hook

Show the robot routing a cable.

Narration:

> Industrial robots often work until one physical detail changes: friction, stiffness, alignment, or cable shape. Finding and repairing those failures is still largely manual.

### 0:20–0:45 — Baseline failure

Show the cable snagging under a difficult condition.

Overlay:

```text
CABLE_SNAG
Stage: ROUTE_CLIP_2
Tension threshold exceeded
Seed: [measured seed]
```

### 0:45–1:15 — Failure discovery

Show parallel environments and the failure map.

Narration:

> CRUX runs the frozen controller across physical variations on one AMD Radeon GPU and records exactly where and why it fails.

### 1:15–1:50 — Counterfactual repair

Show:

- restored state;
- many alternative physical futures;
- accepted correction;
- repair-example generation.

Narration:

> From the last safe state, Radeon evaluates bounded corrective futures. Successful corrections become targeted repair data.

### 1:50–2:15 — Controller training

Show:

- PyTorch ROCm device;
- training progress;
- checkpoint hash;
- training duration.

### 2:15–2:50 — Matched proof

Show the same seed side by side.

Left: baseline fails.  
Right: repaired controller succeeds.

### 2:50–3:15 — Held-out results

Show aggregate results from untouched conditions.

Must display:

- numerator and denominator;
- confidence interval;
- standard-suite regression;
- failure reduction.

### 3:15–3:35 — Live recovery

Force a cable slip.

Show:

- slip detection;
- re-localization;
- regrasp;
- continuation from the last verified stage;
- successful insertion.

### 3:35–4:00 — Radeon and evidence

Show:

- Radeon hardware;
- ROCm backend;
- GPU utilization;
- scaling;
- evidence receipt;
- validator;
- upstream contribution.

Closing line:

> CRUX does not just show that a robot worked once. It shows where it failed, how it was repaired, and why the new controller deserves to advance.

---

## 32. Judge Experience

### First 10 seconds

The judge sees:

- one-line problem;
- one-line solution;
- baseline-versus-repaired success;
- matched replay button;
- AMD Radeon hardware proof.

### First 60 seconds

The judge understands:

- the task is difficult;
- failures are real;
- repair is automatic;
- proof is held out;
- Radeon is central;
- all evidence is inspectable.

### First 5 minutes

The judge can:

- watch the full demo;
- inspect each rubric criterion;
- run the validator;
- open the source;
- view the upstream contribution;
- understand limitations.

---

## 33. Judging-Criteria Mapping

### Robot Capability Performance — 30 points

Evidence:

- complete grasp-route-insert task;
- articulated multi-link cable interaction, with the representation disclosed per §11;
- explicit stage verification;
- randomized evaluation;
- held-out success;
- live recovery;
- physical safety metrics;
- matched baseline comparison.

### AMD Radeon GPU and ROCm Adoption — 20 points

Evidence:

- Genesis on `gs.amdgpu`;
- parallel physics;
- counterfactual physical search;
- PyTorch ROCm repair training;
- ROCm inference;
- telemetry;
- scaling experiment;
- GPU-required preflight.

### Innovation — 20 points

Evidence:

- failure-triggered controller repair;
- last-safe-state restoration;
- counterexample-guided repair data;
- physical-future search;
- residual-policy distillation;
- no-regression release gate;
- evidence-bound controller release.

### Application Value — 20 points

Evidence:

- wire-harness and cable-assembly relevance;
- difficult contact-rich task;
- repeatable qualification workflow;
- reduced manual failure-analysis effort;
- extensibility to other assembly controllers.

### Upstream Community Contribution — 10 points

Evidence:

- tested upstream pull request, benchmark, example, or high-quality bug report;
- clear AMD/ROCm relevance;
- reproduction and tests;
- contribution made during the competition.

---

## 34. Competitive Positioning

### Against GuardianSim

GuardianSim screens proposed actions for safety.

CRUX uses physical alternatives to create a controller repair that can later act without repeating the complete search.

### Against Chaal

Chaal proves fast end-to-end locomotion learning.

CRUX focuses on failure-driven learning for a contact-rich flexible-object assembly process and includes controller-version qualification.

### Against FlightGuard

FlightGuard tests controller robustness across matched adversarial conditions.

CRUX turns failed conditions into targeted repair data, trains a new controller, and verifies the resulting version.

### Against RadeonHome

RadeonHome executes a broad household-manipulation pipeline with recovery.

CRUX goes deeper on a harder flexible-object task and makes automated failure discovery, repair, and proof the product itself.

### Against fruit-sorting projects

Sorting proves rigid-object manipulation.

CRUX requires a continuously reconfiguring multi-body cable, multi-stage routing, contact reasoning, tension management, recovery, and precision insertion.

---

## 35. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| ~~Native cable solver fails on Radeon~~ RESOLVED 2026-08-04 | Critical | No 1D solver exists in Genesis 1.3.1; articulated capsule chain selected (§11) |
| Cable contact is unstable | Critical | Simplify geometry, lower speeds, increase solver iterations, use bounded task |
| Parallel cable environments consume too much memory | High | Reduce environment count; report scaling honestly; use multiple processes |
| Full RL training is unstable | High | Use counterfactual search plus supervised residual distillation |
| Perception model takes too long | Medium | Keep oracle-state control for the core loop; add one learned perception component later |
| Baseline succeeds almost always | Medium | Expand bounded adversarial conditions without weakening baseline |
| Baseline almost never succeeds | High | Simplify to two clips and one insertion; freeze a competent baseline first |
| Repair overfits failed episodes | High | Separate held-out and standard suites; enforce no-regression gate |
| Repair produces small improvement | High | Target the dominant failure family; reduce repair output dimensions |
| Demo rendering reduces throughput | Low | Separate headless formal runs from selected rendered replays |
| Upstream PR cannot be completed | Medium | Submit a high-quality reproducible issue or benchmark, but keep working toward code |
| UI consumes engineering time | Medium | Generate UI from frozen JSON after core evidence is complete |
| Metrics accidentally disagree | Critical | Generate report tables and UI values from the same summary JSON |

---

## 36. Deadline Execution Plan

### August 4 — Core feasibility

#### Morning

- Provision Radeon environment.
- Run ROCm and PyTorch preflight.
- Install and verify the Genesis AMD backend.
- Test the native cable solver.
- Decide native cable versus articulated fallback.
- Load Franka and the basic scene.

#### Afternoon and evening

- Implement baseline state machine.
- Complete one successful normal episode.
- Add task-stage verification.
- Add failure reason codes.
- Add randomization.
- Save episode JSONL.

**End-of-day gate:** The complete task works at least once and meaningful failures are recorded.

### August 5 — Repair and evidence

#### Morning

- Add checkpoints.
- Implement failure restoration.
- Add counterfactual candidate generation.
- Run the first repair search.
- Build the repair dataset.

#### Afternoon

- Train the residual model on Radeon.
- Run primary and held-out comparison.
- Implement the no-regression gate.
- Capture ROCm telemetry.

#### Evening

- Freeze controller and configs.
- Run the formal benchmark.
- Validate raw outputs.
- Generate summary JSON.
- Create matched replays.

**End-of-day gate:** Real baseline-versus-repaired evidence exists.

### August 6 — Submission packaging

#### Early morning

- Finish the public judge arena.
- Finish README and reproduction instructions.
- Finish the technical report.
- Finish the upstream contribution.
- Generate charts from raw JSON.

#### Late morning

- Record and edit the demo.
- Run a link checker.
- Run the evidence validator.
- Verify that the report, video, UI, and PR use identical numbers.
- Freeze the repository revision.

#### By 1:00 PM WAT

- Open the submission pull request.
- Review it in incognito.
- Fix only submission-blocking problems.

#### After 1:00 PM WAT

No new features.

Only:

- broken-link fixes;
- video-access fixes;
- README corrections;
- PR-format corrections;
- secret removal;
- final verification.

---

## 37. Submission Deliverables

### Technical report

Must contain:

1. Problem and application
2. Competitive differentiation
3. System architecture
4. Cable simulation design
5. Baseline controller
6. Failure taxonomy
7. Counterfactual repair
8. Residual training
9. Qualification methodology
10. Radeon and ROCm implementation
11. Results
12. Ablations
13. Upstream contribution
14. Limitations
15. Reproduction
16. Team contribution

### Source repository

Must include:

- complete source;
- license;
- pinned configuration;
- Dockerfile;
- setup scripts;
- tests;
- formal result artifacts;
- model checkpoint;
- validator;
- clear README.

### Demo video

- 3–5 minutes;
- English narration or captions;
- browser-playable;
- shows actual Radeon execution;
- shows the complete workflow;
- shows real result numbers;
- shows limitations.

### Supplementary material

Recommended:

- one-page industrial poster; or
- public evidence arena.

The public evidence arena provides greater value when it is polished and fast.

---

## 38. Final Submission Checklist

### Eligibility

- Hackathon registration complete
- AMD Developer Program registration complete
- Team information consistent
- Minor/guardian requirements handled where applicable

### Technical

- Radeon backend asserted
- No hidden CPU fallback
- Formal source commit frozen
- Configs frozen
- Baseline frozen
- Repaired checkpoint frozen
- Held-out suite untouched
- All failed trials retained
- Metrics regenerated from raw data
- Evidence validator passes
- Checksums pass

### Documentation

- README works from a clean environment
- Technical report opens
- Report text is selectable
- Architecture diagram is readable
- Limitations are explicit
- Dataset and asset licenses are documented
- All metrics include denominators
- Targets have been replaced with measured numbers or removed

### Media

- Video length is 3–5 minutes
- Audio and captions are understandable
- Links work while logged out
- No private credentials appear
- Matched replay uses the same seed and environment
- Radeon telemetry is visible

### Open source

- Contribution link works
- Reproduction is complete
- Contribution timing is documented
- No exaggerated merge claim is made

### Submission PR

- Correct Track 3 naming format
- Source repository linked
- Demo linked
- Report linked
- Reproduction linked
- Upstream contribution linked
- Headline results exactly match evidence
- PR opened before the internal cutoff

---

## 39. Hard Rules for the Coding Agent

1. Do not fabricate metrics, logs, videos, GPU output, or trial records.
2. Do not hard-code desired results into summary files.
3. Do not delete failed episodes.
4. Do not run formal baseline and repaired controllers on different conditions.
5. Do not use training conditions in the retention-held-out suite.
6. Do not claim Radeon execution without explicit device evidence.
7. Do not silently fall back to CPU.
8. Do not start UI polish before the complete physical loop works.
9. Do not add a large LLM or VLA unless every P0 requirement is already complete.
10. Do not add additional robot tasks merely to increase feature count.
11. Do not describe targets as achieved results.
12. Do not claim real-world safety or simulation-to-real success.
13. Generate every displayed number from machine-readable evidence.
14. Prefer one complete, defensible workflow over five incomplete features.
15. Stop feature development after the submission freeze.

---

## 40. Final Product Definition

CRUX is complete when a judge can observe the following chain without trusting unsupported claims:

```text
A competent robot controller encounters a real physical failure.
                            ↓
CRUX identifies and reproduces the failure.
                            ↓
One AMD Radeon evaluates corrective physical futures.
                            ↓
Successful corrections become targeted repair data.
                            ↓
A lightweight residual controller is trained on Radeon.
                            ↓
The repaired controller succeeds on the matched failure.
                            ↓
It also improves on untouched held-out conditions.
                            ↓
Standard performance does not meaningfully regress.
                            ↓
Every result is connected to raw evidence and a frozen release.
```

### One-line pitch

> CRUX is a Radeon-native reliability system that discovers robotic cable-assembly failures, forges targeted controller repairs, and proves those repairs on unseen physical conditions.

### Memorable closing line

> Do not trust a robot because it worked once. Trust the evidence showing how it failed, how it was repaired, and why the repair generalizes.
