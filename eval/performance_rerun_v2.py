"""New, isolated performance suite. Existing code, measurements and CSVs are read-only.

    PYTHONPATH=src .venv/bin/python -m eval.performance_rerun_v2 --repeat 5

Each invocation creates a unique run directory. No resume/overwrite mode is
provided. Successful repetitions, all receipts and partial CSVs survive failure.
"""

import argparse
import copy
import csv
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import random
import shutil
import statistics
import subprocess
import sys
import uuid

from eval.measure_fresh_v2 import run_worker, stage

ROOT = Path(__file__).resolve().parents[1]
DATASETS = ("bpic13cp", "rtfm", "sepsis", "hospital")
STAGES = ("compile", "setup", "witness", "prove", "verify")
BOUNDS = (32, 64, 128, 256, 384)
SIZES = (5, 10, 20, 30, 40, 50)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def write_csv(path, rows):
    """Only called for files inside this invocation's newly created directory."""
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(key for row in rows for key in row))
    pending = path.with_suffix(".pending")
    with pending.open("w", newline="") as stream:
        w = csv.DictWriter(stream, fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    pending.replace(path)


def select_cases(cases):
    eligible = sorted((c for c in cases if c.get("status") == "aligned"
                       and c.get("cost") is not None and c["cost"] <= 1),
                      key=lambda c: len(c["moves"]))
    if not eligible:
        raise ValueError("No eligible benchmark cases")
    roles = {}
    for i, role in ((0, "short"), (len(eligible)//2, "median"), (-1, "long")):
        roles.setdefault(eligible[i]["index"], []).append(role)
    return roles


def make_specs(source, experiments):
    specs = []
    if "real" in experiments or "capacity" in experiments:
        for name in DATASETS:
            if "real" not in experiments and name != "sepsis":
                continue
            folder = source / "data" / name
            cfg = json.loads((folder / "config.json").read_text())
            cases = json.loads((folder / "cases.json").read_text())
            if "real" in experiments:
                roles = select_cases(cases)
                if name == "sepsis":
                    for c in cases:
                        if c["case_id"] in ("AG", "NGA"):
                            if c.get("cost") is None or c["cost"] > 1:
                                raise ValueError("Additional Sepsis case is not eligible")
                            roles.setdefault(c["index"], []).append(c["case_id"])
                for filename in ("model.pnml", "model.json"):
                    if not (folder / filename).is_file():
                        raise FileNotFoundError(folder / filename)
                specs.append(dict(id=f"real-{name}", experiment="real", dataset=name,
                                  config=cfg, cases=cases, roles={str(k): "+".join(v) for k,v in roles.items()},
                                  source=str(folder)))
            if name == "sepsis" and "capacity" in experiments:
                c = copy.deepcopy(next(c for c in cases if c["case_id"] == "AG"))
                c["index"] = 0
                if cfg["trace_capacity"] != 185 or c["cost"] > 1:
                    raise ValueError("Unexpected Sepsis capacity experiment inputs")
                for bound in BOUNDS:
                    if len(c["moves"]) > bound:
                        raise ValueError("AG does not fit capacity")
                    conf = copy.deepcopy(cfg)
                    conf["alignment_capacity"] = bound
                    specs.append(dict(id=f"capacity-{bound}", experiment="capacity", dataset="sepsis",
                                      config=conf, cases=[c], roles={"0":"AG"}, source=str(folder)))
    if "models" in experiments:
        from eval.scalability import synthetic, replay
        for family in ("sequence", "choice", "parallel", "loop"):
            for n in SIZES:
                cfg, c = synthetic(family, n)
                replay(cfg, c)
                specs.append(dict(id=f"model-{family}-{n}", experiment="models", dataset="synthetic",
                                  family=family, activities=n, config=cfg, cases=[c], roles={"0":"synthetic"}))
    return specs


def schedule(specs, repetitions, seed):
    rng = random.Random(seed)
    jobs = []
    # Randomized blocks: every configuration appears once in each round.
    for repeat in range(1, repetitions + 1):
        order = list(range(len(specs)))
        rng.shuffle(order)
        offset = len(jobs)
        jobs.extend(dict(spec_index=i, repeat=repeat, order=offset+j+1)
                    for j,i in enumerate(order))
    return jobs


def statistics_for(rows):
    out = {"observations":len(rows)}
    for field, prefix, divisor in (("operation_seconds","operation_time",1),
                                    ("worker_seconds","worker_time",1),
                                    ("process_peak_rss_bytes","mem",1e6),
                                    ("user_cpu_seconds","user_cpu",1),
                                    ("system_cpu_seconds","system_cpu",1)):
        values = [float(r[field])/divisor for r in rows]
        unit = "mb" if field == "process_peak_rss_bytes" else "s"
        out[f"{prefix}_mean_{unit}"] = statistics.mean(values)
        out[f"{prefix}_sd_{unit}"] = statistics.stdev(values) if len(values)>1 else ""
    return out


def export(run, rows, repetitions, main_threads):
    """Produce comprehensive raw and plot-ready CSVs from new observations only."""
    from collections import defaultdict
    results = run / "results"
    write_csv(results / "stage_runs.csv", rows)
    successful = [r for r in rows if r.get("status")=="ok" and r.get("exit_code")==0]
    groups = defaultdict(list)
    for r in successful:
        if r["stage"] in STAGES or r["stage"]=="alignment":
            groups[(r["configuration"],r["stage"],r["threads"],r.get("index",-1))].append(r)
    summaries = []
    for _, group in sorted(groups.items()):
        first = group[0]
        meta = {k:first[k] for k in ("configuration","experiment","dataset","stage","threads",
                                    "trace_capacity","alignment_capacity","constraints","family","activities",
                                    "case_id","index","roles","trace_length","alignment_length") if k in first}
        meta.update(statistics_for(group), complete=len(group)==repetitions,
                    expected_repetitions=repetitions, K=1)
        summaries.append(meta)
    write_csv(results / "stage_summary.csv", summaries)
    write_csv(results / "capacity_performance.csv", [r for r in summaries if r["experiment"]=="capacity"])
    write_csv(results / "model_scalability.csv", [r for r in summaries if r["experiment"]=="models"])
    pooled = defaultdict(list)
    for r in successful:
        if r["experiment"]=="real" and r["stage"] in STAGES:
            pooled[(r["dataset"],r["stage"],r["threads"])].append(r)
    table = []
    for (dataset, phase, threads), group in sorted(pooled.items()):
        table.append(dict(dataset=dataset,stage=phase,threads=threads,**statistics_for(group),
                          selected_cases=len({r.get('index',-1) for r in group}),
                          K=1, includes_AG=dataset=="sepsis" and phase not in ("compile","setup"),
                          memory_scope="whole-process OS peak RSS; decimal MB",
                          time_scope="operation_time excludes loading/output; worker_time includes full process"))
    write_csv(results / "per_log_performance.csv", table)
    paired = defaultdict(dict)
    for r in successful:
        if r["experiment"]=="real" and r.get("index",-1)>=0:
            paired[(r["dataset"],r["index"],r["threads"],r["repeat"])][r["stage"]] = r
    pairs = []
    for key, g in sorted(paired.items()):
        if not {"alignment","witness","prove","verify"} <= g.keys():
            continue
        base = g["prove"]
        pairs.append(dict(dataset=key[0],case_index=key[1],threads=key[2],repeat=key[3],
                          case_id=base["case_id"],roles=base["roles"],alignment_length=base["alignment_length"],
                          plaintext_operation_s=g["alignment"]["operation_seconds"],
                          zkalign_operation_s=sum(g[s]["operation_seconds"] for s in ("alignment","witness","prove")),
                          plaintext_worker_s=g["alignment"]["worker_seconds"],
                          zkalign_worker_s=sum(g[s]["worker_seconds"] for s in ("alignment","witness","prove")),
                          proof_bytes=base.get("proof_bytes"),bundle_bytes=base.get("bundle_bytes"),
                          verifier_operation_s=g["verify"]["operation_seconds"]))
    write_csv(results / "comparison_repetitions.csv", pairs)
    comparison = []
    pg = defaultdict(list)
    for r in pairs:
        pg[(r["dataset"],r["case_index"],r["threads"])].append(r)
    for _, group in sorted(pg.items()):
        base = group[0]
        if not any(role in base["roles"].split("+") for role in ("short","median","long")):
            continue
        for scope in ("operation","worker"):
            for method, name in (("PM4Py","plaintext"),("zkALIGN","zkalign")):
                vals=[r[f"{name}_{scope}_s"] for r in group]
                comparison.append(dict(**{k:base[k] for k in ("dataset","case_index","case_id","threads","roles","alignment_length")},
                                       method=method,time_scope=scope,time_mean_s=statistics.mean(vals),
                                       time_sd_s=statistics.stdev(vals) if len(vals)>1 else "",
                                       repetitions=len(vals),complete=len(vals)==repetitions,K=1,
                                       note="worker total is sum of separate processes; excludes compile/setup/verify"))
    write_csv(results / "plaintext_comparison.csv", comparison)


def run_suite(source, output_parent, binary, *, repetitions=5, threads=(1,14),
              experiments=("real","capacity","models"), seed=20261021, timeout=600):
    source, output_parent, binary = (Path(p).resolve() for p in (source, output_parent, binary))
    if repetitions<2 or not threads or min(threads)<1 or len(set(threads))!=len(threads):
        raise ValueError("Need at least two repetitions and distinct positive thread counts")
    if not set(experiments)<= {"real","capacity","models"} or not experiments:
        raise ValueError("Unknown or empty experiment selection")
    if not binary.is_file():
        raise FileNotFoundError(f"Worker binary not found: {binary}")
    specs = make_specs(source, experiments)
    jobs = schedule(specs,repetitions,seed)
    # Always append a unique child directory, even when --output-parent points
    # at an existing directory. No old results are resumed or replaced.
    output_parent.mkdir(parents=True,exist_ok=True)
    run=output_parent / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-"+uuid.uuid4().hex[:8])
    run.mkdir(mode=0o700)
    frozen_binary=run/"zkalign-eval"
    shutil.copy2(binary,frozen_binary)
    snapshots=run/"inputs"
    source_hashes={}
    for spec in specs:
        snap=snapshots/spec["id"]
        write_json(snap/"config.json",spec["config"])
        write_json(snap/"cases.json",spec["cases"])
        if spec["experiment"]=="real":
            for name in ("model.json","model.pnml"):
                p=Path(spec["source"])/name
                shutil.copy2(p,snap/name)
                source_hashes[str(p)]=digest(p)
        if "source" in spec:
            for name in ("config.json","cases.json"):
                p=Path(spec["source"])/name
                source_hashes[str(p)]=digest(p)
    def command_info(cmd):
        try:
            return subprocess.check_output(cmd,cwd=ROOT,text=True,stderr=subprocess.STDOUT).strip()
        except (OSError,subprocess.CalledProcessError):
            return "unavailable"
    manifest=dict(schema=2,repetitions=repetitions,thread_counts=list(threads),main_threads=max(threads),
                  experiments=list(experiments),seed=seed,schedule=jobs,
                  configurations=[{k:v for k,v in s.items() if k not in ('config','cases')} for s in specs],
                  source_hashes=source_hashes,binary_sha256=digest(frozen_binary),
                  binary_build_info=command_info(["go","version","-m",str(frozen_binary)]),
                  platform=platform.platform(),python=sys.version,cpu_count=os.cpu_count(),
                  git_revision=command_info(["git","rev-parse","HEAD"]),
                  git_status=command_info(["git","status","--short"]),
                  package_versions={p:importlib.metadata.version(p) for p in ("pm4py","numpy","pandas","psutil")},
                  new_runner_hashes={p.name:digest(p) for p in (Path(__file__),ROOT/"eval/measure_fresh_v2.py")},
                  measurement_method="blocking_wait4_v2", memory_metric="OS peak RSS in bytes; MB=1000000 bytes",
                  cache_policy="No cache flushing or artificial warm-up; randomized configuration blocks",
                  scope="Performance only; no utility/integrity rerun; real-log table includes AG")
    write_json(run/"manifest.json",manifest)
    env=os.environ.copy()
    env["PYTHONPATH"]=os.pathsep.join([str(ROOT),str(ROOT/"src"),env.get("PYTHONPATH","")])
    env["PYTHONDONTWRITEBYTECODE"]="1"
    rows=[]
    print(f"NEW RUN DIRECTORY: {run}",flush=True)
    print(f"{len(jobs)} configuration/repetition jobs; existing results are read-only.",flush=True)

    def collect(meta, folder, phase, *, thread_count, case=None, prefix="case", tag=None):
        print(f"[{meta['order']}/{len(jobs)}] {meta['configuration']} repeat {meta['repeat']} {phase} threads={thread_count} case={meta.get('case_id','-')}",flush=True)
        if phase=="alignment":
            result=folder/"measurements"/f"{tag}.json"
            measured=run_worker([sys.executable,"-m","eval.alignment_bench","--folder",str(folder),
                                 "--index",str(meta["index"]),"--result",str(result)],result,
                                timeout=timeout,env=env,cwd=ROOT)
        else:
            measured=stage(frozen_binary,folder,phase,threads=thread_count,case=case,
                           prefix=prefix,tag=tag,timeout=timeout,env=env)
        row=dict(meta,threads=thread_count,stage=phase,
                 **{k:v for k,v in measured.items() if k not in ("stage","constraints") and not isinstance(v,(dict,list))})
        row["constraints"]=measured.get("constraints",meta.get("constraints",0))
        row.update({f"{k}_bytes":v for k,v in measured.get("bytes",{}).items()})
        if phase=="verify" and measured.get("status")=="ok":
            report=measured.get("details",{})
            if report.get("certified")!=1:
                row.update(status="error",error="Expected exactly one certified case")
            row["certified"]=report.get("certified")
        rows.append(row)
        export(run,rows,repetitions,max(threads))
        if row.get("status")!="ok" or row.get("exit_code")!=0:
            raise RuntimeError(f"Failed {phase}; see {row.get('measurement_file')}: {row.get('error')}")
        return row

    try:
        for job in jobs:
            spec=specs[job["spec_index"]]
            folder=run/"work"/spec["id"]/f"repeat-{job['repeat']}"
            shutil.copytree(snapshots/spec["id"],folder)
            cfg=spec["config"]
            meta=dict(configuration=spec["id"],experiment=spec["experiment"],dataset=spec["dataset"],
                      repeat=job["repeat"],order=job["order"],K=1,
                      trace_capacity=cfg["trace_capacity"],alignment_capacity=cfg["alignment_capacity"])
            for key in ("family","activities"):
                if key in spec:meta[key]=spec[key]
            r=collect(meta,folder,"compile",thread_count=max(threads))
            meta["constraints"]=r["constraints"]
            for phase in ("setup","prepare","context"):
                collect(meta,folder,phase,thread_count=max(threads))
            selected=[c for c in spec["cases"] if str(c["index"]) in spec["roles"]]
            rng=random.Random(seed+job["order"])
            rng.shuffle(selected)
            thread_order=list(threads) if spec["experiment"]=="real" else [max(threads)]
            rng.shuffle(thread_order)
            for count in thread_order:
                for c in selected:
                    case_meta=dict(meta,index=c["index"],case_id=c["case_id"],roles=spec["roles"][str(c["index"])],
                                   trace_length=len(c["events"]),alignment_length=len(c["moves"]))
                    prefix=f"t{count}-case-{c['index']}"
                    if spec["experiment"]=="real":
                        collect(case_meta,folder,"alignment",thread_count=count,tag=f"{prefix}-alignment")
                    for phase in ("witness","prove","verify"):
                        collect(case_meta,folder,phase,thread_count=count,case=folder/f"private-{c['index']}.json",
                                prefix=prefix,tag=f"{prefix}-{phase}")
            write_json(folder/"complete.json",dict(order=job["order"],repeat=job["repeat"],status="ok"))
        for path, expected in source_hashes.items():
            if digest(path)!=expected:raise RuntimeError(f"Source changed during run: {path}")
        write_json(run/"complete.json",dict(status="ok",jobs=len(jobs),measurements=len(rows)))
    except BaseException as exc:
        write_json(run/"failed.json",dict(error=str(exc),measurements=len(rows)))
        print(f"Stopped; partial results preserved in {run}. Nothing was overwritten in the old evaluation.",flush=True)
        raise
    print(f"Complete. New CSVs: {run / 'results'}",flush=True)
    print(f'Plot command: PYTHONPATH=src .venv/bin/python -m eval.plotting.performance_rerun_v2 --run "{run}"',flush=True)
    return run


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",type=Path,default=ROOT/"outputs/evaluation")
    p.add_argument("--output-parent",type=Path,default=ROOT/"outputs/performance-reruns-v2")
    p.add_argument("--binary",type=Path,default=ROOT/"build/zkalign-eval")
    p.add_argument("--repeat",type=int,default=5)
    p.add_argument("--threads",type=int,nargs="+",default=sorted({1,os.cpu_count() or 1}))
    p.add_argument("--experiments",nargs="+",choices=["real","capacity","models"],default=["real","capacity","models"])
    p.add_argument("--seed",type=int,default=20261021)
    p.add_argument("--timeout",type=float,default=600)
    a=p.parse_args()
    run_suite(a.source,a.output_parent,a.binary,repetitions=a.repeat,threads=tuple(a.threads),
              experiments=tuple(a.experiments),seed=a.seed,timeout=a.timeout)


if __name__=="__main__":
    main()
