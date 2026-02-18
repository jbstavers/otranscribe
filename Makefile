VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: help venv install install-local install-faster test doctor clean

help:
	@echo "Targets:"
	@echo "  make venv            Create virtual environment (.venv)"
	@echo "  make install         Install package (editable) + dev deps"
	@echo "  make install-local   Install local whisper extra"
	@echo "  make install-faster  Install faster-whisper extra"
	@echo "  make test            Run pytest"
	@echo "  make doctor          Run diagnostics (non-blocking)"
	@echo "  make doctor-openai   Check OpenAI engine requirements"
	@echo "  make doctor-local    Check local Whisper requirements"
	@echo "  make doctor-faster   Check faster-whisper requirements"
	@echo "  make clean           Remove venv + caches"

venv:
	@test -d $(VENV) || python3 -m venv $(VENV)
	@$(PY) -m pip install -U pip

install: venv
	@$(PIP) install -e ".[dev]"

install-local: venv
	@$(PIP) install -e ".[local]"

install-faster: venv
	@$(PIP) install -e ".[faster]"

test: install
	@$(VENV)/bin/pytest -q

doctor: install
	@$(VENV)/bin/otranscribe doctor || true

doctor-openai: install
	@$(VENV)/bin/otranscribe doctor --engine openai

doctor-local: install
	@$(VENV)/bin/otranscribe doctor --engine local

doctor-faster: install
	@$(VENV)/bin/otranscribe doctor --engine faster

clean:
	@rm -rf $(VENV) .pytest_cache .otranscribe_cache **/__pycache__