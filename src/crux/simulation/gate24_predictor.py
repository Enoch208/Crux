from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import torch

from crux.errors import CruxError, ErrorCode
from crux.failures.recorder import read_episodes
from crux.learning.dataset import build_dataset, feature_names, fit_standardiser, split_by_seed
from crux.learning.metrics import accuracy, brier_score, roc_auc, triage_at_budget
from crux.learning.model import (
    assert_rocm,
    build_model,
    checkpoint,
    predict,
    to_tensors,
    train,
)

SOURCE_PATHS: tuple[Path, ...] = (
    Path("evidence-dev/qualification_v4.jsonl"),
    Path("evidence-dev/qualification_v4_standard.jsonl"),
    Path("evidence-dev/qualification_v3_fixedmetric.jsonl"),
    Path("evidence-dev/qualification_v3_standard_fixedmetric.jsonl"),
)
HELDOUT_SEEDS = tuple(range(501, 533))
METRICS_PATH = Path("evidence-dev/failure_predictor_metrics.json")
CHECKPOINT_PATH = Path("evidence-dev/failure_predictor.pt")
TRIAGE_BUDGETS = (8, 16, 24)


def main() -> int:
    device = assert_rocm()
    records = [record for path in SOURCE_PATHS if path.exists() for record in read_episodes(path)]
    if not records:
        raise CruxError(ErrorCode.SAMPLE_EMPTY, f"no episode records found in {SOURCE_PATHS}")
    dataset = build_dataset(records)
    train_set, test_set = split_by_seed(dataset, HELDOUT_SEEDS)
    standardiser = fit_standardiser(train_set)
    print(
        f"episodes {len(dataset)} -> train {len(train_set)} (failure rate "
        f"{train_set.failure_rate:.2f}), held-out {len(test_set)} "
        f"(failure rate {test_set.failure_rate:.2f})",
        flush=True,
    )

    features, labels = to_tensors(train_set, standardiser, device)
    model = build_model(len(feature_names()))
    run = train(model, features, labels, device)
    print(
        f"trained on {run.device} · torch {run.torch_version} · HIP {run.hip_version}", flush=True
    )
    print(f"loss {run.losses[0]:.4f} -> {run.losses[-1]:.4f}", flush=True)

    test_features, _ = to_tensors(test_set, standardiser, device)
    probabilities = predict(model, test_features)
    triage: dict[str, dict[str, float]] = {}
    metrics: dict[str, object] = {
        "run_at": datetime.now(UTC).isoformat(),
        "device": run.device,
        "torch_version": run.torch_version,
        "hip_version": run.hip_version,
        "train_episodes": len(train_set),
        "heldout_episodes": len(test_set),
        "heldout_failure_rate": round(test_set.failure_rate, 4),
        "roc_auc": round(roc_auc(test_set.labels, probabilities), 4),
        "brier": round(brier_score(test_set.labels, probabilities), 4),
        "accuracy": round(accuracy(test_set.labels, probabilities), 4),
        "triage": triage,
    }
    print("\n=== held-out (seeds 501-532, never trained on) ===")
    print(
        f"  ROC AUC {metrics['roc_auc']}  ·  Brier {metrics['brier']}  ·  acc {metrics['accuracy']}"
    )
    for budget in TRIAGE_BUDGETS:
        score = triage_at_budget(test_set.labels, probabilities, budget)
        triage[str(budget)] = {
            "failures_found": score.failures_found,
            "failures_total": score.failures_total,
            "random_expectation": round(score.random_expectation, 2),
            "lift": round(score.lift, 3),
        }
        print(
            f"  run the {budget} riskiest of {len(test_set)}: finds "
            f"{score.failures_found}/{score.failures_total} failures "
            f"(random would find {score.random_expectation:.1f}, lift {score.lift:.2f}x)"
        )

    METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    torch.save(checkpoint(model, standardiser, feature_names()), CHECKPOINT_PATH)
    print(f"\nmetrics: {METRICS_PATH}\ncheckpoint: {CHECKPOINT_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
