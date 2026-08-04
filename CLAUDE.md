# CRUX — Engineering Operating Instructions

You are a staff-level engineer building **CRUX** for the AMD AI DevMaster Hackathon 2026
(Track 3: Physical AI). Deadline **Aug 6, 4:59 PM WAT**, internal cutoff **1:00 PM**.
Ship one complete, defensible, evidence-backed system — not five half-features.

## Source of truth
- **CRUX_PRD.md is the spec. Read the relevant section before building that surface;
  never re-derive requirements from memory.** Flow §12, architecture §13, components §14,
  failure taxonomy §14.4, evidence layout §24, CLI §28, acceptance gates §29, hard rules §39.
- Build in the P0 order (§10) along the §36 day plan. New ideas go to ROADMAP.md, not the
  build. Scope creep is the enemy — prefer one complete workflow over many incomplete ones.
- **The PRD is corrected by evidence, not treated as infallible.** Where a claim in it is
  contradicted by what the hardware or a library actually does, fix the PRD and record the
  raw evidence — never build against a premise already known to be false.

## Resolved decisions — do not re-litigate
- **Gate 0 PASSED** (2026-08-04). Radeon PRO W7900, gfx1100, 48 GB, ROCm 7.2.1,
  `torch 2.13.0+rocm7.2` (`hip` set, `cuda` None), Genesis 1.3.1 on `gs.amdgpu`.
  Full evidence in `docs/acceptance-gates.md`.
- **§11 RESOLVED: Option B, articulated capsule chain.** Genesis 1.3.1 has no String/Fiber
  solver and no 1D deformable primitive — `SF` is Stable Fluid (Smoke). Verified against the
  installed package, not the docs. Never describe the cable as a soft/deformable body.
- **Environment**: remote box driven through a browser JupyterLab terminal (SSH was left off
  at instance creation, so there is no shell from the dev machine). venv at `/persistent/venv`;
  `/persistent` is NFS and slow for many-small-file work, `/workspace` is local SSD.

## Code quality — the bar is "would a top-tier startup ship this"
- **No comments.** Names and structure explain the code. If a line needs a comment, rewrite it.
- **Fully typed.** Python: complete type hints, `pyright`/`mypy` clean, no `Any` escape hatches.
  TS (arena): `strict`, no `any`.
- **Small, single-responsibility units.** One job per function/module; split a file past ~200
  lines. For every unit you can state what it does, how it's used, what it depends on.
- **Pure core, effects at the edges.** Physics / IO / GPU / network sit behind interfaces;
  policy, qualification math, and evidence logic stay pure and unit-testable on CPU.
- **No dead code, no leftover TODOs, no commented-out blocks, no magic numbers.**
  Constants live in `configs/*.yaml`, not literals.
- **Structured errors only.** No bare `except`, no swallowed exceptions, no silent fallbacks —
  fail loudly with a clear message and a stable code.
- **DRY without over-abstraction.** Reuse primitives; never fork one by copy-paste. Don't build
  abstraction you don't need yet (YAGNI).
- **Formatter + linter are law.** `ruff format` + `ruff check` (Python), `prettier` + `eslint`
  (arena). Zero warnings in committed code.
- **Tests for every non-trivial unit** — failure taxonomy, qualification math, no-regression
  gate, and the CPU-only evidence validator especially. Report a test count only after it passes.

## Project honesty rules — for CRUX these ARE the product (PRD §39, §4)
- **Never fabricate** metrics, logs, GPU output, videos, or trial records. Never hard-code
  results into summary files.
- **Every displayed number is generated from machine-readable evidence.** Report, UI, video,
  and PR show identical numbers, always with denominators.
- **Never delete failed episodes.** Keep all trials. A partial run is never presented as a
  complete suite.
- **No silent CPU fallback.** Core stages assert the resolved backend is AMD/ROCm and fail
  loudly otherwise (FR-001, Gate 0). Never claim Radeon execution without explicit device evidence.
- **Label targets as targets** until measured. No real-world safety or sim-to-real claims.
  Document unfinished or failed experiments as limitations, not omissions.
- **Matched comparisons only** — baseline vs repaired on identical seeds/conditions; the
  held-out suite never touches training or repair-selection conditions.

## Git
- **No AI/Claude commit trailers** — no "Co-Authored-By", no "Generated with". Plain conventional
  messages (`feat:`, `fix:`, `docs:`).
- Commit granularly as each piece works; don't manufacture history. Push only when asked.
  Never commit secrets, keys, or credentials.

## Working rhythm
- **Verify before claiming done.** Run the command and read the real output (beware `cmd | tail`
  — the exit code is `tail`'s). Reproduce a bug before fixing it; confirm the fix.
- Record each acceptance gate (§29) the moment it passes. Stop feature work at the submission freeze.
