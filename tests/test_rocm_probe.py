from __future__ import annotations

import pytest

from crux.errors import BackendError, ErrorCode
from crux.telemetry.rocm import probe_rocm_version, probe_torch

REFUSAL_CODES = {
    ErrorCode.TORCH_MISSING,
    ErrorCode.BACKEND_NOT_RADEON,
    ErrorCode.GPU_NOT_VISIBLE,
}


def test_probe_refuses_to_report_a_device_without_a_radeon() -> None:
    try:
        evidence = probe_torch()
    except BackendError as error:
        assert error.code in REFUSAL_CODES
        return
    assert evidence.hip_version
    assert evidence.visible_gpu_count >= 1


def test_rocm_version_probe_fails_loudly_when_rocm_is_absent() -> None:
    try:
        version = probe_rocm_version()
    except BackendError as error:
        assert error.code is ErrorCode.BACKEND_PROBE_FAILED
        return
    assert version


def test_backend_errors_carry_a_stable_code() -> None:
    error = BackendError(ErrorCode.BACKEND_NOT_RADEON, "no Radeon")
    assert error.code is ErrorCode.BACKEND_NOT_RADEON
    assert "[BACKEND_NOT_RADEON]" in str(error)


def test_error_codes_are_unique() -> None:
    values = [code.value for code in ErrorCode]
    assert len(values) == len(set(values))


@pytest.mark.parametrize("code", sorted(REFUSAL_CODES))
def test_every_refusal_code_is_distinct_from_success(code: ErrorCode) -> None:
    assert code.value.isupper()
