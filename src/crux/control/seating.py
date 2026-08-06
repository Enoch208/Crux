from __future__ import annotations

from math import dist

from crux.control.directives import Observation, Vector
from crux.simulation.taskconfig import TaskConfig


def connector_centre(config: TaskConfig, observation: Observation) -> Vector:
    """The connector body's midpoint, not its trailing joint origin.

    `cable_rows` holds link origins; the last link's body extends beyond its origin
    along the cable direction. Measuring seating at the origin makes success
    geometrically unsatisfiable — the invariant five falsified repair families
    converged on before the measurement was corrected. This ruler is owned by the
    harness and shared by every policy it qualifies, scripted or learned.
    """
    origin = observation.cable_rows[-1]
    inner = observation.cable_rows[-2]
    span = dist(origin, inner)
    if span <= 0.0:
        return origin
    half = config.cable.total_length_m / config.cable.segments / 2.0
    scale = half / span
    return (
        origin[0] + (origin[0] - inner[0]) * scale,
        origin[1] + (origin[1] - inner[1]) * scale,
        origin[2] + (origin[2] - inner[2]) * scale,
    )


def seat_metrics(config: TaskConfig, observation: Observation) -> tuple[bool, float, float]:
    layout = config.layout
    thresholds = config.thresholds
    centre = connector_centre(config, observation)
    lateral = max(abs(centre[0] - layout.socket_x), abs(centre[1] - layout.socket_y))
    depth = centre[2]
    seated = lateral < thresholds.seat_lateral_m and depth < thresholds.seat_z_m
    return seated, lateral, depth
