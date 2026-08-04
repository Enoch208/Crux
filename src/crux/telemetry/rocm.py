from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from crux.errors import BackendError, ErrorCode

ROCM_VERSION_FILE = Path("/opt/rocm/.info/version")
ROCM_SMI = "rocm-smi"
SMI_TIMEOUT_SECONDS = 20


@dataclass(frozen=True, slots=True)
class TorchEvidence:
    pytorch_version: str
    hip_version: str
    gpu_name: str
    architecture: str
    visible_gpu_count: int
    vram_bytes: int


def probe_torch() -> TorchEvidence:
    try:
        import torch
    except ImportError as error:
        raise BackendError(
            ErrorCode.TORCH_MISSING, "PyTorch is not installed in this environment"
        ) from error

    hip_version = getattr(torch.version, "hip", None)
    if hip_version is None:
        cuda_version = getattr(torch.version, "cuda", None)
        raise BackendError(
            ErrorCode.BACKEND_NOT_RADEON,
            f"PyTorch {torch.__version__} is not a ROCm build "
            f"(torch.version.hip is None, torch.version.cuda is {cuda_version!r})",
        )
    if not torch.cuda.is_available():
        raise BackendError(
            ErrorCode.GPU_NOT_VISIBLE,
            f"PyTorch {torch.__version__} is a ROCm build but exposes no usable device",
        )
    count = torch.cuda.device_count()
    if count < 1:
        raise BackendError(ErrorCode.GPU_NOT_VISIBLE, "torch.cuda.device_count() reported 0")

    properties = torch.cuda.get_device_properties(0)
    return TorchEvidence(
        pytorch_version=str(torch.__version__),
        hip_version=str(hip_version),
        gpu_name=torch.cuda.get_device_name(0),
        architecture=str(getattr(properties, "gcnArchName", "unknown")),
        visible_gpu_count=count,
        vram_bytes=int(properties.total_memory),
    )


def probe_rocm_version() -> str:
    if ROCM_VERSION_FILE.is_file():
        recorded = ROCM_VERSION_FILE.read_text(encoding="utf-8").strip()
        if recorded:
            return recorded
    try:
        completed = subprocess.run(
            [ROCM_SMI, "--showdriverversion"],
            capture_output=True,
            text=True,
            timeout=SMI_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise BackendError(
            ErrorCode.BACKEND_PROBE_FAILED, f"could not determine the ROCm version: {error}"
        ) from error
    if completed.returncode != 0:
        raise BackendError(
            ErrorCode.BACKEND_PROBE_FAILED,
            f"{ROCM_SMI} exited {completed.returncode}: {completed.stderr.strip()}",
        )
    return completed.stdout.strip()


def rocm_smi_dump() -> str:
    try:
        completed = subprocess.run(
            [ROCM_SMI],
            capture_output=True,
            text=True,
            timeout=SMI_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise BackendError(
            ErrorCode.BACKEND_PROBE_FAILED, f"{ROCM_SMI} could not be executed: {error}"
        ) from error
    return completed.stdout
