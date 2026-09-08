from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd
import pm4py

from zkalign.append_log import AppendOnlyTraceLog

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG = ROOT / "datasets" / "raw" / "Sepsis Cases - Event Log.xes.gz"
DEFAULT_OUTPUT = ROOT / "outputs" / "sepsis"
CASE_ID = "case:concept:name"
ACTIVITY = "concept:name"
TIMESTAMP = "time:timestamp"
SKIP = ">>"
ALIGNMENT_ALGORITHM = "Variants.VERSION_STATE_EQUATION_A_STAR"


def split_by_case(
    dataframe: pd.DataFrame, train_fraction: float, seed: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split whole patient cases, never individual events, to avoid leakage."""
    cases = sorted(dataframe[CASE_ID].astype(str).unique())
    random.Random(seed).shuffle(cases)
    boundary = round(len(cases) * train_fraction)
    train_ids = set(cases[:boundary])
    train = dataframe[dataframe[CASE_ID].astype(str).isin(train_ids)].copy()
    test = dataframe[~dataframe[CASE_ID].astype(str).isin(train_ids)].copy()
    return train, test


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def unpack_alignment_move(value: Any) -> tuple[Any, Any, Any]:
    """Return log label, model label, and exact model-transition name."""
    first, second = value
    if isinstance(first, tuple) and isinstance(second, tuple):
        _, model_transition_name = first
        log_side, model_side = second
        if model_transition_name == SKIP:
            model_transition_name = None
        return log_side, model_side, model_transition_name
    return first, second, None


def classify_moves(
    raw_alignment: list[Any],
    net: Any,
    initial_marking: Any,
    activity_encoding: dict[str, int],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Convert PM4Py output to moves with explicit Petri-net marking changes."""
    places = sorted(net.places, key=lambda place: str(place.name))
    place_names = [str(place.name) for place in places]
    transition_by_name = {str(transition.name): transition for transition in net.transitions}
    transition_encoding = {
        name: index + 1 for index, name in enumerate(sorted(transition_by_name))
    }
    marking = {place: int(initial_marking.get(place, 0)) for place in places}
    moves: list[dict[str, Any]] = []
    for raw_move in raw_alignment:
        log_side, model_side, transition_name = unpack_alignment_move(raw_move)
        if log_side != SKIP and model_side != SKIP:
            move_type = "SYNC"
            cost = 0
        elif log_side != SKIP and model_side == SKIP:
            move_type = "LOG"
            cost = 1
        elif log_side == SKIP:
            move_type = "MODEL"
            # PM4Py represents silent model labels as None; they are legal and
            # normally cost zero under standard alignment semantics.
            cost = 0 if model_side is None else 1
        else:
            raise ValueError(f"unrecognized PM4Py alignment move: {raw_move!r}")
        before = [marking[place] for place in places]
        if move_type in {"SYNC", "MODEL"}:
            if transition_name is None or str(transition_name) not in transition_by_name:
                raise ValueError(f"alignment omitted exact model transition: {raw_move!r}")
            transition = transition_by_name[str(transition_name)]
            if move_type == "SYNC" and (
                transition.label != log_side or model_side != log_side
            ):
                raise ValueError(
                    f"synchronous labels do not match for transition {transition.name!r}"
                )
            if move_type == "MODEL" and transition.label != model_side:
                raise ValueError(
                    f"model label does not match transition {transition.name!r}"
                )
            for arc in transition.in_arcs:
                if marking[arc.source] < arc.weight:
                    raise ValueError(
                        f"PM4Py supplied disabled transition {transition.name!r}"
                    )
            for arc in transition.in_arcs:
                marking[arc.source] -= arc.weight
            for arc in transition.out_arcs:
                marking[arc.target] += arc.weight
        after = [marking[place] for place in places]
        moves.append(
            {
                "type": move_type,
                "log_activity": None if log_side == SKIP else log_side,
                "model_activity": None if model_side == SKIP else model_side,
                "log_activity_id": (
                    0 if log_side == SKIP else activity_encoding[str(log_side)]
                ),
                "model_activity_id": (
                    0 if model_side in {SKIP, None} else activity_encoding[str(model_side)]
                ),
                "transition_id": transition_name,
                "transition_index": (
                    0 if transition_name is None else transition_encoding[str(transition_name)]
                ),
                "pre_marking": before,
                "post_marking": after,
                "reference_cost": cost,
            }
        )
    return moves, place_names


def export_circuit_model(
    net: Any,
    initial_marking: Any,
    final_marking: Any,
    activity_encoding: dict[str, int],
) -> dict[str, Any]:
    """Serialize the public Petri-net constants needed by a future circuit."""
    places = sorted(net.places, key=lambda place: str(place.name))
    place_index = {place: index for index, place in enumerate(places)}
    transitions = []
    for transition_index, transition in enumerate(
        sorted(net.transitions, key=lambda item: str(item.name)), start=1
    ):
        input_vector = [0] * len(places)
        output_vector = [0] * len(places)
        for arc in transition.in_arcs:
            input_vector[place_index[arc.source]] = int(arc.weight)
        for arc in transition.out_arcs:
            output_vector[place_index[arc.target]] = int(arc.weight)
        transitions.append(
            {
                "id": str(transition.name),
                "index": transition_index,
                "label": transition.label,
                "label_id": 0 if transition.label is None else activity_encoding[transition.label],
                "silent": transition.label is None,
                "input_vector": input_vector,
                "output_vector": output_vector,
            }
        )
    return {
        "schema": "zkalign.public-petri-net.v1",
        "activity_encoding": activity_encoding,
        "place_order": [str(place.name) for place in places],
        "initial_marking": [int(initial_marking.get(place, 0)) for place in places],
        "final_marking": [int(final_marking.get(place, 0)) for place in places],
        "transitions": transitions,
    }


def choose_test_cases(test: pd.DataFrame, maximum: int | None) -> pd.DataFrame:
    """Use all held-out cases unless an explicitly disclosed limit is requested."""
    if maximum is None:
        return test.copy()
    ids = sorted(test[CASE_ID].astype(str).unique())[:maximum]
    return test[test[CASE_ID].astype(str).isin(ids)].copy()


def run(args: argparse.Namespace) -> dict[str, Any]:
    args.output.mkdir(parents=True, exist_ok=True)
    dataframe = pm4py.read_xes(str(args.log))
    dataframe = dataframe.sort_values([CASE_ID, TIMESTAMP], kind="stable")
    activity_encoding = {
        activity: index + 1
        for index, activity in enumerate(sorted(dataframe[ACTIVITY].astype(str).unique()))
    }

    # Commit every patient trace before discovery/alignment. The common sparse
    # Merkle root binds the complete 1,050-trace source log; individual proofs
    # later bind each alignment witness to one exact leaf.
    committed_traces: list[tuple[str, list[int]]] = []
    for case_id, case_events in dataframe.groupby(CASE_ID, sort=True):
        committed_traces.append(
            (
                str(case_id),
                [activity_encoding[str(activity)] for activity in case_events[ACTIVITY]],
            )
        )
    append_log = AppendOnlyTraceLog(args.output / "commitment_log", depth=32)
    append_log.append_many(committed_traces)
    commitment_validation = append_log.verify_complete_history()
    if not all(
        commitment_validation[key]
        for key in (
            "contiguous_indices",
            "checkpoint_chain_valid",
            "all_membership_proofs_valid",
        )
    ):
        raise RuntimeError("append-only commitment log failed verification")
    record_by_case = {record.case_id: record for record in append_log.records}
    train, held_out = split_by_case(dataframe, args.train_fraction, args.seed)
    test = choose_test_cases(held_out, args.max_test_cases)

    split_manifest = {
        "seed": args.seed,
        "train_fraction": args.train_fraction,
        "train_case_ids": sorted(train[CASE_ID].astype(str).unique()),
        "held_out_case_ids": sorted(held_out[CASE_ID].astype(str).unique()),
        "aligned_case_ids": sorted(test[CASE_ID].astype(str).unique()),
    }
    (args.output / "split_manifest.json").write_text(
        json.dumps(split_manifest, indent=2), encoding="utf-8"
    )

    # Inductive Miner returns a sound workflow Petri net and naturally supports
    # branching, concurrency, loops, and silent transitions.
    net, initial_marking, final_marking = pm4py.discover_petri_net_inductive(
        train,
        noise_threshold=args.noise_threshold,
        activity_key=ACTIVITY,
        timestamp_key=TIMESTAMP,
        case_id_key=CASE_ID,
    )
    pm4py.write_pnml(net, initial_marking, final_marking, str(args.output / "sepsis_model.pnml"))
    pm4py.save_vis_petri_net(
        net,
        initial_marking,
        final_marking,
        str(args.output / "sepsis_model.svg"),
    )

    event_log = pm4py.convert_to_event_log(test)
    alignments = pm4py.conformance_diagnostics_alignments(
        event_log,
        net,
        initial_marking,
        final_marking,
        variant_str=ALIGNMENT_ALGORITHM,
        ret_tuple_as_trans_desc=True,
    )

    witnesses: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    move_counts: Counter[str] = Counter()
    for trace, result in zip(event_log, alignments, strict=True):
        if result is None:
            raise RuntimeError("PM4Py returned no alignment; no case is silently excluded")
        case = str(trace.attributes.get("concept:name", trace.attributes.get(CASE_ID, "unknown")))
        activities = [str(event[ACTIVITY]) for event in trace]
        moves, place_order = classify_moves(
            result["alignment"], net, initial_marking, activity_encoding
        )
        reconstructed_trace = [
            str(move["log_activity"])
            for move in moves
            if move["type"] in {"SYNC", "LOG"}
        ]
        if reconstructed_trace != activities:
            raise ValueError(f"alignment for case {case} does not reconstruct its trace")
        if moves and moves[-1]["post_marking"] != [
            int(final_marking.get(place, 0))
            for place in sorted(net.places, key=lambda place: str(place.name))
        ]:
            raise ValueError(f"alignment for case {case} did not reach final marking")
        derived_cost = sum(int(move["reference_cost"]) for move in moves)
        commitment_record = record_by_case[case]
        membership_proof = append_log.proof_for_index(commitment_record.index)
        if not append_log.verify_membership(commitment_record, membership_proof):
            raise ValueError(f"invalid sparse Merkle proof for case {case}")
        move_counts.update(move["type"] for move in moves)
        witnesses.append(
            {
                "schema": "zkalign.pm4py-witness.v1",
                "case_id": case,
                "private_trace": activities,
                "private_trace_activity_ids": [activity_encoding[item] for item in activities],
                "private_trace_salt": commitment_record.salt,
                "trace_index": commitment_record.index,
                "trace_commitment": commitment_record.commitment,
                "private_sparse_merkle_proof": membership_proof.to_dict(),
                "public_log_root": append_log.tree.root().hex(),
                "place_order": place_order,
                "candidate_alignment": moves,
                "derived_unit_cost": derived_cost,
                "pm4py_raw_cost": result.get("cost"),
                "pm4py_fitness": result.get("fitness"),
            }
        )
        summaries.append(
            {
                "case_id": case,
                "trace_length": len(activities),
                "alignment_length": len(moves),
                "sync_moves": sum(move["type"] == "SYNC" for move in moves),
                "log_moves": sum(move["type"] == "LOG" for move in moves),
                "visible_model_moves": sum(
                    move["type"] == "MODEL" and move["model_activity"] is not None
                    for move in moves
                ),
                "silent_model_moves": sum(
                    move["type"] == "MODEL" and move["model_activity"] is None
                    for move in moves
                ),
                "derived_unit_cost": derived_cost,
                "pm4py_raw_cost": result.get("cost"),
                "pm4py_fitness": result.get("fitness"),
            }
        )

    (args.output / "alignment_witnesses.json").write_text(
        json.dumps(witnesses, indent=2, default=str), encoding="utf-8"
    )
    pd.DataFrame(summaries).to_csv(args.output / "alignment_summary.csv", index=False)
    (args.output / "circuit_model.json").write_text(
        json.dumps(
            export_circuit_model(net, initial_marking, final_marking, activity_encoding),
            indent=2,
        ),
        encoding="utf-8",
    )

    aligned_indices = sorted(record_by_case[case].index for case in split_manifest["aligned_case_ids"])
    expected_held_out_indices = sorted(
        record_by_case[case].index for case in split_manifest["held_out_case_ids"]
    )
    coverage = {
        "schema": "zkalign.alignment-coverage.v1",
        "source_log_root": append_log.tree.root().hex(),
        "source_log_leaf_count": len(append_log.records),
        "aligned_partition": "held-out",
        "aligned_trace_count": len(aligned_indices),
        "aligned_trace_indices": aligned_indices,
        "expected_held_out_indices": expected_held_out_indices,
        "complete_held_out_coverage": aligned_indices == expected_held_out_indices,
        "no_duplicate_aligned_indices": len(aligned_indices) == len(set(aligned_indices)),
        "note": (
            "This manifest verifies pre-ZKP coverage. The later aggregate circuit must "
            "enforce the same index set rather than trusting this JSON."
        ),
    }
    (args.output / "alignment_coverage.json").write_text(
        json.dumps(coverage, indent=2), encoding="utf-8"
    )

    summary_frame = pd.DataFrame(summaries)
    metadata = {
        "dataset": "Sepsis Cases - Event Log",
        "dataset_doi": "10.4121/uuid:915d2bfb-7e84-49ad-a286-dc35f063a460",
        "pm4py_version": pm4py.__version__,
        "alignment_algorithm": "PM4Py state-equation A*",
        "alignment_variant": ALIGNMENT_ALGORITHM,
        "alignment_timeouts_or_exclusions": 0,
        "append_only_log": {
            "tree_type": "32-level sparse Merkle tree",
            "committed_traces": len(append_log.records),
            "merkle_root": append_log.tree.root().hex(),
            "checkpoint_chain_head": append_log.checkpoints[-1]["checkpoint_hash"],
            "history_validation": commitment_validation,
            "held_out_coverage_complete": coverage["complete_held_out_coverage"],
            "held_out_indices_unique": coverage["no_duplicate_aligned_indices"],
        },
        "source_log_sha256": file_sha256(args.log),
        "model_pnml_sha256": file_sha256(args.output / "sepsis_model.pnml"),
        "split_seed": args.seed,
        "train_fraction": args.train_fraction,
        "noise_threshold": args.noise_threshold,
        "all_cases": int(dataframe[CASE_ID].nunique()),
        "all_events": int(len(dataframe)),
        "train_cases": int(train[CASE_ID].nunique()),
        "held_out_cases": int(held_out[CASE_ID].nunique()),
        "aligned_test_cases": int(test[CASE_ID].nunique()),
        "activities": sorted(dataframe[ACTIVITY].astype(str).unique()),
        "activity_encoding": activity_encoding,
        "petri_net": {
            "places": len(net.places),
            "transitions": len(net.transitions),
            "visible_transitions": sum(t.label is not None for t in net.transitions),
            "silent_transitions": sum(t.label is None for t in net.transitions),
            "arcs": len(net.arcs),
        },
        "alignment_move_counts": dict(move_counts),
        "alignment_results": {
            "perfectly_fitting_cases": int((summary_frame["derived_unit_cost"] == 0).sum()),
            "deviating_cases": int((summary_frame["derived_unit_cost"] > 0).sum()),
            "mean_unit_deviation_cost": float(summary_frame["derived_unit_cost"].mean()),
            "maximum_unit_deviation_cost": int(summary_frame["derived_unit_cost"].max()),
            "maximum_trace_length": int(summary_frame["trace_length"].max()),
            "maximum_alignment_length": int(summary_frame["alignment_length"].max()),
        },
    }
    (args.output / "run_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    return metadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Discover a Sepsis Petri net and align held-out patient cases"
    )
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--train-fraction", type=float, default=0.8)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--noise-threshold", type=float, default=0.2)
    parser.add_argument(
        "--max-test-cases",
        type=int,
        default=None,
        help="optional test-only limit; omitted means align every held-out case",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.log.exists():
        raise SystemExit(
            f"Dataset not found: {args.log}\nRun: python3 scripts/download_sepsis.py"
        )
    metadata = run(args)
    print(json.dumps(metadata, indent=2))
    print(f"Outputs written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
