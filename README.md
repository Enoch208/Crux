<div align="center">

# CRUX

![tests](https://img.shields.io/badge/tests-212%20passing-2FA46A)
![backend](https://img.shields.io/badge/backend-gs.amdgpu%20·%20ROCm%207.2.1-ED1C24)
![gate](https://img.shields.io/badge/release%20gate-APPROVED-2FA46A)
![evidence](https://img.shields.io/badge/evidence-9%2F9%20verified-5BA4FF)
[![page](https://img.shields.io/badge/live-enoch208.github.io%2FCrux-1f1f23)](https://enoch208.github.io/Crux/)

### Find how a robot fails. Repair it. **Prove it.**

Robotics can train a new manipulation policy in an afternoon — and then cannot answer the only question that matters: *is it actually better, and can you prove it to someone who wasn't there?* Failure discovery is manual, evidence is a cherry-picked video, and "works on my seed" ships. CRUX is the missing **reliability layer**: it runs a contact-rich task across thousands of matched, batched environments on **one AMD Radeon GPU**, isolates each failure mechanism with experiments that falsify the alternatives, applies named repairs, qualifies the result on virgin seeds with **exact statistics**, and packages every number into a **tamper-evident evidence bundle a judge re-verifies on a laptop CPU in minutes**. It even caught its own success metric being geometrically impossible — and proved it.

**[ Watch the demo ↗ ](evidence-dev/render/crux-demo.mp4)** · **[ Live evidence page ↗ ](https://enoch208.github.io/Crux/)** · **[ Verify it yourself ↗ ](#verify-it-yourself-in-60-seconds-cpu-only)** · **[ Technical report ↗ ](docs/technical-report.md)** · **[ Poster ↗ ](docs/poster.pdf)**

Built for the **AMD AI DevMaster Hackathon 2026** — Track 3: Physical AI.

</div>

---

## ▶ Demo

*Three and a half minutes, narrated, every clip a fresh rollout on the Radeon. The baseline loses the cable during routing. The same seed, side by side: the baseline dies at its regrasp while the repaired controller re-observes, retries, and recovers. Sixteen environments run at once under a live `rocm-smi` panel reading 100% busy. And at the end, one uncut, real-time episode runs the whole task — grasp, both gates, regrasp, align, insert — to a certified `SUCCESS`, the first this harness ever approved.*

https://github.com/user-attachments/assets/64731f6d-6503-4ba0-a5e5-eb3261c9f7cc

*(Also in-repo: [`evidence-dev/render/crux-demo.mp4`](evidence-dev/render/crux-demo.mp4))*

| Same seed, same scene | 16 envs + live telemetry | The certified SUCCESS | Verify on your CPU |
|---|---|---|---|
| ![split](docs/stills/split.png) | ![wide](docs/stills/wide.png) | ![success](docs/stills/success.png) | ![validator](docs/stills/validator.png) |

---

## Table of contents

- [The problem](#the-problem)
- [What CRUX is](#what-crux-is)
- [Verify it yourself in 60 seconds (CPU only)](#verify-it-yourself-in-60-seconds-cpu-only)
- [The headline result](#the-headline-result)
- [Architecture](#architecture)
- [The discovery campaign — 8 mechanisms, each earned](#the-discovery-campaign--8-mechanisms-each-earned)
- [The metric bug — the harness audited its own spec](#the-metric-bug--the-harness-audited-its-own-spec)
- [Qualification and the release gate](#qualification-and-the-release-gate)
- [Scale, on one Radeon](#scale-on-one-radeon)
- [Built for any controller — including learned ones](#built-for-any-controller--including-learned-ones)
- [Upstream contributions](#upstream-contributions)
- [Engineering decisions & the hard problems](#engineering-decisions--the-hard-problems)
- [What's real vs simplified — the honesty table](#whats-real-vs-simplified--the-honesty-table)
- [Tech stack](#tech-stack)
- [Project layout](#project-layout)
- [Run it locally](#run-it-locally)
- [Tests](#tests)
- [Docs](#docs)

---

## The problem

A Franka arm must grasp a 40 cm articulated cable, route it through two clip gates, align its connector, and seat it in a channel retainer — a task where contact makes everything fragile and one physical detail silently breaks a working controller. This is the situation industrial robotics lives in every day, and the tooling around it is remarkably thin:

- **Failure discovery is manual.** Someone watches replays and guesses.
- **Comparisons are unmatched.** The new policy runs on different conditions than the old one, and the difference is declared an improvement.
- **Evidence is vibes.** A demo video, a success rate with no denominator, no way for a reviewer to recompute anything.
- **Success metrics are unaudited.** Nobody checks whether the definition of "done" is even achievable — this project found its own wasn't (see [the metric bug](#the-metric-bug--the-harness-audited-its-own-spec)).

Software fixed this a decade ago with SRE: measure, isolate, fix, gate the release on evidence. Robotics has no equivalent. CRUX is that layer, built AMD-native from the first line.

## What CRUX is

A failure-discovery → repair → qualification harness whose every stage runs on, or is verified against, one Radeon PRO W7900. The memorable loop:

<div align="center">

**`FAIL → ISOLATE → REPAIR → QUALIFY → GATE → PROVE`**

</div>

1. **Fail** — run the frozen controller across seeded physical variations, 32–128 matched environments at a time in one batched Genesis scene. Every episode becomes a machine-readable record: 12 reason codes × 11 task stages, JSONL, failures never deleted.
2. **Isolate** — matched sweeps where arms differ by exactly one hypothesis, plus instrumented post-mortems that retain full note trails. A mechanism is *named* only when the experiment falsified its alternatives.
3. **Repair** — 24 typed controller knobs; each repair states its mechanism. `candidate-v3` differs from v2 by exactly one repair, selected by exactly one post-mortem.
4. **Qualify** — matched pairs on **virgin seeds asserted disjoint in code** from everything selection ever touched: Wilson intervals, **exact McNemar**, suite-level only (single episodes are never evidence here — [measured reason](#whats-real-vs-simplified--the-honesty-table)).
5. **Gate** — a release gate with pre-registered rules APPROVES or REJECTS the candidate. It rejected the first two. Its first approval had to be earned.
6. **Prove** — `crux bundle` writes hashed episodes, configs, the frozen controller spec, Radeon device evidence, and replay videos under a manifest + receipt; `crux validate` re-verifies everything **on CPU**, recomputing the headline numbers from raw episodes. Change one byte and it fails — tested.

## Verify it yourself in 60 seconds (CPU only)

No GPU required. Every claim in this README regenerates from raw records in this repository:

```bash
git clone https://github.com/Enoch208/Crux && cd Crux && uv sync
uv run pytest -q                                  # 212 tests, ~1 s
uv run crux validate evidence/manifest.json       # → 9/9 checks passed
uv run crux report evidence-dev/qualification_v3_standard_fixedmetric.jsonl \
  evidence-dev/qualification_v3_fixedmetric.jsonl \
  --baseline-version baseline-v1 --repaired-version candidate-v3 \
  --config configs/qualification.yaml             # → Release gate: APPROVED + every headline number
```

The validator recomputes aggregates and the headline regression from the raw episode files and checks 9 sha256-verified artifacts — including the Radeon device evidence (`gfx1100 via amdgpu, ROCm 7.2.1, torch 2.13.0+rocm7.2`). Tamper with one byte of an episode file and it fails. That is the point.

## The headline result

32 virgin held-out seeds per arm (401–432, disjointness from every selection seed asserted in code), matched conditions per pair, 96 environments in one batched scene, 114 s of wall-clock:

| Endpoint | `baseline-v1` | `candidate-v3` | Delta | Exact McNemar |
|---|---|---|---|---|
| Task success | 0/32 | 1/32 *(first completions — honestly n.s.)* | +3.1 pp | n.s. |
| **Reached seating verification** | 0/32 | **12/32** | **+37.5 pp** | **p = 0.0005** |

**The effect replicates exactly:** the standard suite (seeds 101–132) reads the *identical* 0/32 → 12/32, +37.5 pp, p = 0.0005. Earlier runs measured the same comparison at +25.0 to +53.1 pp across two further seed ranges. The one claim that did **not** replicate (a v3-over-v2 increment, +28.1 pp → +9.4 pp n.s.) is **withdrawn in writing** in the [gate log](docs/acceptance-gates.md). The release gate returned its first **APPROVED** on this evidence — a real primary-endpoint improvement with zero regression — and the approval, its rule, and the raw episodes all ship in the receipt.

## Architecture

Authority over the numbers flows one way: the GPU only steps physics; everything that decides, judges, or certifies is pure Python, unit-tested on CPU, and recomputable by a reviewer.

```mermaid
flowchart LR
    subgraph GPU["AMD Radeon PRO W7900 · ROCm 7.2.1 · Genesis"]
        SCENE["Batched task scene<br/>N envs, one GPU, 200k+ steps/s"]
    end
    subgraph CPU["Pure Python · CPU-testable · 212 tests"]
        POLICY["Generator policy<br/>obs in, control chunks out"]
        DRIVER["Batch driver<br/>N policies, per-env knobs"]
        TAX["Failure taxonomy<br/>12 codes x 11 stages, JSONL"]
        REPAIR["Repair space<br/>24 typed knobs, named operators"]
        QUAL["Qualification<br/>Wilson, exact McNemar, release gate"]
        EVID["Evidence bundle<br/>manifest, receipt, sha256"]
    end
    DRIVER -->|batched IK + control| SCENE
    SCENE -->|observations| DRIVER
    DRIVER <--> POLICY
    POLICY -->|episode outcomes| TAX
    TAX -->|raw episodes| QUAL
    REPAIR -->|candidate knobs| POLICY
    QUAL -->|APPROVED / REJECTED| EVID
    EVID -->|crux validate recomputes on CPU| QUAL
```

| Module | Responsibility |
|---|---|
| `crux/control` | Generator policy (yields control chunks, receives observations — CPU-testable without a simulator) + batch driver running N independent policies against one batched scene |
| `crux/failures` | 12-code × 11-stage taxonomy, episode records, JSONL recorder — every trial ever run is retained |
| `crux/repair` | 24 typed knobs, named repair operators with stated mechanisms, composing search |
| `crux/qualification` | Wilson intervals, exact McNemar on matched pairs, suite-contamination assertions, the release gate |
| `crux/evidence` | Bundle builder + the CPU validator (manifest, receipt, sha256, aggregate recomputation) |
| `crux/simulation` | Thin Genesis adapters + every gate/sweep experiment, numbered in the order they ran |
| `configs/` | Every constant in the system — the code contains no magic numbers |

## The discovery campaign — 8 mechanisms, each earned

Seventeen matched sweep rounds plus an instrumented post-mortem, ~1,000 batched episodes. Nothing here was guessed: each mechanism is named only because an experiment falsified its alternatives, and the negative results are retained beside the positive ones.

| Mechanism | Fix |
|---|---|
| Routing slip is force-invariant (−28…−72 N) | — (hypothesis class eliminated) |
| …and speed-invariant (0.06–0.60 m/s) | — (eliminated) |
| Diagonal transport wedges the strand at the gate | Lift-then-translate |
| Release recoil throws a dangling connector 50–80 mm | Grip the connector link |
| The pinch slides axially while corrections read converged | −56 N clamp → sub-mm alignment |
| The open gripper cannot pass the channel walls (stalls at −22 mm at every force) | Mouth entry + fingertip nudge |
| Single-shot regrips close on air (18/32 post-mortem episodes, gap 0.3–3.3 mm) | Re-observed grasp retries ×3 — MISSED_GRASP **19 → 6** on virgin seeds |
| Five seating methods all stall at the same 12–13.4 mm floor | The floor *was* the fully-seated position — see below |

## The metric bug — the harness audited its own spec

The finding this project is proudest of, because no amount of demo polish can fake it:

Five physically independent seating strategies — gripped push, fingertip nudge at three commanded depths, a 0.6 m/s momentum stroke, a 90° cross-grip, and towing the cable from behind — were each tried against the endgame and each falsified, **all stalling at the same 12.0–13.4 mm floor** across 512 matched episodes, the tow ending in `OVER_TENSION` against a hard stop. Independent mechanisms don't converge on one number by coincidence. The invariant equals the scene geometry exactly: a fully seated connector's *link origin* sits 13.0 mm from the socket centre, outside the 10 mm tolerance — because the success check measured the trailing joint of a 25 mm connector instead of its body. **Task success had been impossible by construction, for every controller, from day one.**

The fix changed the measured point, not the thresholds; a CPU test pins the impossibility proof so it can never regress; every suite was re-run under the corrected metric within the hour; and the pre-correction records are retained under their original run IDs. The first three completed episodes in the project's history appeared immediately — one of them [on camera, uncut](evidence-dev/render/candidate-v3-scene2-seed428.mp4).

This is the CRUX thesis in one story: the class of spec bug that ships broken robots is exactly the class an evidence-first harness catches.

## Qualification and the release gate

- **Matched pairs, always** — baseline and candidate run identical seeds and conditions; the comparison is per-pair with **exact McNemar**, never pooled proportions.
- **Virgin seeds, asserted** — `assert_heldout_uncontaminated()` fails the run if any evaluation seed ever touched selection. Three seed ranges have been burned through honestly; each new qualification opened a fresh one.
- **A gate with teeth** — pre-registered rules (max regression, required improvement, small-sample provision). It **REJECTED** `repaired-v1` (no improvement) and rejected every candidate scored under the broken metric. Its single **APPROVED** — +3.1 pp primary-endpoint improvement, −3.1 pp regression (better on both suites) — ships in the receipt beside the rule that produced it, with the n.s. caveat stated in the same breath.
- **Suite-level statistics only** — because this stack's contact rollouts are not reproducible (measured: bit-exact resets, up to 256 mm divergence in full episodes), no claim rests on a single episode. An early "reproduction PASSED" gate was retracted when the measurement said otherwise.

## Scale, on one Radeon

Measured batched throughput on the full task scene (16-link cable + Franka), two independent runs, both reported:

| n_envs | env-steps/s (run 1 / run 2) |
|---:|---:|
| 1 | 344 / 340 |
| 64 | 19,525 / 18,730 |
| 256 | 75,871 / 67,480 |
| 1024 | 219,227 / 201,691 |
| 4096 | 293,289 / (truncated) |

**~200k–293k environment-steps per second** — 590–851× a single environment, on one W7900. The 96-episode qualification with live per-environment control and batched IK takes 114 s; the discovery campaign iterated 32-episode matched sweeps every ~4 minutes, which is what made 17 rounds and ~1,000 episodes affordable in days. `rocm-smi`, sampled live mid-sweep: **GPU 100% busy** ([telemetry logs retained](evidence-dev/)). Core stages assert the resolved backend is `gs.amdgpu` and fail loudly otherwise — there is no silent CPU fallback anywhere.

## Built for any controller — including learned ones

The policy interface is a generator: observations in, control chunks out — the same shape as a VLA or RL policy's action loop. Everything downstream (taxonomy, matched suites, McNemar, release gate, hash-verified evidence) never asks how the actions were computed. The scripted controller here is the *first* policy the harness qualified — chosen deliberately, so every number in the report is attributable to the harness rather than to a model. The question CRUX answers is the one the field can't currently answer at all: *is the new checkpoint actually better, and can you prove it to someone who wasn't there?*

## Upstream contributions

Three issues filed against Genesis, each with a minimal self-contained reproduction (in [`upstream/`](upstream/)) and verbatim console logs from the ROCm rig — plus follow-up engagement as upstream evolved:

1. [genesis-world#3177](https://github.com/Genesis-Embodied-AI/genesis-world/issues/3177) — `control_dofs_position` silently does nothing on tendon-approximated Franka finger joints; the detection path (`get_dofs_kp`) raises instead of reporting.
2. [genesis-world#3178](https://github.com/Genesis-Embodied-AI/genesis-world/issues/3178) — a `stop_recording` call that raises still writes the video at teardown under `<frozen runpy>_cam_0_*.mp4` ([follow-up posted](https://github.com/Genesis-Embodied-AI/genesis-world/issues/3178#issuecomment-5192357663) after upstream's API rework).
3. [genesis-world#3179](https://github.com/Genesis-Embodied-AI/genesis-world/issues/3179) — one environment's constraint NaN kills the whole batched scene, with no failing-env index; at n_envs=4096 one bad contact destroys 4,095 healthy rollouts.

## Engineering decisions & the hard problems

The bugs that taught something, and the decisions worth defending — under one rule that was never broken: **never fake a number**.

- **A fictional config parameter.** `drag_speed_mps` never governed motion in the original controller — it only set dwell time. Implementing it faithfully *broke* routing and led straight to the diagonal-transport mechanism. Config-vs-reality drift is itself a reliability failure mode, so it's reported as one.
- **The docs lie; the installed package doesn't.** The original spec claimed Genesis had a String/Fiber cable solver. Introspection of the installed 1.3.1 package showed `SF` is Stable Fluid and no 1-D deformable exists. The spec was corrected against evidence, and the cable is honestly an articulated chain everywhere.
- **Silent no-ops cost real days.** The Franka fingers ignored position control without an exception (tendon approximation). The fix — force control — came from the error message of a *different* call. Filed upstream; the gripper has been force-controlled since.
- **One NaN kills 4,096 environments.** Genesis has no per-env quarantine, so the batch runner records the blast as per-environment `UNSTABLE_SIMULATION` and salvages every episode that finished before the explosion. Large sweeps survived only because of it.
- **Reproducibility was claimed, measured, and retracted.** A reproduction gate was recorded PASSED on one matching replay; proper measurement showed contact rollouts diverge up to 256 mm from bit-identical resets. The claim was withdrawn in writing and the whole evidence design moved to suite-level statistics — and every demo clip is labelled a *fresh rollout*, never a replay.
- **The regrasp post-mortem paid for the whole instrument.** Retaining full note trails showed 18/32 episodes dying with the pinch closing to 0.3–3.3 mm on air. One retry knob later, MISSED_GRASP fell 19 → 6 on seeds the selection never saw — and two plausible alternatives (regrip-link moves, a tip-pinch bias) were tried and falsified rather than assumed.
- **Five falsified repairs were worth more than five successes.** They triangulated the impossible metric ([above](#the-metric-bug--the-harness-audited-its-own-spec)). The campaign's negative results are not failures of the project; they are its product.
- **Pure core, effects at the edges.** Physics, IO, and GPU sit behind thin adapters; policy logic, qualification math, and evidence checks are pure functions. That is why 212 tests run in under a second with no GPU, and why a judge can re-verify the bundle on a laptop.

## What's real vs simplified — the honesty table

| Capability | Status |
|---|---|
| **17-round discovery campaign** | Real. Matched arms, ~1,000 episodes, negative results retained. (Retention caveat: sweep rounds 1–10 kept summaries, not raw files — a process error, disclosed in the gate log.) |
| **Qualification statistics** | Real. Matched pairs, exact McNemar, Wilson CIs, contamination asserted in code, recomputable via `crux report`. |
| **Release gate APPROVED** | Real, rule-based. The success difference (1/32 vs 0/32) is *not* statistically significant and the receipt says so. |
| **On-camera SUCCESS** | Real fresh rollout on virgin seed 428, uncut, in-repo. |
| **Evidence bundle** | Real. sha256 manifest + receipt; the validator recomputes headline numbers from raw episodes; tamper-tested. |
| **Throughput numbers** | Real, measured twice, up to 11% spread — ranges reported, never best-run figures. |
| **Radeon execution** | Real and asserted: core stages fail loudly unless the backend resolves to `gs.amdgpu`. Device evidence ships in the bundle. |
| The cable | A rigid articulated chain — Genesis 1.3.1 has no 1-D deformable (verified by introspection, disclosed everywhere). |
| Episode reproducibility | Not available on this stack (measured); all statistics are suite-level by design. |
| Task success rate | 1/32 on the best controller — real, first-ever, and honestly below significance. Most endgames still stall just outside tolerance. |
| Learned policies | Not included, by choice — the interface is policy-agnostic and the scripted controller keeps every number attributable to the harness. |
| Sim-to-real | No claims, anywhere in this repository. |

## Tech stack

- **Simulation:** Genesis 1.3.1 on `gs.amdgpu` — AMD Radeon PRO W7900 (gfx1100, 48 GB), ROCm 7.2.1, `torch 2.13.0+rocm7.2`.
- **Language:** Python 3.12, fully typed — `mypy` clean across 72 source files, `ruff` format + lint enforced, zero warnings.
- **Core libraries:** pydantic (frozen config/record schemas), typer (CLI), torch (batched tensors/IK only at the adapter edge).
- **Statistics:** exact McNemar and Wilson intervals implemented in-repo and unit-tested — no stats library to hide behind.
- **Testing:** pytest — 212 CPU tests in ~1 s, including the metric impossibility proof, the tamper-detection suite, and a fake-world harness that drives the entire policy without a simulator.
- **Tooling:** uv for env + reproduction; the demo pipeline (ElevenLabs narration, ffmpeg assembly, Pillow overlays) lives in [`video/`](video/).

## Project layout

```
src/crux/
  control/       # generator policy · batch driver (the controller, CPU-testable)
  failures/      # taxonomy (12 codes x 11 stages) · episode records · JSONL recorder
  repair/        # 24 typed knobs · named repair operators · composing search
  qualification/ # Wilson · exact McNemar · matched pairing · release gate
  evidence/      # bundle builder · CPU validator (manifest, receipt, sha256)
  simulation/    # Genesis adapters · gate0..gate17 experiments, in the order they ran
tests/           # 212 CPU tests — no GPU needed
configs/         # every constant in the system (task, cable, qualification)
evidence/        # the hash-verified bundle a judge validates (crux-final-4)
evidence-dev/    # raw experiment records, telemetry, renders — failures never deleted
upstream/        # minimal reproductions behind the 3 filed Genesis issues
docs/            # technical report · gate-by-gate evidence log · poster · evidence page
video/           # the demo pipeline (narration, cards, assembly) — all numbers from evidence
```

## Run it locally

The judge path needs only a CPU (see [Verify it yourself](#verify-it-yourself-in-60-seconds-cpu-only)). The GPU experiments reproduce on any ROCm machine with a supported Radeon:

```bash
uv sync
uv run python -m crux.simulation.gate0_device        # assert Radeon + ROCm + gs.amdgpu
uv run python -m crux.simulation.gate16_qualify_v3   # the headline qualification (96 envs, ~2 min)
uv run python -m crux.simulation.gate17_standard_v3  # the replication suite
uv run python -m crux.simulation.gate11_render       # fresh-rollout render clips
```

Every experiment is a numbered `gate*.py` — the exact scripts that produced the evidence, in the order they ran. The [gate log](docs/acceptance-gates.md) records what each one found, including the retractions.

## Tests

```bash
uv run pytest -q          # 212 tests, ~1 s, CPU only
```

Behaviour-first and adversarial where it matters: the policy runs end-to-end against a cooperative fake world and against worlds that miss grasps, slip cables, and over-tension; the validator suite proves one flipped byte fails the bundle; the qualification suite covers McNemar edge cases and contamination detection; and the metric correction carries a test that *proves the old metric was impossible* from the scene constants — pinned so it can never quietly return.

## Docs

[Technical report](docs/technical-report.md) · [Gate-by-gate evidence log](docs/acceptance-gates.md) · [Live evidence page](https://enoch208.github.io/Crux/) · [Poster](docs/poster.pdf) · [Upstream issues](upstream/ISSUES.md) · [Spec (PRD)](CRUX_PRD.md)

## Honesty rules this repo lives by

Every displayed number is computed from machine-readable evidence — the report, the video, the poster, and this README carry identical figures with denominators. Failed episodes are never deleted. Baselines are frozen before comparison; virgin seeds never touch selection. Claims that didn't survive measurement (episode reproducibility, a non-replicating increment) were retracted in writing, on the record, next to the results that did survive. The cable is an articulated chain, not a deformable body — and no sim-to-real claim appears anywhere in this repository.
