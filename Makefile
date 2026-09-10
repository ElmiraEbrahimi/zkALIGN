.PHONY: setup data pre-zkp prove test

setup:
	python3 -m venv .venv
	.venv/bin/python -m pip install '.[process-mining]'

data:
	python3 scripts/download_sepsis.py

pre-zkp: data
	.venv/bin/python scripts/healthcare_pipeline.py

prove:
	go run ./cmd/zkalign-proof -case AG -threshold 1

test:
	PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
	go test ./...
