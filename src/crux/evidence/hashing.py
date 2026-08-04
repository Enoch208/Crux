from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TypeAlias

JsonValue: TypeAlias = (
    "bool | int | float | str | Sequence[JsonValue] | Mapping[str, JsonValue] | None"
)

_READ_CHUNK_BYTES = 1 << 20


def canonical_json(value: JsonValue) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def hash_json(value: JsonValue) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_READ_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def conditions_key(seed: int, environment_parameters: Mapping[str, float]) -> str:
    return hash_json({"seed": seed, "environment_parameters": dict(environment_parameters)})
