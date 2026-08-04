from __future__ import annotations

import json
from pathlib import Path

import pytest

from crux.evidence.manifest import DeviceEvidence
from crux.evidence.validator import ValidationReport, validate_evidence
from tests.evidence_tree import RADEON_DEVICE, build_evidence_tree

EXPECTED_CHECKS = {
    "schema",
    "files_exist",
    "hashes",
    "device_evidence",
    "suite_separation",
    "checkpoint_identity",
    "replays",
    "aggregates",
    "headline_regression",
}


def failed_check_names(report: ValidationReport) -> set[str]:
    return {result.name for result in report.failures}


def test_a_clean_evidence_tree_passes_every_check(tmp_path: Path) -> None:
    tree = build_evidence_tree(tmp_path / "evidence")
    report = validate_evidence(tree.manifest_path)
    assert {result.name for result in report.results} == EXPECTED_CHECKS
    assert report.passed, failed_check_names(report)


def test_the_validator_covers_every_fr014_dimension(tmp_path: Path) -> None:
    tree = build_evidence_tree(tmp_path / "evidence")
    report = validate_evidence(tree.manifest_path)
    assert len(report.results) == len(EXPECTED_CHECKS)


def test_a_tampered_raw_file_fails_hash_verification(tmp_path: Path) -> None:
    tree = build_evidence_tree(tmp_path / "evidence")
    target = tree.root / "raw/heldout_repaired.jsonl"
    target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    report = validate_evidence(tree.manifest_path)
    assert "hashes" in failed_check_names(report)


def test_a_deleted_file_fails_existence(tmp_path: Path) -> None:
    tree = build_evidence_tree(tmp_path / "evidence")
    (tree.root / "checkpoints/repaired_policy.pt").unlink()
    report = validate_evidence(tree.manifest_path)
    assert {"files_exist", "hashes", "checkpoint_identity"} <= failed_check_names(report)


def test_a_cpu_backend_fails_device_evidence(tmp_path: Path) -> None:
    cpu_device = DeviceEvidence.model_validate(
        {**RADEON_DEVICE.model_dump(), "resolved_backend": "gs.cpu"}
    )
    tree = build_evidence_tree(tmp_path / "evidence", device=cpu_device)
    report = validate_evidence(tree.manifest_path)
    assert "device_evidence" in failed_check_names(report)


def test_an_nvidia_backend_fails_device_evidence(tmp_path: Path) -> None:
    cuda_device = DeviceEvidence.model_validate(
        {**RADEON_DEVICE.model_dump(), "resolved_backend": "gs.cuda"}
    )
    tree = build_evidence_tree(tmp_path / "evidence", device=cuda_device)
    report = validate_evidence(tree.manifest_path)
    assert "device_evidence" in failed_check_names(report)


def test_a_heldout_seed_used_for_repair_fails_suite_separation(tmp_path: Path) -> None:
    tree = build_evidence_tree(tmp_path / "evidence", repair_seeds=[101, 102, 103])
    report = validate_evidence(tree.manifest_path)
    assert "suite_separation" in failed_check_names(report)


def test_an_inflated_headline_number_fails_aggregates(tmp_path: Path) -> None:
    tree = build_evidence_tree(tmp_path / "evidence")
    receipt = json.loads(tree.receipt_path.read_text(encoding="utf-8"))
    receipt["repaired"]["successes"] = 59
    tree.receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    report = validate_evidence(tree.manifest_path)
    assert "aggregates" in failed_check_names(report)


def test_a_misreported_regression_fails_the_headline_check(tmp_path: Path) -> None:
    tree = build_evidence_tree(tmp_path / "evidence")
    receipt = json.loads(tree.receipt_path.read_text(encoding="utf-8"))
    receipt["standard_regression_pp"] = -5.0
    tree.receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    report = validate_evidence(tree.manifest_path)
    assert "headline_regression" in failed_check_names(report)


def test_a_real_standard_regression_is_reported_faithfully(tmp_path: Path) -> None:
    tree = build_evidence_tree(tmp_path / "evidence", standard_successes=(58, 55))
    report = validate_evidence(tree.manifest_path)
    assert report.passed, failed_check_names(report)
    headline = next(r for r in report.results if r.name == "headline_regression")
    assert "+5.00 pp" in headline.detail


def test_a_foreign_checkpoint_fails_identity(tmp_path: Path) -> None:
    tree = build_evidence_tree(tmp_path / "evidence")
    receipt = json.loads(tree.receipt_path.read_text(encoding="utf-8"))
    receipt["checkpoint_sha256"] = "f" * 64
    tree.receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    report = validate_evidence(tree.manifest_path)
    assert "checkpoint_identity" in failed_check_names(report)


def test_a_missing_replay_fails(tmp_path: Path) -> None:
    tree = build_evidence_tree(tmp_path / "evidence")
    (tree.root / "replays/baseline_failure.mp4").unlink()
    report = validate_evidence(tree.manifest_path)
    assert "replays" in failed_check_names(report)


def test_a_missing_receipt_fails_schema_and_stops(tmp_path: Path) -> None:
    tree = build_evidence_tree(tmp_path / "evidence")
    tree.receipt_path.unlink()
    report = validate_evidence(tree.manifest_path)
    assert failed_check_names(report) == {"schema"}


def test_a_malformed_manifest_fails_schema(tmp_path: Path) -> None:
    tree = build_evidence_tree(tmp_path / "evidence")
    tree.manifest_path.write_text('{"manifest_version": "1.0"}', encoding="utf-8")
    report = validate_evidence(tree.manifest_path)
    assert failed_check_names(report) == {"schema"}


@pytest.mark.parametrize("truncate_to", [0, 30])
def test_partial_episode_files_are_caught(tmp_path: Path, truncate_to: int) -> None:
    tree = build_evidence_tree(tmp_path / "evidence")
    target = tree.root / "raw/heldout_repaired.jsonl"
    kept = target.read_text(encoding="utf-8").splitlines()[:truncate_to]
    target.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    report = validate_evidence(tree.manifest_path)
    assert {"hashes", "aggregates"} <= failed_check_names(report)
