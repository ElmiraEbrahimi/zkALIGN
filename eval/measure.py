"""Fresh-process measurements; never use cumulative child-process peaks."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
import psutil


def run_worker(
    command, result, *, timeout=600, interval=0.005, env=None, memory_limit=20 * 1024**3
):
    result = Path(result)
    result.parent.mkdir(parents=True, exist_ok=True)
    if result.exists():
        result.unlink()
    # Each measurement has its own logs. File redirection avoids pipe-buffer deadlocks.
    start = time.perf_counter()
    samples = []
    reason = None
    usage = None
    with (
        result.with_suffix(".stdout.log").open("w") as out,
        result.with_suffix(".stderr.log").open("w") as err,
    ):
        child = subprocess.Popen(
            command, stdout=out, stderr=err, env=env, start_new_session=True
        )
        proc = psutil.Process(child.pid)
        while True:
            try:
                rss = proc.memory_info().rss
                samples.append((time.time_ns(), rss))
                if rss > memory_limit and reason is None:
                    reason = "memory_limit"
                    os.killpg(child.pid, signal.SIGKILL)
            except psutil.NoSuchProcess:
                pass
            pid, status, usage_now = os.wait4(child.pid, os.WNOHANG)
            if pid:
                usage = usage_now
                child.returncode = os.waitstatus_to_exitcode(status)
                break
            if time.perf_counter() - start > timeout and reason is None:
                reason = "timeout"
                os.killpg(child.pid, signal.SIGKILL)
            time.sleep(interval)
    elapsed = time.perf_counter() - start
    try:
        data = json.loads(result.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        data = {"status": "error", "error": reason or "worker returned no measurement"}
    # A failed re-run cannot inherit an old successful result.
    if child.returncode:
        data["status"] = "error"
        data["error"] = reason or data.get("error", f"exit {child.returncode}")
    operation = [
        rss
        for ns, rss in samples
        if data.get("start_ns", 0) <= ns <= data.get("end_ns", 0)
    ]
    peak = int(usage.ru_maxrss) * (1 if sys.platform == "darwin" else 1024)
    data.update(
        worker_seconds=elapsed,
        process_peak_rss_bytes=peak,
        sampled_operation_peak_rss_bytes=max(operation) if operation else None,
        operation_samples=len(operation),
        sample_interval_seconds=interval,
        worker_samples=len(samples),
        pid=child.pid,
        exit_code=child.returncode,
        user_cpu_seconds=usage.ru_utime,
        system_cpu_seconds=usage.ru_stime,
    )
    result.write_text(json.dumps(data, indent=2) + "\n")
    return data


def stage(
    binary,
    folder,
    name,
    *,
    case=None,
    k=1,
    prefix="case",
    tag=None,
    threads=None,
    timeout=600,
):
    folder = Path(folder)
    result = folder / "measurements" / ((tag or f"{name}-{prefix}") + ".json")
    # Remove only a previous measurement at this exact generated path, never keys.
    if result.exists():
        result.unlink()
    cmd = [
        str(binary),
        "-stage",
        name,
        "-dir",
        str(folder),
        "-threshold",
        str(k),
        "-prefix",
        prefix,
        "-result",
        str(result),
    ]
    if case is not None:
        cmd.extend(["-case", str(case)])
    env = os.environ.copy()
    if threads is not None:
        env["GOMAXPROCS"] = str(threads)
    data = run_worker(cmd, result, env=env, timeout=timeout)
    data["measurement_file"] = str(result)
    return data
