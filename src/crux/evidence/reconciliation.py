from __future__ import annotations

from pathlib import Path

from crux.evidence.checks import CheckResult, fail, ok
from crux.evidence.manifest import Manifest, Receipt
from crux.failures.recorder import read_episodes
from crux.qualification.compare import compare_matched
from crux.qualification.suites import REGRESSION_SUITE, SuiteName

REGRESSION_TOLERANCE_PP = 1e-6


def baseline_version(manifest: Manifest, receipt: Receipt) -> str | None:
    versions = sorted(
        {
            evidence.controller_version
            for evidence in manifest.suites
            if evidence.controller_version != receipt.controller_version
        }
    )
    return versions[0] if len(versions) == 1 else None


def episodes_path(manifest: Manifest, suite: SuiteName, controller: str) -> str | None:
    for evidence in manifest.suites:
        if evidence.suite is suite and evidence.controller_version == controller:
            return evidence.episodes_path
    return None


def check_aggregates(root: Path, manifest: Manifest, receipt: Receipt) -> CheckResult:
    suite = receipt.qualification_suite
    baseline = baseline_version(manifest, receipt)
    if baseline is None:
        return fail("aggregates", "manifest does not identify exactly one baseline controller")
    arms = {
        "baseline": (baseline, receipt.baseline),
        "repaired": (receipt.controller_version, receipt.repaired),
    }
    details: list[str] = []
    for label, (controller, declared) in arms.items():
        path = episodes_path(manifest, suite, controller)
        if path is None:
            return fail("aggregates", f"manifest lacks {suite} episodes for {controller}")
        episodes = read_episodes(root / path)
        recomputed = (sum(episode.succeeded for episode in episodes), len(episodes))
        if (declared.successes, declared.episodes) != recomputed:
            return fail(
                "aggregates",
                f"receipt {label} {(declared.successes, declared.episodes)} disagrees with raw "
                f"episodes {recomputed} on {suite}",
            )
        details.append(f"{label} {recomputed[0]}/{recomputed[1]}")
    return ok("aggregates", f"{suite}: {', '.join(details)} recomputed from raw episodes")


def check_headline_regression(root: Path, manifest: Manifest, receipt: Receipt) -> CheckResult:
    baseline = baseline_version(manifest, receipt)
    if baseline is None:
        return fail(
            "headline_regression", "manifest does not identify exactly one baseline controller"
        )
    baseline_path = episodes_path(manifest, REGRESSION_SUITE, baseline)
    repaired_path = episodes_path(manifest, REGRESSION_SUITE, receipt.controller_version)
    if baseline_path is None or repaired_path is None:
        return fail("headline_regression", f"manifest lacks a matched {REGRESSION_SUITE} pair")
    comparison = compare_matched(
        read_episodes(root / baseline_path), read_episodes(root / repaired_path)
    )
    recomputed = comparison.regression_percentage_points
    if abs(recomputed - receipt.standard_regression_pp) > REGRESSION_TOLERANCE_PP:
        return fail(
            "headline_regression",
            f"receipt standard_regression_pp {receipt.standard_regression_pp} disagrees with "
            f"recomputed {recomputed}",
        )
    return ok(
        "headline_regression",
        f"standard regression {recomputed:+.2f} pp reproduced from "
        f"{comparison.pairs} matched pairs",
    )
