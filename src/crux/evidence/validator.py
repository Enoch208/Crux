from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from crux.errors import CruxError
from crux.evidence.checks import (
    CheckResult,
    check_checkpoint_identity,
    check_device_evidence,
    check_files_exist,
    check_hashes,
    check_replays,
    check_suite_separation,
    fail,
    ok,
)
from crux.evidence.manifest import load_manifest, load_receipt
from crux.evidence.reconciliation import check_aggregates, check_headline_regression

RECEIPT_FILENAME = "receipt.json"


@dataclass(frozen=True, slots=True)
class ValidationReport:
    results: tuple[CheckResult, ...]

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    @property
    def failures(self) -> tuple[CheckResult, ...]:
        return tuple(result for result in self.results if not result.passed)


def validate_evidence(manifest_path: Path) -> ValidationReport:
    root = manifest_path.parent
    try:
        manifest = load_manifest(manifest_path)
        receipt = load_receipt(root / RECEIPT_FILENAME)
    except CruxError as error:
        return ValidationReport((fail("schema", error.message),))

    structural = (
        check_files_exist(root, manifest),
        check_hashes(root, manifest),
        check_device_evidence(manifest),
        check_suite_separation(manifest),
        check_checkpoint_identity(root, manifest, receipt),
        check_replays(root, manifest),
    )
    numeric: tuple[CheckResult, ...]
    try:
        numeric = (
            check_aggregates(root, manifest, receipt),
            check_headline_regression(root, manifest, receipt),
        )
    except CruxError as error:
        numeric = (fail("aggregates", error.message),)

    schema = ok(
        "schema",
        f"manifest {manifest.manifest_version} and receipt {receipt.receipt_version} parsed "
        f"against the declared schema",
    )
    return ValidationReport((schema, *structural, *numeric))
