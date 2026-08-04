from __future__ import annotations

from enum import IntEnum

from crux.evidence.manifest import DeviceEvidence
from crux.evidence.backend import backend_name


class FakeBackend(IntEnum):
    cpu = 0
    amdgpu = 3


def test_an_int_enum_backend_resolves_to_its_name() -> None:
    assert backend_name(FakeBackend.amdgpu) == "amdgpu"


def test_a_plain_object_falls_back_to_its_repr() -> None:
    class Opaque:
        def __repr__(self) -> str:
            return "<backend.amdgpu: 3>"

    assert "amdgpu" in backend_name(Opaque())


def test_the_resolved_name_satisfies_the_radeon_check() -> None:
    evidence = DeviceEvidence(
        gpu_name="AMD Radeon Graphics",
        architecture="gfx1100",
        rocm_version="7.2.1",
        hip_version="7.2.53211",
        pytorch_version="2.13.0+rocm7.2",
        genesis_version="1.3.1",
        resolved_backend=backend_name(FakeBackend.amdgpu),
        visible_gpu_count=1,
        vram_bytes=51522830336,
    )
    assert evidence.is_radeon


def test_a_cpu_backend_fails_the_radeon_check() -> None:
    evidence = DeviceEvidence(
        gpu_name="cpu",
        architecture="x86",
        rocm_version="none",
        hip_version="none",
        pytorch_version="2.13.0",
        genesis_version="1.3.1",
        resolved_backend=backend_name(FakeBackend.cpu),
        visible_gpu_count=0,
        vram_bytes=0,
    )
    assert not evidence.is_radeon
