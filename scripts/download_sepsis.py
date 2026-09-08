from __future__ import annotations

import hashlib
import subprocess
import urllib.request
from pathlib import Path

URL = "https://ndownloader.figshare.com/files/24061976"
EXPECTED_MD5 = "b5671166ac71eb20680d3c74616c43d2"
ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "datasets" / "raw" / "Sepsis Cases - Event Log.xes.gz"


def md5(path: Path) -> str:
    digest = hashlib.md5()  # nosec B324 - required only for published file verification
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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
    actual = md5(DESTINATION)
    if actual != EXPECTED_MD5:
        raise RuntimeError(
            f"checksum mismatch for {DESTINATION}: expected {EXPECTED_MD5}, got {actual}"
        )
    print(f"Verified {DESTINATION.name}: MD5 {actual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
