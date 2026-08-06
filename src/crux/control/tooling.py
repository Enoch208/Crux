from __future__ import annotations

from math import atan2, cos, sin

TOOL_DOWN_QUAT = (0.0, 1.0, 0.0, 0.0)


def tool_down_yaw_quat(yaw_rad: float) -> tuple[float, float, float, float]:
    return (0.0, cos(yaw_rad / 2.0), sin(yaw_rad / 2.0), 0.0)


def yaw_of_tool_quat(quat: tuple[float, float, float, float]) -> float:
    return 2.0 * atan2(quat[2], quat[1])
