from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from crux.evidence.hashing import hash_file
from crux.evidence.manifest import (
    ArmSummary,
    DeviceEvidence,
    FileEntry,
    Manifest,
    Receipt,
    SuiteEvidence,
)
from crux.failures.recorder import write_episodes
from crux.failures.records import EpisodeRecord
from crux.qualification.release_gate import GateDecision
from crux.qualification.suites import SuiteName
from tests.factories import FIXED_TIME, make_arm

BASELINE = "baseline-v1"
REPAIRED = "repair-v1"
STANDARD_FIRST_SEED = 1
HELDOUT_FIRST_SEED = 101
REPAIR_SEEDS = tuple(range(201, 211))

RADEON_DEVICE = DeviceEvidence(
    gpu_name="AMD Radeon PRO W7900",
    architecture="gfx1100",
    rocm_version="6.2.0",
    hip_version="6.2.41133",
    pytorch_version="2.5.1+rocm6.2",
    genesis_version="0.2.1",
    resolved_backend="gs.amdgpu",
    visible_gpu_count=1,
    vram_bytes=48 * 1024**3,
)


@dataclass(frozen=True, slots=True)
class EvidenceTree:
    root: Path
    manifest_path: Path
    receipt_path: Path


def _entry(root: Path, relative: str) -> FileEntry:
    target = root / relative
    return FileEntry(path=relative, sha256=hash_file(target), size_bytes=target.stat().st_size)


def _write_bytes(root: Path, relative: str, payload: bytes) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)


def _arm(
    successes: int, total: int, controller: str, suite: SuiteName, first_seed: int
) -> list[EpisodeRecord]:
    return make_arm(
        successes,
        total - successes,
        controller_version=controller,
        suite=suite,
        first_seed=first_seed,
    )


def build_evidence_tree(
    root: Path,
    *,
    standard_successes: tuple[int, int] = (58, 58),
    standard_total: int = 60,
    heldout_successes: tuple[int, int] = (30, 45),
    heldout_total: int = 60,
    repair_seeds: Sequence[int] = REPAIR_SEEDS,
    device: DeviceEvidence = RADEON_DEVICE,
) -> EvidenceTree:
    root.mkdir(parents=True, exist_ok=True)
    arms = {
        ("raw/standard_baseline.jsonl", SuiteName.STANDARD, BASELINE): _arm(
            standard_successes[0], standard_total, BASELINE, SuiteName.STANDARD, STANDARD_FIRST_SEED
        ),
        ("raw/standard_repaired.jsonl", SuiteName.STANDARD, REPAIRED): _arm(
            standard_successes[1], standard_total, REPAIRED, SuiteName.STANDARD, STANDARD_FIRST_SEED
        ),
        ("raw/heldout_baseline.jsonl", SuiteName.HELDOUT, BASELINE): _arm(
            heldout_successes[0], heldout_total, BASELINE, SuiteName.HELDOUT, HELDOUT_FIRST_SEED
        ),
        ("raw/heldout_repaired.jsonl", SuiteName.HELDOUT, REPAIRED): _arm(
            heldout_successes[1], heldout_total, REPAIRED, SuiteName.HELDOUT, HELDOUT_FIRST_SEED
        ),
    }
    for (relative, _, _), episodes in arms.items():
        write_episodes(root / relative, episodes)

    _write_bytes(root, "checkpoints/repaired_policy.pt", b"residual-policy-weights")
    _write_bytes(root, "raw/repair_dataset.jsonl", b'{"observation":[0.0],"correction":[0.01]}\n')
    _write_bytes(root, "configs/heldout_suite.yaml", b"episodes: 60\n")
    _write_bytes(root, "environment/hardware.json", b'{"gpu":"AMD Radeon PRO W7900"}\n')
    _write_bytes(root, "replays/baseline_failure.mp4", b"\x00\x00\x00\x18ftypmp42fake")
    _write_bytes(root, "replays/repaired_same_seed.mp4", b"\x00\x00\x00\x18ftypmp42fake")

    replay_paths = ("replays/baseline_failure.mp4", "replays/repaired_same_seed.mp4")
    tracked = (
        *(relative for relative, _, _ in arms),
        "checkpoints/repaired_policy.pt",
        "raw/repair_dataset.jsonl",
        "configs/heldout_suite.yaml",
        "environment/hardware.json",
        *replay_paths,
    )
    manifest = Manifest(
        manifest_version="1.0",
        run_id="run-formal-1",
        created_at=FIXED_TIME,
        source_commit="0" * 40,
        device=device,
        files=tuple(_entry(root, relative) for relative in tracked),
        suites=tuple(
            SuiteEvidence(
                suite=suite,
                controller_version=controller,
                episodes_path=relative,
                seeds=tuple(episode.seed for episode in episodes),
            )
            for (relative, suite, controller), episodes in arms.items()
        ),
        repair_seeds=tuple(repair_seeds),
        replay_paths=replay_paths,
    )
    standard_baseline = standard_successes[0] / standard_total
    standard_repaired = standard_successes[1] / standard_total
    receipt = Receipt(
        receipt_version="1.0",
        controller_version=REPAIRED,
        source_commit="0" * 40,
        checkpoint_sha256=hash_file(root / "checkpoints/repaired_policy.pt"),
        training_dataset_sha256=hash_file(root / "raw/repair_dataset.jsonl"),
        suite_config_sha256=hash_file(root / "configs/heldout_suite.yaml"),
        hardware_manifest_sha256=hash_file(root / "environment/hardware.json"),
        qualification_suite=SuiteName.HELDOUT,
        baseline=ArmSummary(successes=heldout_successes[0], episodes=heldout_total),
        repaired=ArmSummary(successes=heldout_successes[1], episodes=heldout_total),
        standard_regression_pp=100.0 * (standard_baseline - standard_repaired),
        decision=GateDecision.APPROVED,
        reason_codes=(),
        created_at=FIXED_TIME,
    )
    manifest_path = root / "manifest.json"
    receipt_path = root / "receipt.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    receipt_path.write_text(receipt.model_dump_json(indent=2), encoding="utf-8")
    return EvidenceTree(root=root, manifest_path=manifest_path, receipt_path=receipt_path)
