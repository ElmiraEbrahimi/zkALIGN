from __future__ import annotations

import argparse
import json
from pathlib import Path

from .alignment import find_min_cost_alignment
from .commitment import commit_trace
from .model import load_model
from .types import MoveType
from .verifier import PublicStatement, verify_witness

ROOT = Path(__file__).resolve().parents[2]


def run_demo() -> int:
    model = load_model(ROOT / "model" / "healthcare_fsm.json")
    trace = ["Admit", "Examine", "EmergencyTest", "Treat", "Discharge"]
    salt = bytes.fromhex("00112233445566778899aabbccddeeff")
    moves = find_min_cost_alignment(trace, model)
    trace_ids = [model.activities[item] for item in trace]
    commitment = commit_trace(trace_ids, salt)
    statement = PublicStatement(commitment, model.version, threshold=2, claimed_cost=2)
    result = verify_witness(trace, salt, moves, model, statement)

    rendered_moves = []
    for move in moves:
        transition = model.transition(move.transition_id) if move.transition_id else None
        rendered_moves.append(
            {
                "type": MoveType(move.move_type).name,
                "trace": move.log_activity,
                "model": transition.activity if transition else None,
                "transition_id": move.transition_id,
            }
        )
    print(json.dumps({
        "private_trace_demo_only": trace,
        "private_alignment_demo_only": rendered_moves,
        "public": {
            "trace_commitment": commitment,
            "model_id": model.version,
            "threshold": statement.threshold,
            "claimed_cost": statement.claimed_cost,
        },
        "six_checks": {
            "1_binding": result.binding,
            "2_trace_consistency": result.trace_consistency,
            "3_move_legality": result.move_legality,
            "4_completeness": result.completeness,
            "5_cost_integrity": result.cost_integrity,
            "6_threshold": result.threshold,
        },
        "accepted": result.accepted,
    }, indent=2))
    return 0 if result.accepted else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="zkALIGN reference prototype")
    parser.add_argument("command", choices=["demo"])
    args = parser.parse_args()
    return run_demo() if args.command == "demo" else 2


if __name__ == "__main__":
    raise SystemExit(main())
