from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from crux.config import QualificationConfig, ReleaseGateConfig
from crux.evidence.bundle import finalise_bundle, load_device_evidence, write_bundle_inputs
from crux.evidence.validator import validate_evidence
from crux.failures.records import EpisodeMetrics, EpisodeRecord
from crux.failures.taxonomy import ReasonCode, TaskStage
from crux.qualification.release_gate import evaluate_release_gate
from crux.qualification.suites import SuiteName
from crux.report.qualification_report import build_report

DEVICE = {
    "gpu_name": "AMD Radeon Graphics",
    "architecture": "gfx1100",
    "rocm_version": "7.2.1",
    "hip_version": "7.2.53211",
    "pytorch_version": "2.13.0+rocm7.2",
    "genesis_version": "1.3.1",
    "resolved_backend": "gs.amdgpu",
    "visible_gpu_count": 1,
    "vram_bytes": 51522830336,
}


def episode(seed: int, version: str, suite: SuiteName) -> EpisodeRecord:
    return EpisodeRecord(
        run_id="bundle-test",
        episode_id=f"bundle-test-{suite}-{seed}-{version}",
        seed=seed,
        controller_version=version,
        suite=suite,
        reason_code=ReasonCode.CABLE_SLIP,
        task_stage=TaskStage.ROUTE_CLIP_1,
        simulation_step=10,
        timestamp=datetime.now(UTC),
        environment_parameters={"cable_dx": 0.0},
        metrics=EpisodeMetrics(
            completion_steps=10,
            completion_seconds=0.1,
            max_cable_tension=1.0,
            max_collision_impulse=0.0,
        ),
    )


def config() -> QualificationConfig:
    return QualificationConfig(
        confidence_level=0.95,
        release_gate=ReleaseGateConfig(
            max_regression_pp=2.0,
            max_additional_failures=1,
            small_sample_episodes=60,
            require_improvement=True,
        ),
    )


def build(tmp_path: Path) -> Path:
    heldout_seeds, standard_seeds = (201, 202, 203), (101, 102, 103)
    heldout_baseline = [episode(s, "baseline-v1", SuiteName.HELDOUT) for s in heldout_seeds]
    heldout_repaired = [episode(s, "repaired-v1", SuiteName.HELDOUT) for s in heldout_seeds]
    standard_baseline = [episode(s, "baseline-v1", SuiteName.STANDARD) for s in standard_seeds]
    standard_repaired = [episode(s, "repaired-v1", SuiteName.STANDARD) for s in standard_seeds]

    source = tmp_path / "source"
    source.mkdir()
    (source / "device.json").write_text(json.dumps(DEVICE), encoding="utf-8")
    (source / "task.yaml").write_text("layout: {}\n", encoding="utf-8")
    (source / "qualification.yaml").write_text("confidence_level: 0.95\n", encoding="utf-8")
    (source / "repaired.json").write_text('{"skip_insert_regrip": 1}', encoding="utf-8")
    replay = source / "episode.mp4"
    replay.write_bytes(b"video-bytes")

    root = tmp_path / "evidence"
    root.mkdir()
    inputs = write_bundle_inputs(
        root,
        heldout_baseline=heldout_baseline,
        heldout_repaired=heldout_repaired,
        standard_baseline=standard_baseline,
        standard_repaired=standard_repaired,
        task_config=source / "task.yaml",
        qualification_config=source / "qualification.yaml",
        controller_spec=source / "repaired.json",
        replays=(replay,),
    )
    report = build_report(
        standard_baseline, standard_repaired, heldout_baseline, heldout_repaired, config()
    )
    return finalise_bundle(
        root,
        run_id="bundle-test",
        source_commit="deadbeef",
        device=load_device_evidence(source / "device.json"),
        inputs=inputs,
        heldout_baseline=heldout_baseline,
        heldout_repaired=heldout_repaired,
        standard_baseline=standard_baseline,
        standard_repaired=standard_repaired,
        repaired_version="repaired-v1",
        gate=evaluate_release_gate(
            report.standard_success, report.heldout_success, config().release_gate
        ),
    )


def test_a_freshly_built_bundle_passes_every_validator_check(tmp_path: Path) -> None:
    manifest_path = build(tmp_path)
    report = validate_evidence(manifest_path)
    failures = [f"{result.name}: {result.detail}" for result in report.failures]
    assert report.passed, failures


def test_tampering_with_an_episode_file_is_caught(tmp_path: Path) -> None:
    manifest_path = build(tmp_path)
    episodes = manifest_path.parent / "episodes" / "heldout-baseline.jsonl"
    episodes.write_text(episodes.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    report = validate_evidence(manifest_path)
    assert not report.passed
    assert any(result.name == "hashes" for result in report.failures)


def test_a_device_that_is_not_radeon_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "device.json"
    path.write_text(json.dumps({**DEVICE, "resolved_backend": "cpu"}), encoding="utf-8")
    try:
        load_device_evidence(path)
    except Exception as error:
        assert "not a Radeon backend" in str(error)
    else:
        raise AssertionError("a non-Radeon device must be rejected")
