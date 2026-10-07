import sys
import tempfile
import unittest
from pathlib import Path
from eval.measure import run_worker

class MeasurementTests(unittest.TestCase):
    def test_large_then_small_has_independent_peak(self):
        with tempfile.TemporaryDirectory() as tmp:
            def run(mb,name):
                return run_worker([sys.executable,"-c",
                    f"import time; x=bytearray({mb}*1024*1024); time.sleep(.08)"],
                    Path(tmp)/(name+".json"))
            large=run(160,"large");small=run(1,"small")
            self.assertNotEqual(large["pid"],small["pid"])
            self.assertGreater(large["process_peak_rss_bytes"],small["process_peak_rss_bytes"]+100*1024**2)
    def test_timeout_is_not_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=run_worker([sys.executable,"-c","import time;time.sleep(10)"],
                         Path(tmp)/"timeout.json",timeout=.03)
            self.assertEqual(r["error"],"timeout")
            self.assertNotEqual(r["exit_code"],0)

if __name__=="__main__":unittest.main()

