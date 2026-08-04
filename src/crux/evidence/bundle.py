from __future__ import annotations

import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from crux.errors import ErrorCode, EvidenceError
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
from crux.qualification.compare import compare_matched
from crux.qualification.release_gate import ReleaseGateResult
from crux.qualification.suites import SuiteName

MANIFEST_VERSION = "1"
RECEIPT_VERSION = "1"


def arm_summary(episodes: Sequence[EpisodeRecord]) -> ArmSummary:
    return ArmSummary(
        successes=sum(episode.succeeded for episode in episodes), episodes=len(episodes)
    )


def suite_evidence(
    episodes: Sequence[EpisodeRecord],
    relative_path: str,
) -> SuiteEvidence:
    suites = {episode.suite for episode in episodes}
    controllers = {episode.controller_version for episode in episodes}
    if len(suites) != 1 or len(controllers) != 1:
        raise EvidenceError(
            ErrorCode.EVIDENCE_SCHEMA_INVALID,
            f"{relative_path} must hold one suite and one controller, "
            f"found {sorted(suites)} and {sorted(controllers)}",
        )
    return SuiteEvidence(
        suite=suites.pop(),
        controller_version=controllers.pop(),
        episodes_path=relative_path,
        seeds=tuple(sorted(episode.seed for episode in episodes)),
    )


def file_entries(root: Path, relative_paths: Sequence[str]) -> tuple[FileEntry, ...]:
    return tuple(
        FileEntry(
            path=relative,
            sha256=hash_file(root / relative),
            size_bytes=(root / relative).stat().st_size,
        )
        for relative in relative_paths
    )


def copy_into(root: Path, source: Path, relative: str) -> str:
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return relative


@dataclass(frozen=True, slots=True)
class BundleInputs:
    heldout_baseline: str
    heldout_repaired: str
    standard_baseline: str
    standard_repaired: str
    task_config: str
    qualification_config: str
    controller_spec: str
    replays: tuple[str, ...]

    @property
    def all_paths(self) -> tuple[str, ...]:
        return (
            self.heldout_baseline,
            self.heldout_repaired,
            self.standard_baseline,
            self.standard_repaired,
            self.task_config,
            self.qualification_config,
            self.controller_spec,
            *self.replays,
        )


def load_device_evidence(path: Path) -> DeviceEvidence:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise EvidenceError(
            ErrorCode.EVIDENCE_FILE_MISSING,
            f"no device evidence at {path}; run crux.simulation.gate0_device on the Radeon box",
        ) from error
    try:
        evidence = DeviceEvidence.model_validate_json(raw)
    except ValidationError as error:
        raise EvidenceError(
            ErrorCode.EVIDENCE_SCHEMA_INVALID, f"{path} is not valid device evidence: {error}"
        ) from error
    if not evidence.is_radeon:
        raise EvidenceError(
            ErrorCode.EVIDENCE_SCHEMA_INVALID,
            f"{path} resolves to {evidence.resolved_backend!r}, which is not a Radeon backend",
        )
    return evidence


def write_arm(root: Path, episodes: Sequence[EpisodeRecord], relative: str) -> str:
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_episodes(destination, episodes)
    return relative


def write_bundle_inputs(
    root: Path,
    heldout_baseline: Sequence[EpisodeRecord],
    heldout_repaired: Sequence[EpisodeRecord],
    standard_baseline: Sequence[EpisodeRecord],
    standard_repaired: Sequence[EpisodeRecord],
    task_config: Path,
    qualification_config: Path,
    controller_spec: Path,
    replays: Sequence[Path],
) -> BundleInputs:
    return BundleInputs(
        heldout_baseline=write_arm(root, heldout_baseline, "episodes/heldout-baseline.jsonl"),
        heldout_repaired=write_arm(root, heldout_repaired, "episodes/heldout-repaired.jsonl"),
        standard_baseline=write_arm(root, standard_baseline, "episodes/standard-baseline.jsonl"),
        standard_repaired=write_arm(root, standard_repaired, "episodes/standard-repaired.jsonl"),
        task_config=copy_into(root, task_config, "configs/task.yaml"),
        qualification_config=copy_into(root, qualification_config, "configs/qualification.yaml"),
        controller_spec=copy_into(root, controller_spec, "controller/repaired.json"),
        replays=tuple(copy_into(root, replay, f"replays/{replay.name}") for replay in replays),
    )


def build_manifest(
    root: Path,
    run_id: str,
    source_commit: str,
    device: DeviceEvidence,
    relative_paths: Sequence[str],
    suites: Sequence[SuiteEvidence],
    repair_seeds: Sequence[int],
) -> Manifest:
    return Manifest(
        manifest_version=MANIFEST_VERSION,
        run_id=run_id,
        created_at=datetime.now(UTC),
        source_commit=source_commit,
        device=device,
        files=file_entries(root, relative_paths),
        suites=tuple(suites),
        repair_seeds=tuple(sorted(set(repair_seeds))),
    )


def finalise_bundle(
    root: Path,
    run_id: str,
    source_commit: str,
    device: DeviceEvidence,
    inputs: BundleInputs,
    heldout_baseline: Sequence[EpisodeRecord],
    heldout_repaired: Sequence[EpisodeRecord],
    standard_baseline: Sequence[EpisodeRecord],
    standard_repaired: Sequence[EpisodeRecord],
    repaired_version: str,
    gate: ReleaseGateResult,
) -> Path:
    manifest = build_manifest(
        root,
        run_id=run_id,
        source_commit=source_commit,
        device=device,
        relative_paths=inputs.all_paths,
        suites=(
            suite_evidence(heldout_baseline, inputs.heldout_baseline),
            suite_evidence(heldout_repaired, inputs.heldout_repaired),
            suite_evidence(standard_baseline, inputs.standard_baseline),
            suite_evidence(standard_repaired, inputs.standard_repaired),
        ),
        repair_seeds=[episode.seed for episode in standard_baseline],
    )
    manifest = manifest.model_copy(update={"replay_paths": inputs.replays})
    entry = manifest.entry_for(inputs.controller_spec)
    config_entry = manifest.entry_for(inputs.qualification_config)
    if entry is None or config_entry is None:
        raise EvidenceError(
            ErrorCode.EVIDENCE_SCHEMA_INVALID, "bundle is missing its controller or config entry"
        )
    receipt = build_receipt(
        controller_version=repaired_version,
        source_commit=source_commit,
        suite=SuiteName.HELDOUT,
        baseline=heldout_baseline,
        repaired=heldout_repaired,
        standard_baseline=standard_baseline,
        standard_repaired=standard_repaired,
        gate=gate,
        config_sha256=config_entry.sha256,
        hardware_sha256=hash_file(root / inputs.task_config),
        checkpoint_sha256=entry.sha256,
        dataset_sha256=hash_file(root / inputs.standard_baseline),
    )
    manifest_path = root / "manifest.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    (root / "receipt.json").write_text(receipt.model_dump_json(indent=2), encoding="utf-8")
    return manifest_path


def build_receipt(
    controller_version: str,
    source_commit: str,
    suite: SuiteName,
    baseline: Sequence[EpisodeRecord],
    repaired: Sequence[EpisodeRecord],
    standard_baseline: Sequence[EpisodeRecord],
    standard_repaired: Sequence[EpisodeRecord],
    gate: ReleaseGateResult,
    config_sha256: str,
    hardware_sha256: str,
    checkpoint_sha256: str,
    dataset_sha256: str,
) -> Receipt:
    return Receipt(
        receipt_version=RECEIPT_VERSION,
        controller_version=controller_version,
        source_commit=source_commit,
        checkpoint_sha256=checkpoint_sha256,
        training_dataset_sha256=dataset_sha256,
        suite_config_sha256=config_sha256,
        hardware_manifest_sha256=hardware_sha256,
        qualification_suite=suite,
        baseline=arm_summary(baseline),
        repaired=arm_summary(repaired),
        standard_regression_pp=compare_matched(
            standard_baseline, standard_repaired
        ).regression_percentage_points,
        decision=gate.decision,
        reason_codes=gate.reason_codes,
        created_at=datetime.now(UTC),
    )
