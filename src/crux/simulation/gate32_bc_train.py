from __future__ import annotations

import json
from pathlib import Path

from crux.learning.bc import (
    assert_rocm,
    dataset_from_steps,
    save_bc_checkpoint,
    train_bc,
)
from crux.learning.trace import read_trace

TRACES_PATH = Path("evidence-dev/bc_traces.jsonl")
CHECKPOINT_PATH = Path("evidence-dev/bc_policy.pt")
METRICS_PATH = Path("evidence-dev/bc_training.json")
REPORT_EVERY = 100


def main() -> int:
    device = assert_rocm()
    steps = list(read_trace(TRACES_PATH))
    dataset = dataset_from_steps(steps)
    print(
        f"=== behaviour cloning on the Radeon: {len(dataset)} steps "
        f"from {len(dataset.seeds)} successful expert episodes ===",
        flush=True,
    )

    model, standardiser, run = train_bc(dataset, device)
    for epoch in range(0, len(run.losses), REPORT_EVERY):
        print(f"  epoch {epoch:4d}: loss {run.losses[epoch]:.5f}", flush=True)
    print(f"  final loss: {run.losses[-1]:.5f}  ·  device: {run.device}", flush=True)

    save_bc_checkpoint(CHECKPOINT_PATH, model, standardiser, feature_width=len(dataset.features[0]))
    METRICS_PATH.write_text(
        json.dumps(
            {
                "trace_steps": len(dataset),
                "expert_episodes": len(dataset.seeds),
                "expert_seeds": list(dataset.seeds),
                "feature_width": len(dataset.features[0]),
                "final_loss": run.losses[-1],
                "first_loss": run.losses[0],
                "epochs": len(run.losses),
                "device": run.device,
                "torch_version": run.torch_version,
                "hip_version": run.hip_version,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"  checkpoint: {CHECKPOINT_PATH}")
    print(f"  metrics: {METRICS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
