"""Independent fresh-process timing and OS peak RSS, without exit polling.

Nothing in the original measurement module is modified. This module deliberately
does not sample RSS: wait4 supplies the child's lifetime RSS high-water mark.
"""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time


def run_worker(command, result, *, timeout=600, env=None, cwd=None):
    """Run once in a fresh result location; never overwrite an earlier receipt.

    Timing includes Popen and blocking wait4. It excludes opening output logs,
    JSON parsing and writing the combined receipt. OS scheduling latency remains;
    unlike the original harness there is no periodic exit-detection sleep.
    """
    if not hasattr(os, "wait4") or sys.platform not in ("darwin", "linux"):
        raise RuntimeError("This measurement method requires macOS or Linux")
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    result = Path(result)
    receipt = result.with_suffix(".receipt.json")
    stdout = result.with_suffix(".stdout.log")
    stderr = result.with_suffix(".stderr.log")
    if any(p.exists() for p in (result, receipt, stdout, stderr)):
        raise FileExistsError(f"Measurement already exists: {result}")
    result.parent.mkdir(parents=True, exist_ok=True)
    ready, finished = threading.Event(), threading.Event()
    state = {}

    def kill_child():
        try:
            os.killpg(state["pid"], signal.SIGKILL)
        except ProcessLookupError:
            pass

    def watchdog():
        ready.wait()
        if "pid" in state and not finished.wait(timeout):
            state["timed_out"] = True
            kill_child()

    # Start the timeout thread before the measured interval. It only wakes on
    # termination or timeout and never polls for completion or reads process RSS.
    guard = threading.Thread(target=watchdog, daemon=True)
    guard.start()
    try:
        with stdout.open("x") as out, stderr.open("x") as err:
            start_ns = time.perf_counter_ns()
            child = subprocess.Popen(command, stdout=out, stderr=err, env=env,
                                     cwd=cwd, start_new_session=True)
            state["pid"] = child.pid
            ready.set()
            try:
                _, status, usage = os.wait4(child.pid, 0)
                end_ns = time.perf_counter_ns()
            except BaseException:
                kill_child()
                _, status, _ = os.wait4(child.pid, 0)
                child.returncode = os.waitstatus_to_exitcode(status)
                raise
            finally:
                finished.set()
            child.returncode = os.waitstatus_to_exitcode(status)
    finally:
        finished.set()
        ready.set()
        guard.join()
    try:
        data = json.loads(result.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        data = {"status": "error", "error": "worker returned no valid measurement"}
    if not isinstance(data, dict):
        data = {"status": "error", "error": "worker measurement is not an object"}
    if child.returncode or state.get("timed_out"):
        data.update(status="error", error="timeout" if state.get("timed_out")
                    else data.get("error", f"exit {child.returncode}"))
    data.update(
        worker_seconds=(end_ns - start_ns) / 1e9,
        process_peak_rss_bytes=int(usage.ru_maxrss) * (1 if sys.platform == "darwin" else 1024),
        user_cpu_seconds=usage.ru_utime, system_cpu_seconds=usage.ru_stime,
        pid=child.pid, exit_code=child.returncode,
        measurement_method="blocking_wait4_v2",
        worker_time_scope="process launch through blocking wait4 return; no exit polling",
        memory_scope="whole-process OS peak RSS, including runtime, loaded inputs and serialization",
        operation_memory_scope="not measured; no sampled-operation RSS is inferred",
        measurement_file=str(receipt), worker_measurement_file=str(result),
        command=list(map(str, command)),
    )
    with receipt.open("x") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")
    return data


def stage(binary, folder, name, *, case=None, k=1, prefix="case", tag=None,
          threads=14, timeout=600, env=None):
    folder = Path(folder).resolve()
    result = folder / "measurements" / f"{tag or name}.json"
    command = [str(binary), "-stage", name, "-dir", str(folder),
               "-threshold", str(k), "-prefix", prefix, "-result", str(result)]
    if case is not None:
        command += ["-case", str(case)]
    child_env = dict(os.environ if env is None else env)
    child_env["GOMAXPROCS"] = str(threads)
    data = run_worker(command, result, timeout=timeout, env=child_env)
    if data.get("status") == "ok" and data.get("gomaxprocs") != threads:
        raise RuntimeError("Worker GOMAXPROCS does not match requested threads")
    return data
