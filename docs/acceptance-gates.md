# Acceptance Gates (PRD §29)

Each gate is recorded the moment it passes, with the raw evidence that justified it.

## Gate 0 — Hardware

**Status:** PASSED — 2026-08-04 12:16 UTC

| Requirement | Evidence |
|---|---|
| Radeon GPU visible | `rocm-smi`: GPU[0] AMD Radeon Graphics, model `0x744b`, GFX version `gfx1100` |
| VRAM | 51,522,830,336 B (47.98 GB) |
| ROCm operational | `/opt/rocm/.info/version` → `7.2.1` |
| PyTorch on Radeon | `torch 2.13.0+rocm7.2` installed from the `rocm7.2` wheel index (Python 3.12.3) |
| Genesis resolves to `gs.amdgpu` | `Running on [AMD Radeon Graphics] with backend gs.amdgpu. Device memory: 47.98 GB.` |
| Genesis version | 1.3.1 (quadrants 1.2.0) |
| No core-stage CPU fallback | Genesis reported the amdgpu backend directly; no fallback warning emitted |

Host: `u-11389-f00f5508`, 128 CPU cores, 503 GB RAM, `/workspace` 98 GB local SSD,
`/persistent` 100 GB NFS (SFS Turbo). Environment installed at `/persistent/venv`.

**Outstanding:** the post-install assertion that `torch.version.hip` survived the
`genesis-world` install has not yet been captured. `genesis-world` pulled
`nvidia-cuda-nvrtc-cu12` and `nvidia-nvjitlink-cu12`, but did not reinstall torch.

## Gate 1 — Physical scene

**Status:** NOT STARTED

Blocked on the §11 cable representation decision (native String/Fiber vs articulated
capsule-chain fallback).

## Gate 2 — Baseline capability

**Status:** NOT STARTED

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
