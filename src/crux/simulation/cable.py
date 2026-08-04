from __future__ import annotations

from math import pi
from xml.etree import ElementTree as ET

from pydantic import Field

from crux.errors import ConfigError, ErrorCode
from crux.schema import Frozen

BEND_AXIS_Y = (0.0, 1.0, 0.0)
BEND_AXIS_Z = (0.0, 0.0, 1.0)
TWIST_AXIS_X = (1.0, 0.0, 0.0)
JOINT_AXIS_CYCLE: tuple[tuple[float, float, float], ...] = (BEND_AXIS_Y, BEND_AXIS_Z, TWIST_AXIS_X)


class CableSpec(Frozen):
    name: str = Field(min_length=1)
    total_length_m: float = Field(gt=0.0)
    radius_m: float = Field(gt=0.0)
    segments: int = Field(ge=2)
    density_kg_m3: float = Field(gt=0.0)
    bend_limit_rad: float = Field(gt=0.0)
    twist_limit_rad: float = Field(gt=0.0)
    bend_damping: float = Field(ge=0.0)
    twist_damping: float = Field(ge=0.0)
    joint_friction: float = Field(ge=0.0)

    @property
    def segment_length_m(self) -> float:
        return self.total_length_m / self.segments

    @property
    def segment_mass_kg(self) -> float:
        volume = pi * self.radius_m**2 * self.segment_length_m
        return volume * self.density_kg_m3

    @property
    def total_mass_kg(self) -> float:
        return self.segment_mass_kg * self.segments


def segment_inertia(mass: float, radius: float, length: float) -> tuple[float, float, float]:
    axial = 0.5 * mass * radius**2
    transverse = mass * (3.0 * radius**2 + length**2) / 12.0
    return axial, transverse, transverse


def is_twist_joint(joint_index: int) -> bool:
    return JOINT_AXIS_CYCLE[joint_index % len(JOINT_AXIS_CYCLE)] == TWIST_AXIS_X


def _vector(values: tuple[float, ...]) -> str:
    return " ".join(f"{value:g}" for value in values)


def _append_link(robot: ET.Element, spec: CableSpec, index: int) -> None:
    link = ET.SubElement(robot, "link", name=f"{spec.name}_link_{index}")
    length = spec.segment_length_m
    mass = spec.segment_mass_kg
    axial, transverse, _ = segment_inertia(mass, spec.radius_m, length)

    inertial = ET.SubElement(link, "inertial")
    ET.SubElement(inertial, "origin", xyz=f"{length / 2.0:g} 0 0", rpy="0 0 0")
    ET.SubElement(inertial, "mass", value=f"{mass:g}")
    ET.SubElement(
        inertial,
        "inertia",
        ixx=f"{axial:g}",
        ixy="0",
        ixz="0",
        iyy=f"{transverse:g}",
        iyz="0",
        izz=f"{transverse:g}",
    )

    for tag in ("visual", "collision"):
        element = ET.SubElement(link, tag)
        ET.SubElement(element, "origin", xyz=f"{length / 2.0:g} 0 0", rpy="0 1.5707963 0")
        geometry = ET.SubElement(element, "geometry")
        ET.SubElement(geometry, "cylinder", radius=f"{spec.radius_m:g}", length=f"{length:g}")


def _append_joint(robot: ET.Element, spec: CableSpec, index: int) -> None:
    axis = JOINT_AXIS_CYCLE[index % len(JOINT_AXIS_CYCLE)]
    twist = is_twist_joint(index)
    limit = spec.twist_limit_rad if twist else spec.bend_limit_rad
    damping = spec.twist_damping if twist else spec.bend_damping

    joint = ET.SubElement(
        robot,
        "joint",
        name=f"{spec.name}_joint_{index}",
        type="revolute",
    )
    ET.SubElement(joint, "parent", link=f"{spec.name}_link_{index}")
    ET.SubElement(joint, "child", link=f"{spec.name}_link_{index + 1}")
    ET.SubElement(joint, "origin", xyz=f"{spec.segment_length_m:g} 0 0", rpy="0 0 0")
    ET.SubElement(joint, "axis", xyz=_vector(axis))
    ET.SubElement(
        joint,
        "limit",
        lower=f"{-limit:g}",
        upper=f"{limit:g}",
        effort="100",
        velocity="100",
    )
    ET.SubElement(joint, "dynamics", damping=f"{damping:g}", friction=f"{spec.joint_friction:g}")


def build_cable_urdf(spec: CableSpec) -> str:
    if spec.segment_length_m <= 2.0 * spec.radius_m:
        raise ConfigError(
            ErrorCode.CONFIG_INVALID,
            f"segment length {spec.segment_length_m:g} m is not longer than the cable diameter "
            f"{2.0 * spec.radius_m:g} m; increase total_length_m or reduce segments",
        )
    robot = ET.Element("robot", name=spec.name)
    for index in range(spec.segments):
        _append_link(robot, spec, index)
    for index in range(spec.segments - 1):
        _append_joint(robot, spec, index)
    ET.indent(robot, space="  ")
    return ET.tostring(robot, encoding="unicode")
