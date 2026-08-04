from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from crux.evidence.validator import validate_evidence

app = typer.Typer(add_completion=False, no_args_is_help=True)


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


def main() -> None:
    app()
