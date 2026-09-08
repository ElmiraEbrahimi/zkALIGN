from __future__ import annotations

from dataclasses import dataclass

from .commitment import commit_trace
from .model import ProcessModel
from .types import AlignmentMove, MoveType


@dataclass(frozen=True)
class PublicStatement:
    trace_commitment: str
    model_id: str
    threshold: int
    claimed_cost: int
    max_trace_length: int = 16


@dataclass(frozen=True)
class VerificationResult:
    binding: bool
    trace_consistency: bool
    move_legality: bool
    completeness: bool
    cost_integrity: bool
    threshold: bool
    calculated_cost: int
    errors: tuple[str, ...]

    @property
    def accepted(self) -> bool:
        return all(
            (
                self.binding,
                self.trace_consistency,
                self.move_legality,
                self.completeness,
                self.cost_integrity,
                self.threshold,
            )
        )


def verify_witness(
    trace: list[str],
    salt: bytes,
    moves: list[AlignmentMove],
    model: ProcessModel,
    statement: PublicStatement,
) -> VerificationResult:
    """Executable specification of the six circuit goals.

    This code is not a ZK proof. It is the readable oracle against which the
    circuit and its test vectors are checked.
    """
    errors: list[str] = []
    try:
        trace_ids = [model.activities[item] for item in trace]
        actual_commitment = commit_trace(trace_ids, salt, statement.max_trace_length)
        binding = actual_commitment == statement.trace_commitment
    except (KeyError, ValueError):
        binding = False
    if statement.model_id != model.version:
        binding = False
    if not binding:
        errors.append("goal 1: trace/model binding failed")

    position = 0
    state = model.initial_state
    calculated_cost = 0
    trace_consistency = True
    move_legality = True

    for index, move in enumerate(moves):
        if move.move_type == MoveType.SYNC:
            if position >= len(trace) or move.log_activity != trace[position]:
                trace_consistency = False
                errors.append(f"goal 2: sync move {index} does not match the next trace event")
                break
            try:
                transition = model.transition(move.transition_id or -1)
            except ValueError:
                move_legality = False
                errors.append(f"goal 3: sync move {index} uses an unknown transition")
                break
            if (
                transition.silent
                or transition.source != state
                or transition.activity != move.log_activity
            ):
                move_legality = False
                errors.append(f"goal 3: sync move {index} is not enabled or labels do not match")
                break
            position += 1
            state = transition.target
            calculated_cost += model.costs.sync
        elif move.move_type == MoveType.LOG:
            if position >= len(trace) or move.log_activity != trace[position]:
                trace_consistency = False
                errors.append(f"goal 2: log move {index} does not match the next trace event")
                break
            position += 1
            calculated_cost += model.costs.log
        elif move.move_type == MoveType.MODEL:
            try:
                transition = model.transition(move.transition_id or -1)
            except ValueError:
                move_legality = False
                errors.append(f"goal 3: model move {index} uses an unknown transition")
                break
            if transition.source != state:
                move_legality = False
                errors.append(f"goal 3: model move {index} is not enabled")
                break
            state = transition.target
            calculated_cost += (
                model.costs.silent_model if transition.silent else model.costs.visible_model
            )
        else:
            move_legality = False
            errors.append(f"goal 3: explicit PAD moves are not accepted by the reference API")
            break

    if not trace_consistency:
        errors.append("goal 2: alignment does not reconstruct the private trace")
    completeness = position == len(trace) and state in model.accepting_states
    if not completeness:
        errors.append("goal 4: trace was not fully consumed or model is not in a final state")
    cost_integrity = calculated_cost == statement.claimed_cost
    if not cost_integrity:
        errors.append("goal 5: claimed cost differs from the cost derived from moves")
    threshold = calculated_cost <= statement.threshold
    if not threshold:
        errors.append("goal 6: calculated cost exceeds the public threshold")

    return VerificationResult(
        binding=binding,
        trace_consistency=trace_consistency,
        move_legality=move_legality,
        completeness=completeness,
        cost_integrity=cost_integrity,
        threshold=threshold,
        calculated_cost=calculated_cost,
        errors=tuple(errors),
    )
