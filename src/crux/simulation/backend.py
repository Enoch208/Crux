from __future__ import annotations

from dataclasses import dataclass

from crux.errors import BackendError, ErrorCode

CANONICAL_BACKEND = "gs.amdgpu"


@dataclass(frozen=True, slots=True)
class GenesisEvidence:
    genesis_version: str
    resolved_backend: str
    raw_backend: str


def probe_genesis() -> GenesisEvidence:
    try:
        import genesis as gs
    except ImportError as error:
        raise BackendError(
            ErrorCode.GENESIS_MISSING, "Genesis is not installed in this environment"
        ) from error

    if not hasattr(gs, "amdgpu"):
        raise BackendError(
            ErrorCode.BACKEND_NOT_RADEON,
            f"Genesis {getattr(gs, '__version__', 'unknown')} exposes no amdgpu backend",
        )

    gs.init(backend=gs.amdgpu)
    resolved = getattr(gs, "backend", None)
    if resolved is None:
        raise BackendError(
            ErrorCode.BACKEND_PROBE_FAILED, "Genesis reported no resolved backend after init"
        )
    if resolved != gs.amdgpu:
        raise BackendError(
            ErrorCode.BACKEND_NOT_RADEON,
            f"Genesis resolved to backend {resolved!r}, not {CANONICAL_BACKEND}",
        )
    return GenesisEvidence(
        genesis_version=str(gs.__version__),
        resolved_backend=CANONICAL_BACKEND,
        raw_backend=repr(resolved),
    )
