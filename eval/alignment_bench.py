"""Fresh-process unit-cost alignment timing on a previously frozen model/case."""

import argparse
import json
import time
from pathlib import Path
import pm4py
from pm4py.objects.log.obj import Trace, Event
from eval.data import align, save


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--folder", type=Path, required=True)
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--result", type=Path, required=True)
    a = p.parse_args()
    cfg = json.loads((a.folder / "model.json").read_text())
    reverse = {v: k for k, v in cfg["activity_encoding"].items()}
    cases = json.loads((a.folder / "cases.json").read_text())
    c = next(c for c in cases if c["index"] == a.index)
    net, im, fm = pm4py.read_pnml(str(a.folder / "model.pnml"))
    trace = Trace([Event({"concept:name": reverse[e]}) for e in c["events"]])
    start_ns = time.time_ns()
    start = time.perf_counter()
    r = align(trace, net, im, fm)
    seconds = time.perf_counter() - start
    end_ns = time.time_ns()
    good = r is not None and r["cost"] == c["cost"]
    save(
        a.result,
        {
            "stage": "alignment",
            "status": "ok" if good else "error",
            "error": "" if good else "reference changed or timed out",
            "start_ns": start_ns,
            "end_ns": end_ns,
            "operation_seconds": seconds,
        },
    )
    if not good:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
