"""Shared policy interface for adding agents without changing the runner."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Decision:
    action: str
    confidence: float | None
    probabilities: dict | None
    model: str
    usage: dict
    observation_time: float
    latency_seconds: float
    allowed_actions: tuple
    plan: dict | None = None
    parameters: dict | None = None


class Agent(Protocol):
    def decide(self, task: dict, state: dict, elapsed: float, progress: dict,
               observation_time: float) -> Decision: ...
