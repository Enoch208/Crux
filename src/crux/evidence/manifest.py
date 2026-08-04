from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TypeVar

from pydantic import Field, ValidationError

from crux.errors import ErrorCode, EvidenceError
from crux.qualification.release_gate import GateDecision, GateReason
from crux.qualification.suites import SuiteName
from crux.schema import Frozen

RADEON_BACKEND_TOKENS: frozenset[str] = frozenset({"amdgpu", "gs.amdgpu", "rocm", "hip"})


class DeviceEvidence(Frozen):
    gpu_name: str = Field(min_length=1)
    architecture: str = Field(min_length=1)
    rocm_version: str = Field(min_length=1)
    hip_version: str = Field(min_length=1)
    pytorch_version: str = Field(min_length=1)
    genesis_version: str = Field(min_length=1)
    resolved_backend: str = Field(min_length=1)
    visible_gpu_count: int = Field(ge=0)
    vram_bytes: int = Field(ge=0)

    @property
    def is_radeon(self) -> bool:
        backend = self.resolved_backend.strip().lower()
        return any(token in backend for token in RADEON_BACKEND_TOKENS)


class FileEntry(Frozen):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)


class SuiteEvidence(Frozen):
    suite: SuiteName
    controller_version: str = Field(min_length=1)
    episodes_path: str = Field(min_length=1)
    seeds: tuple[int, ...]


class Manifest(Frozen):
    manifest_version: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    created_at: datetime
    source_commit: str = Field(min_length=1)
    device: DeviceEvidence
    files: tuple[FileEntry, ...]
    suites: tuple[SuiteEvidence, ...]
    repair_seeds: tuple[int, ...]
    replay_paths: tuple[str, ...] = ()

    def entry_for(self, path: str) -> FileEntry | None:
        return next((entry for entry in self.files if entry.path == path), None)

    def seeds_for(self, suite: SuiteName, controller_version: str) -> tuple[int, ...]:
        for evidence in self.suites:
            if evidence.suite is suite and evidence.controller_version == controller_version:
                return evidence.seeds
        return ()


class ArmSummary(Frozen):
    successes: int = Field(ge=0)
    episodes: int = Field(ge=0)


class Receipt(Frozen):
    receipt_version: str = Field(min_length=1)
    controller_version: str = Field(min_length=1)
    source_commit: str = Field(min_length=1)
    checkpoint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    training_dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    suite_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    hardware_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    qualification_suite: SuiteName
    baseline: ArmSummary
    repaired: ArmSummary
    standard_regression_pp: float
    decision: GateDecision
    reason_codes: tuple[GateReason, ...]
    created_at: datetime


ModelT = TypeVar("ModelT", bound=Frozen)


def _load(path: Path, model: type[ModelT], label: str) -> ModelT:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise EvidenceError(ErrorCode.EVIDENCE_FILE_MISSING, f"no {label} at {path}") from error
    try:
        return model.model_validate_json(raw)
    except ValidationError as error:
        raise EvidenceError(
            ErrorCode.EVIDENCE_SCHEMA_INVALID, f"{path} is not a valid {label}: {error}"
        ) from error


def load_manifest(path: Path) -> Manifest:
    return _load(path, Manifest, "manifest")


def load_receipt(path: Path) -> Receipt:
    return _load(path, Receipt, "receipt")
