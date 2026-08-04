from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from crux.config import QualificationConfig
from crux.failures.records import EpisodeRecord
from crux.failures.taxonomy import TaskStage
from crux.qualification.compare import MatchedComparison, compare_matched
from crux.qualification.metrics import SuiteMetrics, aggregate_suite
from crux.qualification.progress import StageComparison, compare_stage_reached
from crux.qualification.release_gate import ReleaseGateResult, evaluate_release_gate

ENDPOINT = TaskStage.VERIFY_SEATED


def group_by_controller(episodes: Sequence[EpisodeRecord]) -> dict[str, list[EpisodeRecord]]:
    grouped: dict[str, list[EpisodeRecord]] = defaultdict(list)
    for episode in episodes:
        grouped[episode.controller_version].append(episode)
    return dict(grouped)


@dataclass(frozen=True, slots=True)
class QualificationReport:
    standard_success: MatchedComparison
    standard_seated: StageComparison
    heldout_success: MatchedComparison
    heldout_seated: StageComparison
    gate: ReleaseGateResult
    arm_metrics: tuple[SuiteMetrics, ...]
    confidence_level: float


def build_report(
    standard_baseline: Sequence[EpisodeRecord],
    standard_repaired: Sequence[EpisodeRecord],
    heldout_baseline: Sequence[EpisodeRecord],
    heldout_repaired: Sequence[EpisodeRecord],
    config: QualificationConfig,
) -> QualificationReport:
    standard_success = compare_matched(standard_baseline, standard_repaired)
    heldout_success = compare_matched(heldout_baseline, heldout_repaired)
    return QualificationReport(
        standard_success=standard_success,
        standard_seated=compare_stage_reached(standard_baseline, standard_repaired, ENDPOINT),
        heldout_success=heldout_success,
        heldout_seated=compare_stage_reached(heldout_baseline, heldout_repaired, ENDPOINT),
        gate=evaluate_release_gate(standard_success, heldout_success, config.release_gate),
        arm_metrics=(
            aggregate_suite(standard_baseline),
            aggregate_suite(standard_repaired),
            aggregate_suite(heldout_baseline),
            aggregate_suite(heldout_repaired),
        ),
        confidence_level=config.confidence_level,
    )


def _proportion_cell(successes: int, total: int, lower: float, upper: float) -> str:
    rate = 100.0 * successes / total
    return f"{successes}/{total} ({rate:.1f}%) [{lower * 100:.1f}, {upper * 100:.1f}]"


def render_markdown(report: QualificationReport) -> str:
    level = report.confidence_level
    lines = [
        "# CRUX qualification report",
        "",
        "Every number below is computed from the episode JSONL by "
        "`crux report`; none is transcribed by hand.",
        "",
        f"## Release gate: **{report.gate.decision}**",
        "",
    ]
    if report.gate.reason_codes:
        for reason in report.gate.reason_codes:
            lines.append(f"- `{reason}`")
    else:
        lines.append("- no blocking reasons")
    lines.extend(
        [
            "",
            f"- standard regression: {report.gate.standard_regression_pp:+.1f} pp",
            f"- additional standard failures: {report.gate.additional_standard_failures}",
            f"- generalization improvement: {report.gate.generalization_improvement_pp:+.1f} pp",
            f"- small-sample rule applied: {report.gate.small_sample_rule_applied}",
            "",
            f"## Per-arm outcomes (Wilson {level:.0%} CI)",
            "",
            "| Suite | Controller | Episodes | Success | Mean peak tension (N) |",
            "|---|---|---|---|---|",
        ]
    )
    for metrics in report.arm_metrics:
        interval = metrics.success.wilson_interval(level)
        cell = _proportion_cell(
            metrics.success.successes, metrics.success.total, interval.lower, interval.upper
        )
        lines.append(
            f"| {metrics.suite} | `{metrics.controller_version}` | {metrics.success.total} | "
            f"{cell} | {metrics.mean_max_cable_tension:.1f} |"
        )
    lines.extend(
        [
            "",
            "## Matched comparisons",
            "",
            "| Suite | Endpoint | Baseline | Repaired | Delta | McNemar p |",
            "|---|---|---|---|---|---|",
        ]
    )
    for label, success, seated in (
        ("standard", report.standard_success, report.standard_seated),
        ("heldout", report.heldout_success, report.heldout_seated),
    ):
        lines.append(
            f"| {label} | success | {success.baseline_success.successes}/{success.pairs} | "
            f"{success.repaired_success.successes}/{success.pairs} | "
            f"{success.delta_percentage_points:+.1f} pp | {success.mcnemar_p_value:.4f} |"
        )
        lines.append(
            f"| {label} | reached {ENDPOINT} | "
            f"{seated.baseline_reached.successes}/{seated.pairs} | "
            f"{seated.repaired_reached.successes}/{seated.pairs} | "
            f"{seated.delta_percentage_points:+.1f} pp | {seated.mcnemar_p_value:.4f} |"
        )
    lines.extend(
        [
            "",
            "## Failure families",
            "",
            "| Suite | Controller | Reason codes |",
            "|---|---|---|",
        ]
    )
    for metrics in report.arm_metrics:
        counts = ", ".join(f"{k} {v}" for k, v in sorted(metrics.reason_code_counts.items()))
        lines.append(f"| {metrics.suite} | `{metrics.controller_version}` | {counts} |")
    lines.append("")
    return "\n".join(lines)
