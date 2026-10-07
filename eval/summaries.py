"""Reporting-only reductions of saved observations. Never runs a worker."""

import pandas as pd


def truth(value):
    return str(value).lower() == "true"


def utility_metrics(rows, mode):
    """Unknown/errors are not rejections and are excluded from verdict agreement."""
    compared = []
    satisfied = rejected = 0
    for row in rows:
        reason = row.get("reason", "")
        if mode == "solver":
            if reason not in ("constraint_satisfied", "constraint_rejected"):
                continue
            verdict = truth(row.get("solver_satisfied"))
            if verdict != (reason == "constraint_satisfied"):
                raise ValueError("inconsistent solver result")
            satisfied += verdict
            rejected += not verdict
        else:
            if reason not in ("certified", "above_threshold"):
                continue
            verdict = truth(row.get("certified"))
        compared.append(verdict == truth(row.get("reference_ok")))
    return {
        "solver_satisfied": satisfied if mode == "solver" else "",
        "solver_rejected": rejected if mode == "solver" else "",
        "agreement_cases": len(compared),
        "agreement_unavailable": len(rows) - len(compared),
        "agreement_pct": 100 * sum(compared) / len(compared) if compared else "",
    }


def enrich_utility(summary, cases):
    summary = summary.copy()
    for key, group in cases.groupby(["dataset", "K", "mode"]):
        mask = (
            (summary.dataset == key[0])
            & (summary.K == key[1])
            & (summary["mode"] == key[2])
        )
        if mask.sum() != 1:
            raise ValueError(f"missing or duplicated utility summary: {key}")
        if len(group) != int(summary.loc[mask, "processed"].iloc[0]):
            raise ValueError("utility processed count differs from case rows")
        for name, value in utility_metrics(group.to_dict("records"), key[2]).items():
            summary.loc[mask, name] = value if value != "" else float("nan")
    summary.loc[summary["mode"] == "solver", ["certified", "certified_share"]] = float(
        "nan"
    )
    return summary


def case_metadata(cases):
    base = cases[(cases["mode"] == "groth16") & (cases.K == 1)].copy()
    if base.duplicated(["dataset", "index"]).any():
        raise ValueError("duplicate case metadata")
    base["roles"] = ""
    for _, group in base.groupby("dataset", sort=False):
        eligible = group[group.reference_ok.map(truth)].sort_values(
            "alignment_length", kind="stable"
        )
        roles = {}
        if len(eligible):
            for pos, role in (
                (0, "short"),
                (len(eligible) // 2, "median"),
                (len(eligible) - 1, "long"),
            ):
                roles.setdefault(eligible.index[pos], []).append(role)
        for ix, row in group.iterrows():
            if row.dataset == "sepsis" and row.case_id in ("AG", "NGA"):
                roles.setdefault(ix, []).append(row.case_id)
        for ix, labels in roles.items():
            base.loc[ix, "roles"] = "+".join(labels)
    return base[
        ["dataset", "index", "case_id", "trace_length", "alignment_length", "roles"]
    ]


def stats(values, prefix):
    return {
        prefix + "_mean": values.mean(),
        prefix + "_sd": values.std(ddof=1),
        prefix + "_median": values.median(),
    }


def overhead_summary(pairs, cases):
    """Equal-repeat selected-case statistics, not population estimates."""
    pairs = pairs.merge(
        case_metadata(cases), on=["dataset", "index"], validate="many_to_one"
    )
    metrics = [
        "plaintext_alignment_seconds",
        "prover_operation_seconds",
        "operation_overhead",
    ]
    rows = []
    for dataset, group in pairs.groupby("dataset"):
        case_rows = []
        for index, sample in group.groupby("index"):
            row = {
                "dataset": dataset,
                "scope": "case",
                "index": index,
                "case_id": sample.case_id.iloc[0],
                "roles": sample.roles.iloc[0],
                "trace_length": sample.trace_length.iloc[0],
                "alignment_length": sample.alignment_length.iloc[0],
                "n": len(sample),
                "selected_cases": 1,
                "threads": "default",
            }
            for metric in metrics:
                row.update(stats(sample[metric], metric))
            case_rows.append(row)
        med = pd.Series([r["operation_overhead_mean"] for r in case_rows]).median()
        for row in case_rows:
            row["dataset_median_case_overhead"] = med
        rows.extend(case_rows)
        row = {
            "dataset": dataset,
            "scope": "dataset_selected_sample",
            "n": len(group),
            "selected_cases": len(case_rows),
            "threads": "default",
            "dataset_median_case_overhead": med,
        }
        for metric in metrics:
            row.update(stats(group[metric], metric))
        rows.append(row)
    return pd.DataFrame(rows)


def model_summary(raw):
    rows = []
    for (family, activities), group in raw[raw.stage == "prove"].groupby(
        ["family", "activities"]
    ):
        row = {"family": family, "activities": activities, "n": len(group)}
        for field in (
            "places",
            "transitions",
            "arcs",
            "constraints",
            "trace_capacity",
            "alignment_capacity",
            "pk_bytes",
        ):
            if group[field].nunique() != 1:
                raise ValueError(
                    f"inconsistent model metadata: {family}, {activities}, {field}"
                )
            row[field] = group[field].iloc[0]
        row.update(stats(group.operation_seconds, "prove_seconds"))
        rows.append(row)
    return pd.DataFrame(rows)


def trace_summary(repeated, cases):
    selected = repeated[
        (repeated.dataset == "sepsis")
        & (repeated.stage == "prove")
        & (repeated.threads.astype(str) == "default")
    ]
    rows = []
    for (dataset, index), group in selected.groupby(["dataset", "index"]):
        row = {
            "dataset": dataset,
            "index": index,
            "n": len(group),
            "measurement_kind": "repeated_selected_case",
            "prove_seconds_min": group.operation_seconds.min(),
            "prove_seconds_max": group.operation_seconds.max(),
        }
        row.update(stats(group.operation_seconds, "prove_seconds"))
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).merge(
        case_metadata(cases), on=["dataset", "index"], validate="one_to_one"
    )
