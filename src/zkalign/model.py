from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Transition:
    id: int
    source: int
    activity: str
    target: int
    silent: bool = False


@dataclass(frozen=True)
class CostPolicy:
    sync: int
    log: int
    visible_model: int
    silent_model: int


@dataclass(frozen=True)
class ProcessModel:
    version: str
    initial_state: int
    accepting_states: frozenset[int]
    activities: dict[str, int]
    transitions: tuple[Transition, ...]
    costs: CostPolicy

    def outgoing(self, state: int) -> tuple[Transition, ...]:
        return tuple(t for t in self.transitions if t.source == state)

    def transition(self, transition_id: int) -> Transition:
        for transition in self.transitions:
            if transition.id == transition_id:
                return transition
        raise ValueError(f"unknown transition id: {transition_id}")


def load_model(path: str | Path) -> ProcessModel:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    transitions = tuple(Transition(**item) for item in raw["transitions"])
    return ProcessModel(
        version=raw["version"],
        initial_state=raw["initial_state"],
        accepting_states=frozenset(raw["accepting_states"]),
        activities=raw["activities"],
        transitions=transitions,
        costs=CostPolicy(**raw["cost_policy"]),
    )
