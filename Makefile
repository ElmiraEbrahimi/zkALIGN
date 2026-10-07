.PHONY: setup data pre-zkp prove test eval eval-test eval-core eval-scalability eval-report

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

eval-test: test
	PYTHONPATH=src .venv/bin/python -m unittest discover -s eval -p 'test_*.py' -v

eval-core:
	PYTHONPATH=src .venv/bin/python -m eval.run

# Sequential execution prevents competing benchmarks contaminating timings.
eval-scalability:
	go build -o build/zkalign-eval ./cmd/zkalign-eval
	PYTHONPATH=src .venv/bin/python -m eval.scalability --mode repeats
	PYTHONPATH=src .venv/bin/python -m eval.scalability --mode capacity
	PYTHONPATH=src .venv/bin/python -m eval.scalability --mode models
	PYTHONPATH=src .venv/bin/python -m eval.scalability --mode population
	PYTHONPATH=src .venv/bin/python -m eval.scalability --mode integrity

eval-report:
	PYTHONPATH=src .venv/bin/python -m eval.run --collect-only
	PYTHONPATH=src .venv/bin/python -m eval.report

eval:
	$(MAKE) eval-test
	$(MAKE) eval-core
	$(MAKE) eval-scalability
	$(MAKE) eval-report
