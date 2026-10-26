"""Tests use tiny subprocesses and mocked benchmarks, never the paper evaluation."""

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from eval.measure_fresh_v2 import run_worker
from eval.performance_rerun_v2 import (make_specs, run_suite, schedule, statistics_for,
                                       export, write_json, digest)


class FreshMeasurementTests(unittest.TestCase):
    def worker(self, path, mb=1, delay=.02, exit_code=0):
        script=("import json,sys,time; from pathlib import Path; "
                f"x=bytearray({mb}*1024*1024); "
                "start=time.perf_counter(); "
                f"time.sleep({delay}); "
                "elapsed=time.perf_counter()-start; "
                "Path(sys.argv[1]).write_text(json.dumps({'status':'ok','stage':'test','operation_seconds':elapsed})); "
                f"sys.exit({exit_code})")
        return [sys.executable,"-c",script,str(path)]

    def test_blocking_wait_and_independent_rss(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch("eval.measure_fresh_v2.os.wait4",wraps=os.wait4) as wait:
                a=run_worker(self.worker(root/"large.json",96),root/"large.json")
                b=run_worker(self.worker(root/"small.json"),root/"small.json")
            self.assertTrue(all(call.args[1]==0 for call in wait.call_args_list))
            self.assertEqual(a["status"],"ok")
            self.assertGreater(a["process_peak_rss_bytes"],b["process_peak_rss_bytes"]+60*1024**2)
            self.assertGreater(a["worker_seconds"],a["operation_seconds"])
            self.assertNotEqual(a["pid"],b["pid"])
            self.assertEqual(json.loads((root/"large.json").read_text())["status"],"ok")
            self.assertTrue((root/"large.receipt.json").exists())
            self.assertNotIn("sampled_operation_peak_rss_bytes",a)

    def test_timeout_and_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"timeout.json"
            r=run_worker(self.worker(p,delay=10),p,timeout=.05)
            self.assertEqual(r["error"],"timeout")
            self.assertNotEqual(r["exit_code"],0)
            p=Path(tmp)/"failed.json"
            r=run_worker(self.worker(p,exit_code=3),p)
            self.assertEqual(r["status"],"error")
            self.assertEqual(r["exit_code"],3)

    def test_existing_result_is_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"old.json";p.write_text("original")
            with self.assertRaises(FileExistsError):run_worker(self.worker(p),p)
            self.assertEqual(p.read_text(),"original")

    def test_spawn_error_does_not_hang_watchdog(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                run_worker([str(Path(tmp)/"missing")],Path(tmp)/"result.json")


class SuiteTests(unittest.TestCase):
    def test_randomized_blocks_are_complete_and_reproducible(self):
        specs=[{} for _ in range(33)]
        jobs=schedule(specs,5,42)
        self.assertEqual(jobs,schedule(specs,5,42))
        self.assertEqual([j["order"] for j in jobs],list(range(1,166)))
        for r in range(1,6):
            ids=[j["spec_index"] for j in jobs if j["repeat"]==r]
            self.assertEqual(sorted(ids),list(range(33)))
            self.assertNotEqual(ids,sorted(ids))

    def test_statistics_use_sample_sd(self):
        rows=[dict(operation_seconds=v,worker_seconds=2*v,process_peak_rss_bytes=v*1e6,
                   user_cpu_seconds=v,system_cpu_seconds=v) for v in (1,3)]
        s=statistics_for(rows)
        self.assertEqual(s["mem_mean_mb"],2)
        self.assertAlmostEqual(s["mem_sd_mb"],2**.5)
        self.assertEqual(s["worker_time_mean_s"],4)

    def tiny_spec(self):
        return dict(id="capacity-32",experiment="capacity",dataset="sepsis",
                    config={"trace_capacity":185,"alignment_capacity":32},
                    cases=[dict(index=0,case_id="AG",events=[1],moves=[{}],cost=0)],roles={"0":"AG"})

    def fake_stage(self,binary,folder,name,**kwargs):
        return dict(status="ok",stage=name,exit_code=0,operation_seconds=.1,
                    worker_seconds=.2,process_peak_rss_bytes=20_000_000,
                    user_cpu_seconds=.3,system_cpu_seconds=.01,constraints=123,
                    bytes={"proof":164,"pk":1000},details={"certified":1},
                    measurement_method="blocking_wait4_v2")

    def test_runs_are_unique_originals_preserved_and_all_stages_captured(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);binary=root/"binary";binary.write_bytes(b"mock worker")
            old=root/"old.csv";old.write_text("do not change")
            before=digest(old)
            with patch("eval.performance_rerun_v2.make_specs",return_value=[self.tiny_spec()]), \
                 patch("eval.performance_rerun_v2.stage",side_effect=self.fake_stage) as worker, \
                 redirect_stdout(io.StringIO()):
                a=run_suite(root,root,binary,repetitions=5,threads=(1,14),experiments=("capacity",))
                b=run_suite(root,root,binary,repetitions=5,threads=(1,14),experiments=("capacity",))
            self.assertNotEqual(a,b)
            self.assertEqual(worker.call_count,70)
            self.assertEqual(digest(old),before)
            raw=pd.read_csv(a/"results/stage_runs.csv")
            self.assertEqual(len(raw),35)
            summary=pd.read_csv(a/"results/capacity_performance.csv")
            self.assertEqual(len(summary),5)
            self.assertTrue(summary.complete.all())
            self.assertTrue(summary.observations.eq(5).all())
            self.assertTrue((a/"complete.json").exists())

    def test_invalid_verification_stops_without_complete_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);binary=root/"binary";binary.write_bytes(b"mock")
            def invalid(*args,**kwargs):
                row=self.fake_stage(*args,**kwargs)
                row["details"]={"certified":0}
                return row
            with patch("eval.performance_rerun_v2.make_specs",return_value=[self.tiny_spec()]), \
                 patch("eval.performance_rerun_v2.stage",side_effect=invalid),redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError,"exactly one"):
                    run_suite(root,root,binary,repetitions=5,threads=(14,),experiments=("capacity",))
            directories=[p for p in root.iterdir() if p.is_dir()]
            self.assertEqual(len(directories),1)
            self.assertFalse((directories[0]/"complete.json").exists())
            self.assertTrue((directories[0]/"failed.json").exists())
            self.assertIn("error",(directories[0]/"results/stage_runs.csv").read_text())

    def test_comparison_is_paired_and_ag_is_not_plotted(self):
        with tempfile.TemporaryDirectory() as tmp:
            run=Path(tmp);rows=[]
            for index,role in ((0,"short"),(1,"AG")):
                for repeat in range(1,6):
                    for phase,value in (("alignment",1),("witness",.1),("prove",2),("verify",.01)):
                        rows.append(dict(configuration="real-sepsis",experiment="real",dataset="sepsis",stage=phase,
                                         threads=14,index=index,repeat=repeat,case_id=role,roles=role,
                                         alignment_length=18,trace_length=5,trace_capacity=185,alignment_capacity=384,
                                         constraints=123,status="ok",exit_code=0,operation_seconds=value,
                                         worker_seconds=value+.5,process_peak_rss_bytes=1e6,
                                         user_cpu_seconds=.1,system_cpu_seconds=.1))
            export(run,rows,5,14)
            pairs=pd.read_csv(run/"results/comparison_repetitions.csv")
            self.assertTrue(pairs.zkalign_operation_s.eq(3.1).all())
            self.assertTrue(pairs.zkalign_worker_s.eq(4.6).all())
            figure=pd.read_csv(run/"results/plaintext_comparison.csv")
            self.assertEqual(set(figure.roles),{"short"})
            self.assertEqual(set(figure.time_scope),{"worker","operation"})
            table=pd.read_csv(run/"results/per_log_performance.csv")
            self.assertTrue(table.observations.eq(10).all())

    def test_all_real_inputs_and_model_configurations_fit(self):
        from eval.performance_rerun_v2 import ROOT
        source=ROOT/"outputs/evaluation"
        if not (source/"data/sepsis/cases.json").exists():
            self.skipTest("Frozen local data unavailable")
        specs=make_specs(source,("real","capacity","models"))
        self.assertEqual(len(specs),33)
        counts={s["dataset"]:len(s["roles"]) for s in specs if s["experiment"]=="real"}
        self.assertEqual(counts,{"bpic13cp":3,"rtfm":3,"sepsis":4,"hospital":3})
        for s in specs:
            for c in s["cases"]:
                if str(c["index"]) in s["roles"]:
                    self.assertLessEqual(len(c["events"]),s["config"]["trace_capacity"])
                    self.assertLessEqual(len(c["moves"]),s["config"]["alignment_capacity"])

    def test_plotting_keeps_scopes_separate_and_accepts_larger_new_results(self):
        from matplotlib.figure import Figure
        from eval.plotting.performance_rerun_v2 import generate
        with tempfile.TemporaryDirectory() as tmp:
            run=Path(tmp)
            write_json(run/"manifest.json",dict(main_threads=14,repetitions=5))
            write_json(run/"complete.json",dict(status="ok"))
            (run/"results").mkdir()
            capacity=[]
            for bound in (32,64,128,256,384):
                for phase in ("compile","setup","witness","prove","verify"):
                    capacity.append(dict(stage=phase,alignment_capacity=bound,threads=14,complete=True,
                                         operation_time_mean_s=.1*bound,operation_time_sd_s=.01,
                                         worker_time_mean_s=.2*bound,worker_time_sd_s=.02,
                                         mem_mean_mb=10*bound,mem_sd_mb=3))
            pd.DataFrame(capacity).to_csv(run/"results/capacity_performance.csv",index=False)
            captured=[]
            def capture(fig,path,*a,**kw):
                captured.append((str(path),fig.axes[0].get_ylim(),fig.axes[1].get_ylim()))
            with patch.object(Figure,"savefig",capture):
                first=generate(run);second=generate(run)
            self.assertEqual(len(first),2)
            self.assertNotEqual(first[0].parent,second[0].parent)
            for path,ylim,mlim in captured:
                self.assertGreater(ylim[1],76.8 if "complete_process" in path else 38.4)
                self.assertGreater(mlim[1],3840)


if __name__=="__main__":unittest.main()
