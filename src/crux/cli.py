from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from crux.config import load_qualification_config
from crux.errors import ErrorCode, QualificationError
from crux.evidence.validator import validate_evidence
from crux.failures.recorder import read_episodes
from crux.failures.records import EpisodeRecord
from crux.report.qualification_report import (
    build_report,
    group_by_controller,
    render_markdown,
)

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _arm(
    grouped: dict[str, list[EpisodeRecord]],
    version: str,
    path: Path,
) -> list[EpisodeRecord]:
    if version not in grouped:
        raise QualificationError(
            ErrorCode.SAMPLE_EMPTY,
            f"no episodes for controller {version!r} in {path}; available: {sorted(grouped)}",
        )
    return grouped[version]


@app.callback()
def cli() -> None:
    """CRUX reliability tooling."""


@app.command()
def validate(
    manifest: Annotated[Path, typer.Argument(help="Path to evidence/manifest.json")],
) -> None:
    """Check an evidence bundle on CPU without rerunning any GPU experiment."""
    report = validate_evidence(manifest)
    for result in report.results:
        typer.echo(f"{result.status:<4} {result.name:<22} {result.detail}")
    passed = sum(result.passed for result in report.results)
    typer.echo(f"\n{passed}/{len(report.results)} checks passed")
    if not report.passed:
        raise typer.Exit(code=1)


@app.command()
def report(
    standard: Annotated[Path, typer.Argument(help="JSONL of the standard-suite episodes")],
    heldout: Annotated[Path, typer.Argument(help="JSONL of the held-out-suite episodes")],
    baseline_version: Annotated[str, typer.Option(help="Baseline controller version")],
    repaired_version: Annotated[str, typer.Option(help="Repaired controller version")],
    config: Annotated[Path, typer.Option(help="Qualification config YAML")],
    output: Annotated[Path | None, typer.Option(help="Write markdown here instead of stdout")] = (
        None
    ),
    standard_repaired_version: Annotated[
        str | None, typer.Option(help="Repaired arm name in the standard suite, if it differs")
    ] = None,
) -> None:
    """Render the qualification report and release-gate decision from episode evidence."""
    standard_arms = group_by_controller(read_episodes(standard))
    heldout_arms = group_by_controller(read_episodes(heldout))
    document = render_markdown(
        build_report(
            _arm(standard_arms, baseline_version, standard),
            _arm(standard_arms, standard_repaired_version or repaired_version, standard),
            _arm(heldout_arms, baseline_version, heldout),
            _arm(heldout_arms, repaired_version, heldout),
            load_qualification_config(config),
        )
    )
    if output is None:
        typer.echo(document)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    typer.echo(f"wrote {output}")


def main() -> None:
    app()
