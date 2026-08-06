from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from crux.control.directives import Finish, Observation, Reach, Settle
from crux.control.policy import Plan
from crux.control.safety import abort_reason
from crux.control.seating import seat_metrics
from crux.control.tooling import tool_down_yaw_quat
from crux.failures.taxonomy import ReasonCode, TaskStage
from crux.learning.trace import ActionLimits, chunk_features, clamp_target, decode_action
from crux.simulation.taskconfig import TaskConfig

Predictor = Callable[[Sequence[float]], Sequence[float]]


@dataclass(slots=True)
class LearnedEpisodePolicy:
    """Drives an episode from a learned action predictor behind the scripted interface.

    The network only proposes: each chunk it maps the observation to a bounded tool
    motion, yaw and finger force. Everything that judges stays with the harness — the
    safety envelope aborts through the same `abort_reason` the scripted policy uses,
    and the terminal verdict comes from the same `seat_metrics` ruler, so a learned
    controller cannot grade its own homework.
    """

    config: TaskConfig
    predictor: Predictor
    limits: ActionLimits
    budget_steps: int
    timestep_s: float = 0.005
    stage: TaskStage = TaskStage.OBSERVE
    notes: list[str] = field(default_factory=list, init=False)
    held_link: int | None = field(default=None, init=False)
    max_cable_tension_n: float = field(default=0.0, init=False)
    max_arm_contact_n: float = field(default=0.0, init=False)
    seat_lateral_m: float | None = field(default=None, init=False)
    seat_depth_m: float | None = field(default=None, init=False)

    def run(self, observation: Observation) -> Plan:
        self.stage = TaskStage.OBSERVE
        self.notes.append(f"{self.stage}: learned policy, budget {self.budget_steps} steps")
        while observation.steps_taken <= self.budget_steps:
            self.max_cable_tension_n = max(self.max_cable_tension_n, observation.cable_contact_n)
            self.max_arm_contact_n = max(self.max_arm_contact_n, observation.arm_contact_n)
            abort = abort_reason(observation, self.config.thresholds, self.budget_steps)
            if abort is not None and abort[0] is not ReasonCode.TIMEOUT:
                self.notes.append(f"{self.stage}: FAILED {abort[0]}: {abort[1]}")
                yield Finish(abort[0], self.stage, tuple(self.notes))
                return
            if abort is not None:
                break
            action = decode_action(self.predictor(chunk_features(observation)), self.limits)
            if action.settle:
                observation = yield Settle(action.finger_force_n)
                continue
            target = clamp_target(observation.hand_pos, action, self.limits)
            observation = yield Reach(
                target, tool_down_yaw_quat(action.yaw_rad), action.finger_force_n
            )
        yield self._judge(observation)

    def _judge(self, observation: Observation) -> Finish:
        self.stage = TaskStage.VERIFY_SEATED
        seated, lateral, depth = seat_metrics(self.config, observation)
        self.seat_lateral_m = lateral
        self.seat_depth_m = depth
        self.notes.append(
            f"{self.stage}: connector lateral {lateral * 1000:.1f} mm, tip z {depth * 1000:.1f} mm"
        )
        if seated:
            return Finish(ReasonCode.SUCCESS, self.stage, tuple(self.notes), lateral, depth)
        code = (
            ReasonCode.CONNECTOR_MISALIGNED
            if lateral >= self.config.thresholds.seat_lateral_m
            else ReasonCode.INCOMPLETE_INSERTION
        )
        self.notes.append(f"{self.stage}: FAILED {code}")
        return Finish(code, self.stage, tuple(self.notes), lateral, depth)
