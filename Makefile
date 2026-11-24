# One command for each step. `make all` runs everything and skips conversations that already have a result.
# Needs Ollama running with qwen3:8b pulled (about 5 GB) for the steps that run conversations.
PY = .venv/bin/python
CASES = C01 C02 C03 C04 C05
V2 = --patient-version 2 --interviewer-version 2 --gating --skip-existing

.PHONY: help setup test check v1 v2 swaps score fairness report plots label all
help:
	@echo "make setup      create .venv and install the pinned packages"
	@echo "make test       run the unit tests (no model needed)"
	@echo "make check      check the case files and the scorer's match terms"
	@echo "make all        tests, check, v1, v2, swaps, score, fairness, report, plots"
	@echo "make label      open the page for hand-labelling the 8 transcripts"

setup:
	python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt

test:
	$(PY) -m pytest -q

check:
	$(PY) -m src.cases check

v1:
	$(PY) -m src.run conversations --cases $(CASES) --condition v1 --skip-existing --out results/stage2

v2:
	$(PY) -m src.run conversations --cases $(CASES) --runs 3 $(V2) --condition v2 --out results/stage2_v2

swaps:
	$(PY) -m src.run conversations --cases $(CASES) --variant gender-swap $(V2) --lenient-end --condition v2.1-gender-swap --out results/fairness_gender
	$(PY) -m src.run conversations --cases $(CASES) --variant age-swap $(V2) --lenient-end --condition v2.1-age-swap --out results/fairness_age

score:
	$(PY) -m src.score results/stage2 --label v1
	$(PY) -m src.score results/stage2_v2 --label v2
	$(PY) -m src.score results/fairness_gender --label gender-swap
	$(PY) -m src.score results/fairness_age --label age-swap

fairness:
	$(PY) -m src.fairness

report:
	$(PY) -m src.report

plots:
	$(PY) -m src.plots

label:
	$(PY) -m src.human_check serve

all: test check v1 v2 swaps score fairness report plots
