from __future__ import annotations

import heapq
from itertools import count

from .model import ProcessModel
from .types import AlignmentMove


def find_min_cost_alignment(trace: list[str], model: ProcessModel) -> list[AlignmentMove]:
    """Dijkstra search on product states (trace position, model state).

    This is deliberately outside the circuit. It is a small, transparent
    baseline; a PM4Py adapter can replace it for Petri-net experiments.
    """
    start = (0, model.initial_state)
    serial = count()
    queue: list[tuple[int, int, tuple[int, int], list[AlignmentMove]]] = [
        (0, next(serial), start, [])
    ]
    best = {start: 0}

    while queue:
        cost, _, (position, state), moves = heapq.heappop(queue)
        if cost != best.get((position, state)):
            continue
        if position == len(trace) and state in model.accepting_states:
            return moves

        def push(new_cost: int, new_position: int, new_state: int, move: AlignmentMove) -> None:
            product_state = (new_position, new_state)
            if new_cost < best.get(product_state, 10**18):
                best[product_state] = new_cost
                heapq.heappush(
                    queue,
                    (new_cost, next(serial), product_state, [*moves, move]),
                )

        if position < len(trace):
            activity = trace[position]
            push(cost + model.costs.log, position + 1, state, AlignmentMove.log(activity))

        for transition in model.outgoing(state):
            model_cost = (
                model.costs.silent_model if transition.silent else model.costs.visible_model
            )
            push(
                cost + model_cost,
                position,
                transition.target,
                AlignmentMove.model(transition.id),
            )
            if position < len(trace) and not transition.silent:
                if trace[position] == transition.activity:
                    push(
                        cost + model.costs.sync,
                        position + 1,
                        transition.target,
                        AlignmentMove.sync(trace[position], transition.id),
                    )

    raise ValueError("no complete alignment exists for this model")
