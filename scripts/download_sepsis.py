from __future__ import annotations

import sys
import subprocess
import urllib.request
from pathlib import Path

URL = "https://ndownloader.figshare.com/files/24061976"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from zkalign.mimc import file_mimc

# Project-local MiMC pin of the publisher-checksummed dataset, not a checksum
# claimed to have been published by 4TU. Provenance is documented in datasets/.
EXPECTED_MIMC = "2609148250783286284f49dc67220f63465834e094537a61537001312044c01f"
DESTINATION = ROOT / "datasets" / "raw" / "Sepsis Cases - Event Log.xes.gz"


def main() -> int:
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    if not DESTINATION.exists():
        print(f"Downloading public Sepsis Cases log to {DESTINATION}")
        try:
            urllib.request.urlretrieve(URL, DESTINATION)
        except Exception as error:
            # Some macOS Python installations do not know the system CA path.
            # curl uses the system trust store; checksum validation still guards
            # against receiving a different file.
            DESTINATION.unlink(missing_ok=True)
            print(f"Python HTTPS failed ({error}); retrying with curl")
            subprocess.run(
                ["curl", "--fail", "--location", "--output", str(DESTINATION), URL],
                check=True,
            )
    actual = file_mimc(DESTINATION)
    if actual != EXPECTED_MIMC:
        raise RuntimeError(
            f"checksum mismatch for {DESTINATION}: expected {EXPECTED_MIMC}, got {actual}"
        )
    print(f"Verified {DESTINATION.name}: MiMC {actual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
