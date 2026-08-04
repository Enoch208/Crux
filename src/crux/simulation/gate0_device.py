from __future__ import annotations

import json
import subprocess
from pathlib import Path

import genesis as gs
import torch

OUTPUT_PATH = Path("evidence-dev/device.json")
ROCM_VERSION_FILE = Path("/opt/rocm/.info/version")


def rocm_version() -> str:
    if ROCM_VERSION_FILE.is_file():
        return ROCM_VERSION_FILE.read_text(encoding="utf-8").strip()
    probe = subprocess.run(
        ["rocm-smi", "--showdriverversion"], capture_output=True, text=True, check=False
    )
    return probe.stdout.strip() or "unknown"


def main() -> int:
    gs.init(backend=gs.amdgpu)
    device = torch.device("cuda")
    properties = torch.cuda.get_device_properties(device)

    evidence = {
        "gpu_name": torch.cuda.get_device_name(device),
        "architecture": getattr(properties, "gcnArchName", "unknown"),
        "rocm_version": rocm_version(),
        "hip_version": str(torch.version.hip),
        "pytorch_version": torch.__version__,
        "genesis_version": gs.__version__,
        "resolved_backend": str(gs.backend),
        "visible_gpu_count": torch.cuda.device_count(),
        "vram_bytes": properties.total_memory,
    }
    if torch.version.cuda is not None:
        raise SystemExit(f"torch reports CUDA {torch.version.cuda}; this must be a ROCm build")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    for key, value in sorted(evidence.items()):
        print(f"  {key}: {value}", flush=True)
    print(f"\nwrote {OUTPUT_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
