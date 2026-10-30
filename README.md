# zkALIGN

zkALIGN lets organizations show auditors that recorded process executions
conform to a process model without sharing sensitive event logs. It uses
zero-knowledge proofs to verify that a committed trace has a complete, valid
alignment within an agreed cost threshold, while keeping the trace, alignment,
and exact cost private.

The implementation uses Python and PM4Py for alignment computation and Go
with gnark for Groth16 proof generation and verification.

## Installation

Requirements: Python 3.11 or later, Go 1.25.7 or later, Git, Make, and curl.
The optional Sepsis demonstration also requires Graphviz.

Download and extract the repository ZIP, then open a terminal in the extracted
project directory.

```bash
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
Generated results in `eval/results/` are also local and Git-ignored.
