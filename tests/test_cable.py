from __future__ import annotations

from math import isclose, pi
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
import yaml

from crux.errors import ConfigError, ErrorCode
from crux.simulation.cable import (
    JOINT_AXIS_CYCLE,
    TWIST_AXIS_X,
    CableSpec,
    build_cable_urdf,
    is_twist_joint,
    segment_inertia,
)

CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "cable.yaml"


def make_spec(**overrides: object) -> CableSpec:
    base = {
        "name": "cable",
        "total_length_m": 0.6,
        "radius_m": 0.004,
        "segments": 24,
        "density_kg_m3": 1400.0,
        "bend_limit_rad": 0.5236,
        "twist_limit_rad": 0.2618,
        "bend_damping": 0.002,
        "twist_damping": 0.004,
        "joint_friction": 0.001,
    }
    return CableSpec.model_validate({**base, **overrides})


def parse(spec: CableSpec) -> ET.Element:
    return ET.fromstring(build_cable_urdf(spec))


def child(element: ET.Element, path: str) -> ET.Element:
    found = element.find(path)
    if found is None:
        raise AssertionError(f"missing element {path}")
    return found


def attr(element: ET.Element, name: str) -> str:
    value = element.get(name)
    if value is None:
        raise AssertionError(f"missing attribute {name}")
    return value


def test_shipped_config_is_a_valid_spec() -> None:
    spec = CableSpec.model_validate(yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")))
    assert spec.segments >= 2
    assert build_cable_urdf(spec)


def test_chain_has_one_joint_fewer_than_links() -> None:
    root = parse(make_spec())
    assert len(root.findall("link")) == 24
    assert len(root.findall("joint")) == 23


def test_total_mass_matches_cylinder_volume() -> None:
    spec = make_spec()
    expected = pi * spec.radius_m**2 * spec.total_length_m * spec.density_kg_m3
    assert isclose(spec.total_mass_kg, expected, rel_tol=1e-12)


def test_segment_length_divides_the_cable() -> None:
    spec = make_spec(segments=10, total_length_m=0.5)
    assert isclose(spec.segment_length_m, 0.05, rel_tol=1e-12)


def test_cylinder_inertia_matches_the_analytic_tensor() -> None:
    axial, transverse_a, transverse_b = segment_inertia(mass=2.0, radius=0.1, length=0.6)
    assert isclose(axial, 0.5 * 2.0 * 0.01, rel_tol=1e-12)
    assert isclose(transverse_a, 2.0 * (3.0 * 0.01 + 0.36) / 12.0, rel_tol=1e-12)
    assert transverse_a == transverse_b


def test_joint_axes_cycle_through_two_bends_and_one_twist() -> None:
    root = parse(make_spec(segments=7))
    axes = [attr(child(joint, "axis"), "xyz") for joint in root.findall("joint")]
    assert axes[0] == "0 1 0"
    assert axes[1] == "0 0 1"
    assert axes[2] == "1 0 0"
    assert axes[3] == axes[0]
    assert len(set(axes)) == len(JOINT_AXIS_CYCLE)


def test_twist_joints_are_identified_by_index() -> None:
    assert is_twist_joint(2)
    assert not is_twist_joint(0)
    assert not is_twist_joint(1)
    assert JOINT_AXIS_CYCLE[2] == TWIST_AXIS_X


def test_twist_joints_use_the_twist_limit_and_damping() -> None:
    spec = make_spec(segments=7)
    joints = parse(spec).findall("joint")
    twist, bend = joints[2], joints[0]
    assert float(attr(child(twist, "limit"), "upper")) == pytest.approx(spec.twist_limit_rad)
    assert float(attr(child(bend, "limit"), "upper")) == pytest.approx(spec.bend_limit_rad)
    assert float(attr(child(twist, "dynamics"), "damping")) == pytest.approx(spec.twist_damping)
    assert float(attr(child(bend, "dynamics"), "damping")) == pytest.approx(spec.bend_damping)


def test_joints_are_symmetric_about_zero() -> None:
    for joint in parse(make_spec(segments=5)).findall("joint"):
        limit = child(joint, "limit")
        assert float(attr(limit, "lower")) == -float(attr(limit, "upper"))


def test_links_are_chained_parent_to_child() -> None:
    for index, joint in enumerate(parse(make_spec(segments=6)).findall("joint")):
        assert attr(child(joint, "parent"), "link") == f"cable_link_{index}"
        assert attr(child(joint, "child"), "link") == f"cable_link_{index + 1}"


def test_each_joint_is_offset_by_one_segment_length() -> None:
    spec = make_spec(segments=6)
    for joint in parse(spec).findall("joint"):
        offset = attr(child(joint, "origin"), "xyz").split()
        assert float(offset[0]) == pytest.approx(spec.segment_length_m)


def test_every_link_carries_collision_geometry_and_mass() -> None:
    for link in parse(make_spec(segments=8)).findall("link"):
        assert link.find("collision/geometry/cylinder") is not None
        assert link.find("inertial/mass") is not None


def test_a_cable_thicker_than_its_segments_is_rejected() -> None:
    with pytest.raises(ConfigError) as caught:
        build_cable_urdf(make_spec(segments=200, total_length_m=0.6, radius_m=0.01))
    assert caught.value.code is ErrorCode.CONFIG_INVALID


def test_a_single_segment_cable_is_rejected() -> None:
    with pytest.raises(ValueError, match="segments"):
        make_spec(segments=1)
