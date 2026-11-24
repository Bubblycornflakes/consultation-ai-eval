#!/bin/zsh
# Double-click to open the labelling page. Needs the project's .venv (see the README quick start).
cd "$(dirname "$0")/.." && .venv/bin/python -m src.human_check serve
