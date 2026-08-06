from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import torch
from torch import nn

from crux.errors import BackendError, ErrorCode
from crux.learning.dataset import Dataset, Standardiser

HIDDEN_UNITS = 32
EPOCHS = 400
LEARNING_RATE = 0.01
WEIGHT_DECAY = 1e-4
SEED = 0


@dataclass(frozen=True)
class TrainingRun:
    losses: tuple[float, ...]
    device: str
    torch_version: str
    hip_version: str


def assert_rocm() -> torch.device:
    """Fail loudly unless training will run on a Radeon through ROCm."""
    hip = getattr(torch.version, "hip", None)
    if not hip:
        raise BackendError(
            ErrorCode.BACKEND_NOT_RADEON,
            f"torch {torch.__version__} is not a ROCm build (torch.version.hip is unset)",
        )
    if not torch.cuda.is_available():
        raise BackendError(
            ErrorCode.GPU_NOT_VISIBLE, "no ROCm device visible to torch; refusing to train on CPU"
        )
    return torch.device("cuda")


def build_model(width: int) -> nn.Module:
    return nn.Sequential(
        nn.Linear(width, HIDDEN_UNITS),
        nn.ReLU(),
        nn.Linear(HIDDEN_UNITS, HIDDEN_UNITS),
        nn.ReLU(),
        nn.Linear(HIDDEN_UNITS, 1),
    )


def to_tensors(
    dataset: Dataset, standardiser: Standardiser, device: torch.device
) -> tuple[torch.Tensor, torch.Tensor]:
    rows = standardiser.apply(dataset.rows)
    features = torch.tensor(rows, dtype=torch.float32, device=device)
    labels = torch.tensor(dataset.labels, dtype=torch.float32, device=device).unsqueeze(1)
    return features, labels


def train(
    model: nn.Module, features: torch.Tensor, labels: torch.Tensor, device: torch.device
) -> TrainingRun:
    torch.manual_seed(SEED)
    model.to(device)
    positives = float(labels.sum().item())
    negatives = float(labels.numel() - positives)
    weight = torch.tensor(
        [negatives / positives if positives > 0 else 1.0], dtype=torch.float32, device=device
    )
    criterion = nn.BCEWithLogitsLoss(pos_weight=weight)
    optimiser = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE, weight_decay=WEIGHT_DECAY)
    losses: list[float] = []
    model.train()
    for _ in range(EPOCHS):
        optimiser.zero_grad()
        loss = criterion(model(features), labels)
        loss.backward()
        optimiser.step()
        losses.append(float(loss.item()))
    return TrainingRun(
        losses=tuple(losses),
        device=torch.cuda.get_device_name(device),
        torch_version=torch.__version__,
        hip_version=str(getattr(torch.version, "hip", "")),
    )


def predict(model: nn.Module, features: torch.Tensor) -> list[float]:
    model.eval()
    with torch.no_grad():
        probabilities: list[float] = torch.sigmoid(model(features)).squeeze(1).cpu().tolist()
    return probabilities


def checkpoint(
    model: nn.Module, standardiser: Standardiser, names: Sequence[str]
) -> dict[str, object]:
    return {
        "state_dict": {key: value.cpu() for key, value in model.state_dict().items()},
        "feature_names": list(names),
        "means": list(standardiser.means),
        "scales": list(standardiser.scales),
        "hidden_units": HIDDEN_UNITS,
    }
