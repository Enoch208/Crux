from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path

from pydantic import ValidationError

from crux.errors import ErrorCode, EvidenceError
from crux.failures.records import EpisodeRecord, FailureEvent


def write_episodes(path: Path, episodes: Sequence[EpisodeRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for episode in episodes:
            handle.write(episode.model_dump_json() + "\n")


def append_episode(path: Path, episode: EpisodeRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(episode.model_dump_json() + "\n")


def append_failure(path: Path, event: FailureEvent) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(event.model_dump_json() + "\n")


def _iter_lines(path: Path) -> Iterator[tuple[int, str]]:
    try:
        handle = path.open("r", encoding="utf-8")
    except FileNotFoundError as error:
        raise EvidenceError(
            ErrorCode.EVIDENCE_FILE_MISSING, f"no episode file at {path}"
        ) from error
    with handle:
        for number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if stripped:
                yield number, stripped


def read_episodes(path: Path) -> list[EpisodeRecord]:
    episodes: list[EpisodeRecord] = []
    for number, line in _iter_lines(path):
        try:
            episodes.append(EpisodeRecord.model_validate_json(line))
        except ValidationError as error:
            raise EvidenceError(
                ErrorCode.EVIDENCE_SCHEMA_INVALID,
                f"{path}:{number} is not a valid episode record: {error}",
            ) from error
    return episodes


def read_failures(path: Path) -> list[FailureEvent]:
    events: list[FailureEvent] = []
    for number, line in _iter_lines(path):
        try:
            events.append(FailureEvent.model_validate_json(line))
        except ValidationError as error:
            raise EvidenceError(
                ErrorCode.EVIDENCE_SCHEMA_INVALID,
                f"{path}:{number} is not a valid failure event: {error}",
            ) from error
    return events
