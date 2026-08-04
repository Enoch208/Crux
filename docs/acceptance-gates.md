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

**Status:** NOT STARTED

Unblocked — builds on the Option B capsule chain.

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
