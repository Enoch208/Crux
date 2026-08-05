# CRUX

**Failure-discovery → repair → qualification for contact-rich robot manipulation,
end to end on one AMD Radeon GPU.**

Track 3 · Physical AI · AMD AI DevMaster Hackathon 2026 · [Demo video](evidence-dev/render/crux-demo.mp4) · [Technical report](docs/technical-report.md) · [Gate-by-gate evidence](docs/acceptance-gates.md)

A Franka arm routes an articulated cable through clip gates and seats its connector,
simulated in Genesis on a Radeon PRO W7900 (ROCm 7.2.1, `gs.amdgpu`). CRUX finds how
the controller fails, isolates each mechanism with matched batched experiments, repairs
what it can, qualifies the result on held-out conditions — and packages every number so
you can verify it yourself.

## The 60-second version

1. **The result.** A repair chain selected by the discovery loop raises seating-stage
   arrival from **0/32 to 17/32 (+53.1 pp, exact McNemar p = 1.5e-05)** on virgin
   held-out seeds, matched pairs, contamination asserted in code. The effect chain
   replicates across three independent seed ranges, and the final repair's increment
   is itself significant (+28.1 pp, p = 0.0225). Task success is **0% for all
   controllers** — reported plainly; the terminal blocker is a measured geometric
   incompatibility between the gripper span and the channel width, not a tuning gap.
2. **The scale.** ~**200k–293k environment-steps/s** on one Radeon at 4,096 batched
   environments (two runs reported, spread disclosed). The 64-episode qualification
   took 93 seconds; the discovery campaign ran 32 simultaneous episodes every ~4 min.
3. **The rigor.** Reset is bit-exact but contact rollouts are not reproducible on this
   stack (measured, and an earlier PASSED claim retracted because of it); the release
   gate rejected our first repair; every failed episode is retained; the evidence
   bundle is hash-verified and recomputes its own headline numbers.

## Verify it yourself (CPU only, no GPU required)

```bash
uv sync
uv run pytest -q                                  # 207 tests, ~1 s
uv run crux validate evidence/manifest.json       # hash + recompute the evidence bundle
uv run crux report evidence/episodes/standard-baseline.jsonl ...   # numbers from raw JSONL
```

Tamper with one byte of an episode file and `crux validate` fails. That is the point.

## What's here

| Path | What it is |
|---|---|
| `src/crux/control/` | Generator policy + batch driver — the controller, CPU-testable |
| `src/crux/failures/` | 12-code failure taxonomy, episode records, JSONL recorder |
| `src/crux/repair/` | Typed knob space, named repair operators, composing search |
| `src/crux/qualification/` | Wilson/McNemar, matched pairing, release gate |
| `src/crux/evidence/` | Bundle builder + CPU validator (manifest, receipt, hashes) |
| `src/crux/simulation/` | Genesis adapters + every gate/sweep experiment, in order |
| `upstream/` | Minimal reproductions for three Genesis findings |
| `docs/` | Technical report, acceptance gates with raw evidence |
| `configs/` | Every constant in the system |

## The discovery campaign in one table

Thirteen matched sweep rounds plus an instrumented post-mortem, ~520 batched episodes,
seven mechanisms — each isolated by an experiment that falsified the alternatives
(full detail in the report):

| Mechanism | Fix |
|---|---|
| Routing slip is force-invariant (−28…−72 N) | — |
| …and speed-invariant (0.06–0.60 m/s) | — |
| Diagonal transport wedges the strand at the gate | Lift-then-translate |
| Release recoil throws a dangling connector 50–80 mm | Grip the connector link |
| The pinch slides axially while corrections read converged | −56 N clamp → sub-mm alignment |
| The open gripper cannot pass the channel walls (stalls at −22 mm at every force) | Mouth entry + fingertip nudge; residual is geometric — documented, not hidden |
| Single-shot regrips close on air (18/32 post-mortem episodes, gap 0.3–3.3 mm) | Re-observed grasp retries (×3) — MISSED_GRASP 19 → 3 on virgin seeds |

## Honesty rules this repo lives by

Every displayed number is computed from machine-readable evidence. Failed episodes are
never deleted. Baselines are frozen before comparison; held-out seeds never touch
selection. Claims that turned out to be over-stated (episode reproducibility) were
retracted in writing. The cable is an articulated chain, not a deformable — and no
sim-to-real claim appears anywhere in this repository.
