from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from crux.config import load_qualification_config
from crux.errors import ErrorCode, QualificationError
from crux.evidence.bundle import (
    finalise_bundle,
    load_device_evidence,
    write_bundle_inputs,
)
from crux.evidence.validator import validate_evidence
from crux.failures.recorder import read_episodes
from crux.failures.records import EpisodeRecord
from crux.repair.candidates import CANDIDATES, knobs_for
from crux.report.qualification_report import (
    build_report,
    group_by_controller,
    render_markdown,
)
from crux.simulation.taskconfig import TASK_CONFIG_PATH, load_task_config

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
def spec(
    controller: Annotated[str, typer.Argument(help=f"Controller version: {sorted(CANDIDATES)}")],
    out: Annotated[
        Path | None, typer.Option(help="Write the knob spec here instead of stdout")
    ] = None,
    task_config: Annotated[Path, typer.Option(help="Task config YAML")] = TASK_CONFIG_PATH,
) -> None:
    """Rebuild a named controller's full knob spec on CPU, from its recorded overrides."""
    document = knobs_for(controller, load_task_config(task_config)).model_dump_json(indent=2)
    if out is None:
        typer.echo(document)
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(document + "\n", encoding="utf-8")
    typer.echo(f"wrote {out}")


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


@app.command()
def bundle(
    heldout: Annotated[Path, typer.Argument(help="JSONL of the held-out-suite episodes")],
    standard: Annotated[Path, typer.Argument(help="JSONL of the standard-suite episodes")],
    device: Annotated[Path, typer.Option(help="device.json written by gate0_device")],
    task_config: Annotated[Path, typer.Option(help="Task config YAML")],
    qualification_config: Annotated[Path, typer.Option(help="Qualification config YAML")],
    baseline_version: Annotated[str, typer.Option(help="Baseline controller version")],
    repaired_version: Annotated[str, typer.Option(help="Repaired controller version")],
    run_id: Annotated[str, typer.Option(help="Run identifier")],
    commit: Annotated[str, typer.Option(help="Source commit the evidence came from")],
    controller_spec: Annotated[Path, typer.Option(help="JSON of the repaired controller knobs")],
    replay: Annotated[list[Path], typer.Option(help="Replay video to include")],
    out: Annotated[Path, typer.Option(help="Bundle directory to create")] = Path("evidence"),
    standard_repaired_version: Annotated[
        str | None, typer.Option(help="Repaired arm name in the standard suite, if it differs")
    ] = None,
) -> None:
    """Assemble a hash-verified evidence bundle that `crux validate` can check on CPU."""
    heldout_arms = group_by_controller(read_episodes(heldout))
    standard_arms = group_by_controller(read_episodes(standard))
    standard_repaired_name = standard_repaired_version or repaired_version

    out.mkdir(parents=True, exist_ok=True)
    device_evidence = load_device_evidence(device)
    inputs = write_bundle_inputs(
        out,
        heldout_baseline=_arm(heldout_arms, baseline_version, heldout),
        heldout_repaired=_arm(heldout_arms, repaired_version, heldout),
        standard_baseline=_arm(standard_arms, baseline_version, standard),
        standard_repaired=_arm(standard_arms, standard_repaired_name, standard),
        task_config=task_config,
        qualification_config=qualification_config,
        controller_spec=controller_spec,
        replays=tuple(replay),
    )
    report = build_report(
        _arm(standard_arms, baseline_version, standard),
        _arm(standard_arms, standard_repaired_name, standard),
        _arm(heldout_arms, baseline_version, heldout),
        _arm(heldout_arms, repaired_version, heldout),
        load_qualification_config(qualification_config),
    )
    written_manifest = finalise_bundle(
        out,
        run_id=run_id,
        source_commit=commit,
        device=device_evidence,
        inputs=inputs,
        heldout_baseline=_arm(heldout_arms, baseline_version, heldout),
        heldout_repaired=_arm(heldout_arms, repaired_version, heldout),
        standard_baseline=_arm(standard_arms, baseline_version, standard),
        standard_repaired=_arm(standard_arms, standard_repaired_name, standard),
        repaired_version=repaired_version,
        gate=report.gate,
    )
    typer.echo(f"wrote {written_manifest}")
    typer.echo(f"release gate: {report.gate.decision}")


def main() -> None:
    app()
