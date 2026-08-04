from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import Field, ValidationError

from crux.errors import ConfigError, ErrorCode
from crux.schema import Frozen


class ReleaseGateConfig(Frozen):
    max_regression_pp: float = Field(ge=0.0)
    max_additional_failures: int = Field(ge=0)
    small_sample_episodes: int = Field(ge=0)
    require_improvement: bool


class QualificationConfig(Frozen):
    confidence_level: float = Field(gt=0.0, lt=1.0)
    release_gate: ReleaseGateConfig


def load_qualification_config(path: Path) -> QualificationConfig:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise ConfigError(ErrorCode.CONFIG_MISSING, f"no configuration at {path}") from error
    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as error:
        raise ConfigError(ErrorCode.CONFIG_INVALID, f"{path} is not valid YAML: {error}") from error
    try:
        return QualificationConfig.model_validate(parsed)
    except ValidationError as error:
        raise ConfigError(
            ErrorCode.CONFIG_INVALID, f"{path} does not match the qualification schema: {error}"
        ) from error
