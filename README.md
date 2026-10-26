# zkALIGN

zkALIGN verifies alignment-based conformance claims with zero-knowledge proofs.
A log owner proves that a committed trace admits a valid, complete alignment
within a public cost threshold, without revealing the trace, alignment, or
exact cost. Python and PM4Py prepare the inputs; Go and gnark generate and
verify Groth16 proofs over BN254.

## Installation

Requirements: Python 3.11 or later, Go 1.25.7 or later, Git, Make, and curl.
The optional Sepsis demonstration also requires Graphviz.

```bash
git clone https://github.com/ElmiraEbrahimi/zkALIGN.git
cd zkALIGN
python3 -m venv .venv
.venv/bin/python -m pip install '.[evaluation]'
go mod download
```

## Download the datasets

The evaluation uses BPI Challenge 2013 Closed Problems, Road Traffic Fine
Management, Sepsis Cases, and Hospital Billing. Download all four public logs
and verify their pinned fingerprints:

```bash
PYTHONPATH=src .venv/bin/python -m eval.data --download-only
```

Source links and local filenames are listed in [datasets/README.md](datasets/README.md).
Raw logs are cached locally and are not redistributed in this repository.

## Run

Run the tests and complete four-log evaluation:

```bash
make eval
```

This downloads any missing datasets, prepares the models and alignments,
generates and verifies proofs, runs the benchmarks, and summarizes the results.
A complete evaluation can take several hours. Outputs are saved under
`outputs/evaluation/`; [eval/README.md](eval/README.md) lists individual commands.

For a single-case Sepsis demonstration:

```bash
make pre-zkp
make prove
```

Run tests without starting the evaluation with `make eval-test`.
Private witnesses, salts, keys, and local runs remain in Git-ignored directories.
