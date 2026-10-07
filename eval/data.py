"""Download, freeze and align real datasets under explicit unit costs."""
from __future__ import annotations
import argparse
import json
import random
import secrets
import subprocess
import time
from pathlib import Path

import pm4py
from pm4py.algo.conformance.alignments.petri_net.variants import state_equation_a_star as astar
from scripts.healthcare_pipeline import split_by_case, classify_moves, export_circuit_model

ROOT = Path(__file__).resolve().parents[1]
DATASETS = {
    "bpic13cp": (12714476, 24070847, "c2c3b154-ab26-4b31-a0e8-8f2350ddac11"),
    "rtfm": (12683249, 24018146, "270fd440-1057-4fb9-89a9-b699b47990f5"),
    "sepsis": (12707639, 24061976, "915d2bfb-7e84-49ad-a286-dc35f063a460"),
    "hospital": (12705113, 24058772, "76c46b83-c930-4798-a1c9-4be94dfeb741"),
}
FIELD = 21888242871839275222246405745257275088548364400416034343698204186575808495617

def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str) + "\n")

def align(trace, net, initial, final, timeout=120):
    """Direct API avoids PM4Py's fitness wrapper and its 10,000 scaling."""
    p = astar.Parameters
    return astar.apply(trace, net, initial, final, parameters={
        p.PARAM_TRACE_COST_FUNCTION: [1] * len(trace),
        p.PARAM_MODEL_COST_FUNCTION: {t: int(t.label is not None) for t in net.transitions},
        p.PARAM_SYNC_COST_FUNCTION: {t: 0 for t in net.transitions},
        p.PARAM_ALIGNMENT_RESULT_IS_SYNC_PROD_AWARE: True,
        p.PARAM_MAX_ALIGN_TIME_TRACE: timeout,
    })

def config_from_export(model, trace_capacity, alignment_capacity):
    ts = model["transitions"]
    places = len(model["place_order"])
    for t in ts:
        if any(v not in (0, 1) for v in t["input_vector"] + t["output_vector"]):
            raise ValueError("non-ordinary net")
    return {
        "activity_count": len(model["activity_encoding"]),
        "trace_capacity": trace_capacity, "alignment_capacity": alignment_capacity,
        "initial": model["initial_marking"], "final": model["final_marking"],
        "labels": [t["label_id"] for t in ts],
        "model_costs": [int(not t["silent"]) for t in ts],
        "inputs": [[j for j,t in enumerate(ts) if t["input_vector"][p]] for p in range(places)],
        "outputs": [[j for j,t in enumerate(ts) if t["output_vector"][p]] for p in range(places)],
    }

def download(name):
    article, file_id, doi = DATASETS[name]
    folder = ROOT / "datasets" / "raw" / "evaluation"
    folder.mkdir(parents=True, exist_ok=True)
    meta_path = folder / (name + ".source.json")
    if not meta_path.exists():
        subprocess.run(["curl", "--fail", "-L", "--retry", "3",
                        f"https://api.figshare.com/v2/articles/{article}", "-o", str(meta_path)], check=True)
    meta = json.loads(meta_path.read_text())
    if meta["doi"].lower() != ("10.4121/uuid:" + doi).lower():
        raise ValueError("dataset DOI differs from registered source")
    file = next(f for f in meta["files"] if f["id"] == file_id)
    path = folder / (name + ".xes.gz")
    if not path.exists():
        subprocess.run(["curl", "--fail", "-L", "--retry", "3", file["download_url"], "-o", str(path)], check=True)
    if path.stat().st_size != file["size"]:
        raise ValueError("dataset download size mismatch")
    return path, meta

def prepare(name, out, limit=300, seed=42, timeout=120):
    folder = Path(out) / name
    if (folder / "cases.json").exists():
        metadata=json.loads((folder/"metadata.json").read_text())
        if metadata["seed"]!=seed or metadata["requested_limit"]!=limit:
            raise ValueError("existing frozen population uses different options; choose a new output directory")
        return metadata
    path, source = download(name)
    pm4py.util.constants.SHOW_PROGRESS_BAR = False
    df = pm4py.read_xes(str(path))
    df["case:concept:name"] = df["case:concept:name"].astype(str)
    df = df.sort_values(["case:concept:name","time:timestamp"], kind="stable")
    train, held = split_by_case(df, 0.8, seed)
    all_ids = sorted(held["case:concept:name"].unique())
    ids = sorted(random.Random(seed).sample(all_ids, min(limit, len(all_ids))))
    split = {"seed":seed, "train":sorted(train["case:concept:name"].unique()),
             "held_out":all_ids, "audit":ids}
    if (folder/"split.json").exists() and json.loads((folder/"split.json").read_text()) != split:
        raise ValueError("frozen population changed")
    save(folder/"split.json",split)
    # Membership is frozen before any alignment cost is examined.
    audit=df[df["case:concept:name"].isin(ids)]
    encoding={a:i+1 for i,a in enumerate(sorted(df["concept:name"].astype(str).unique()))}
    pnml=folder/"model.pnml"
    if pnml.exists():
        net,im,fm=pm4py.read_pnml(str(pnml))
    else:
        tree=pm4py.discover_process_tree_inductive(train,noise_threshold=0.2)
        pm4py.write_ptml(tree,str(folder/"model.ptml"))
        net,im,fm=pm4py.convert_to_petri_net(tree)
        pm4py.write_pnml(net,im,fm,str(pnml))
    model=export_circuit_model(net,im,fm,encoding)
    cases=[]
    for index,trace in enumerate(pm4py.convert_to_event_log(audit)):
        start=time.perf_counter()
        result=align(trace,net,im,fm,timeout)
        duration=time.perf_counter()-start
        row={"case_id":str(trace.attributes["concept:name"]), "index":index,
             "events":[encoding[str(e["concept:name"])] for e in trace],
             "salt":str(secrets.randbelow(FIELD)), "alignment_seconds":duration,
             "status":"alignment_timeout", "moves":[], "cost":None}
        if result is not None:
            moves,_=classify_moves(result["alignment"],net,im,encoding)
            consumed=[m["log_activity_id"] for m in moves if m["type"] in ("SYNC","LOG")]
            final=model["initial_marking"] if not moves else moves[-1]["post_marking"]
            if consumed!=row["events"] or final!=model["final_marking"]:
                raise ValueError("reference alignment failed independent replay")
            if any(v not in (0,1) for m in moves for v in m["post_marking"]):
                raise ValueError("reference firing exceeds 1-safe marking")
            cost=sum(m["reference_cost"] for m in moves)
            if cost != result["cost"]:
                raise ValueError("search and circuit cost policies differ")
            row.update(cost=cost,status="aligned",moves=[
                {"type":{"SYNC":1,"LOG":2,"MODEL":3}[m["type"]],
                 "activity":m["log_activity_id"],"transition":m["transition_index"]} for m in moves])
        cases.append(row)
    sigma=max(len(c["events"]) for c in cases)
    gamma=max([len(c["moves"]) for c in cases]+[1])
    # Keep the published Sepsis candidate 384; other logs use their actual maximum.
    if name=="sepsis": gamma=max(384,gamma)
    cfg=config_from_export(model,sigma,gamma)
    metadata={"dataset":name,"doi":source["doi"],"seed":seed,"requested_limit":limit,
        "source_cases":df["case:concept:name"].nunique(),"source_events":len(df),
        "activities":len(encoding),"population":len(cases),
        "median_trace_length":float(audit.groupby("case:concept:name").size().median()),
        "max_trace_length":sigma,"max_alignment_length":max(len(c["moves"]) for c in cases),
        "places":len(net.places),"transitions":len(net.transitions),
        "silent_transitions":sum(t.label is None for t in net.transitions),"arcs":len(net.arcs),
        "trace_capacity":sigma,"alignment_capacity":gamma,
        "alignment_timeouts":sum(c["status"]!="aligned" for c in cases),
        "classifier":"concept:name","order":"case,timestamp,stable input ties",
        "safety":"process-tree conversion; ordinary arcs checked; witness markings replayed",
        "pm4py_version":pm4py.__version__}
    save(folder/"config.json",cfg)
    save(folder/"model.json",model)
    save(folder/"metadata.json",metadata)
    save(folder/"cases.json",cases)
    return metadata

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",type=Path,default=ROOT/"outputs/evaluation/data")
    parser.add_argument("--datasets",nargs="+",default=list(DATASETS))
    parser.add_argument("--limit",type=int,default=300)
    args=parser.parse_args()
    for name in args.datasets:
        print(json.dumps(prepare(name,args.out,args.limit),default=str),flush=True)

