from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import torch
from torch import nn

from crux.errors import CruxError, ErrorCode
from crux.learning.dataset import Standardiser, fit_rows
from crux.learning.model import TrainingRun, assert_rocm
from crux.learning.trace import ACTION_WIDTH, TraceStep

HIDDEN_UNITS = 128
EPOCHS = 600
BATCH_SIZE = 512
LEARNING_RATE = 0.001
WEIGHT_DECAY = 1e-5
SEED = 0


def build_bc_model(feature_width: int) -> nn.Module:
    return nn.Sequential(
        nn.Linear(feature_width, HIDDEN_UNITS),
        nn.ReLU(),
        nn.Linear(HIDDEN_UNITS, HIDDEN_UNITS),
        nn.ReLU(),
        nn.Linear(HIDDEN_UNITS, ACTION_WIDTH),
    )


@dataclass(frozen=True)
class BCDataset:
    features: tuple[tuple[float, ...], ...]
    actions: tuple[tuple[float, ...], ...]
    seeds: tuple[int, ...]

    def __len__(self) -> int:
        return len(self.features)


def dataset_from_steps(steps: Sequence[TraceStep]) -> BCDataset:
    if not steps:
        raise CruxError(ErrorCode.SAMPLE_EMPTY, "no trace steps to train on")
    widths = {len(step.features) for step in steps}
    if len(widths) != 1:
        raise CruxError(ErrorCode.SAMPLE_INVALID, f"inconsistent feature widths: {sorted(widths)}")
    return BCDataset(
        features=tuple(step.features for step in steps),
        actions=tuple(step.action for step in steps),
        seeds=tuple(sorted({step.seed for step in steps})),
    )


def train_bc(
    dataset: BCDataset, device: torch.device
) -> tuple[nn.Module, Standardiser, TrainingRun]:
    torch.manual_seed(SEED)
    standardiser = fit_rows(dataset.features)
    model = build_bc_model(len(dataset.features[0]))
    model.to(device)
    features = torch.tensor(
        standardiser.apply(dataset.features), dtype=torch.float32, device=device
    )
    actions = torch.tensor(dataset.actions, dtype=torch.float32, device=device)
    criterion = nn.MSELoss()
    optimiser = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE, weight_decay=WEIGHT_DECAY)
    losses: list[float] = []
    model.train()
    for _ in range(EPOCHS):
        permutation = torch.randperm(len(dataset), device=device)
        epoch_loss = 0.0
        batches = 0
        for start in range(0, len(dataset), BATCH_SIZE):
            index = permutation[start : start + BATCH_SIZE]
            optimiser.zero_grad()
            loss = criterion(model(features[index]), actions[index])
            loss.backward()
            optimiser.step()
            epoch_loss += float(loss.item())
            batches += 1
        losses.append(epoch_loss / batches)
    return (
        model,
        standardiser,
        TrainingRun(
            losses=tuple(losses),
            device=torch.cuda.get_device_name(device),
            torch_version=torch.__version__,
            hip_version=str(getattr(torch.version, "hip", "")),
        ),
    )


def save_bc_checkpoint(
    path: Path, model: nn.Module, standardiser: Standardiser, feature_width: int
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": {key: value.cpu() for key, value in model.state_dict().items()},
            "feature_width": feature_width,
            "means": list(standardiser.means),
            "scales": list(standardiser.scales),
            "hidden_units": HIDDEN_UNITS,
        },
        path,
    )


def load_bc_predictor(path: Path, device: torch.device) -> tuple[nn.Module, Standardiser]:
    payload = torch.load(path, map_location=device, weights_only=True)
    model = build_bc_model(int(payload["feature_width"]))
    model.load_state_dict(payload["state_dict"])
    model.to(device)
    model.eval()
    standardiser = Standardiser(means=tuple(payload["means"]), scales=tuple(payload["scales"]))
    return model, standardiser


def make_predictor(
    model: nn.Module, standardiser: Standardiser, device: torch.device
) -> _TorchPredictor:
    return _TorchPredictor(model, standardiser, device)


class _TorchPredictor:
    def __init__(self, model: nn.Module, standardiser: Standardiser, device: torch.device) -> None:
        self._model = model
        self._standardiser = standardiser
        self._device = device

    def __call__(self, features: Sequence[float]) -> Sequence[float]:
        row = self._standardiser.apply([tuple(features)])
        tensor = torch.tensor(row, dtype=torch.float32, device=self._device)
        with torch.no_grad():
            output: list[float] = self._model(tensor).squeeze(0).cpu().tolist()
        return output


__all__ = [
    "BCDataset",
    "assert_rocm",
    "build_bc_model",
    "dataset_from_steps",
    "load_bc_predictor",
    "make_predictor",
    "save_bc_checkpoint",
    "train_bc",
]
