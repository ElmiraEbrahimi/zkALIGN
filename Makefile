.PHONY: setup data pre-zkp test

setup:
	python3 -m venv .venv
	.venv/bin/python -m pip install '.[process-mining]'

data:
	python3 scripts/download_sepsis.py

pre-zkp: data
	.venv/bin/python scripts/healthcare_pipeline.py

test:
	PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
	go test ./...
