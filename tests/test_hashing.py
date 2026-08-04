from __future__ import annotations

import hashlib
from pathlib import Path

from crux.evidence.hashing import canonical_json, conditions_key, hash_file, hash_json


def test_canonical_json_is_independent_of_key_order() -> None:
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})


def test_canonical_json_has_no_incidental_whitespace() -> None:
    assert canonical_json({"a": 1, "b": [1, 2]}) == '{"a":1,"b":[1,2]}'


def test_hash_json_is_stable_across_key_order() -> None:
    assert hash_json({"seed": 1, "x": 0.5}) == hash_json({"x": 0.5, "seed": 1})


def test_hash_json_distinguishes_different_values() -> None:
    assert hash_json({"x": 0.5}) != hash_json({"x": 0.6})


def test_hash_file_matches_hashlib(tmp_path: Path) -> None:
    target = tmp_path / "payload.bin"
    payload = b"crux evidence" * 1000
    target.write_bytes(payload)
    assert hash_file(target) == hashlib.sha256(payload).hexdigest()


def test_conditions_key_ignores_parameter_ordering() -> None:
    left = conditions_key(7, {"friction": 0.4, "stiffness": 0.9})
    right = conditions_key(7, {"stiffness": 0.9, "friction": 0.4})
    assert left == right


def test_conditions_key_separates_seeds_and_parameters() -> None:
    assert conditions_key(7, {"friction": 0.4}) != conditions_key(8, {"friction": 0.4})
    assert conditions_key(7, {"friction": 0.4}) != conditions_key(7, {"friction": 0.5})
