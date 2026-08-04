from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from crux.evidence.hashing import hash_file
from crux.evidence.manifest import Manifest, Receipt
from crux.qualification.suites import SuiteName


class CheckStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    status: CheckStatus
    detail: str

    @property
    def passed(self) -> bool:
        return self.status is CheckStatus.PASS


def ok(name: str, detail: str) -> CheckResult:
    return CheckResult(name, CheckStatus.PASS, detail)


def fail(name: str, detail: str) -> CheckResult:
    return CheckResult(name, CheckStatus.FAIL, detail)


def check_files_exist(root: Path, manifest: Manifest) -> CheckResult:
    missing = [entry.path for entry in manifest.files if not (root / entry.path).is_file()]
    if missing:
        return fail("files_exist", f"{len(missing)} declared file(s) missing: {missing[:5]}")
    return ok("files_exist", f"all {len(manifest.files)} declared files present")


def check_hashes(root: Path, manifest: Manifest) -> CheckResult:
    problems: list[str] = []
    for entry in manifest.files:
        candidate = root / entry.path
        if not candidate.is_file():
            problems.append(f"{entry.path} (missing)")
        elif hash_file(candidate) != entry.sha256:
            problems.append(f"{entry.path} (sha256)")
        elif candidate.stat().st_size != entry.size_bytes:
            problems.append(f"{entry.path} (size)")
    if problems:
        return fail("hashes", f"{len(problems)} file(s) failed verification: {problems[:5]}")
    return ok("hashes", f"{len(manifest.files)} files match their recorded sha256 and size")


def check_device_evidence(manifest: Manifest) -> CheckResult:
    device = manifest.device
    if not device.is_radeon:
        return fail(
            "device_evidence",
            f"resolved backend {device.resolved_backend!r} is not an AMD/ROCm backend",
        )
    if device.visible_gpu_count < 1:
        return fail("device_evidence", "manifest reports zero visible GPUs")
    return ok(
        "device_evidence",
        f"{device.gpu_name} ({device.architecture}) via {device.resolved_backend}, "
        f"ROCm {device.rocm_version}, torch {device.pytorch_version}",
    )


def check_suite_separation(manifest: Manifest) -> CheckResult:
    heldout_seeds = {
        seed
        for evidence in manifest.suites
        if evidence.suite is SuiteName.HELDOUT
        for seed in evidence.seeds
    }
    if not heldout_seeds:
        return fail("suite_separation", "manifest declares no held-out seeds")
    overlap = sorted(heldout_seeds & set(manifest.repair_seeds))
    if overlap:
        return fail(
            "suite_separation",
            f"{len(overlap)} held-out seed(s) were also used for repair: {overlap[:10]}",
        )
    return ok(
        "suite_separation",
        f"{len(heldout_seeds)} held-out seeds disjoint from "
        f"{len(manifest.repair_seeds)} repair seeds",
    )


def check_checkpoint_identity(root: Path, manifest: Manifest, receipt: Receipt) -> CheckResult:
    matches = [entry for entry in manifest.files if entry.sha256 == receipt.checkpoint_sha256]
    if not matches:
        return fail(
            "checkpoint_identity",
            f"receipt checkpoint {receipt.checkpoint_sha256[:12]} matches no manifest file",
        )
    entry = matches[0]
    candidate = root / entry.path
    if not candidate.is_file():
        return fail("checkpoint_identity", f"checkpoint {entry.path} is declared but missing")
    if hash_file(candidate) != receipt.checkpoint_sha256:
        return fail("checkpoint_identity", f"{entry.path} does not hash to the receipt checkpoint")
    return ok("checkpoint_identity", f"receipt checkpoint resolves to {entry.path}")


def check_replays(root: Path, manifest: Manifest) -> CheckResult:
    if not manifest.replay_paths:
        return fail("replays", "manifest declares no replay files")
    problems: list[str] = []
    for path in manifest.replay_paths:
        candidate = root / path
        if not candidate.is_file():
            problems.append(f"{path} (missing)")
        elif candidate.stat().st_size == 0:
            problems.append(f"{path} (empty)")
        elif manifest.entry_for(path) is None:
            problems.append(f"{path} (unhashed)")
    if problems:
        return fail("replays", f"{len(problems)} replay problem(s): {problems[:5]}")
    return ok("replays", f"{len(manifest.replay_paths)} replays present, non-empty and hashed")
