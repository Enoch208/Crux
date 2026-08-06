from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from crux.cli import app
from crux.repair.knobs import ControllerKnobs

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "task.yaml"
runner = CliRunner()


def test_spec_prints_a_controller_that_parses_back_into_knobs() -> None:
    result = runner.invoke(app, ["spec", "candidate-v4", "--task-config", str(CONFIG_PATH)])
    assert result.exit_code == 0
    assert ControllerKnobs.model_validate_json(result.stdout).nudge_seat == 1


def test_spec_writes_the_file_the_bundle_consumes(tmp_path: Path) -> None:
    destination = tmp_path / "nested" / "candidate.json"
    result = runner.invoke(
        app,
        ["spec", "candidate-v4", "--out", str(destination), "--task-config", str(CONFIG_PATH)],
    )
    assert result.exit_code == 0
    assert json.loads(destination.read_text(encoding="utf-8"))["nudge_rounds"] == 2


def test_spec_refuses_an_unknown_controller() -> None:
    result = runner.invoke(app, ["spec", "candidate-v9", "--task-config", str(CONFIG_PATH)])
    assert result.exit_code != 0
    assert "CONTROLLER_UNKNOWN" in str(result.exception)
