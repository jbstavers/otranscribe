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
	@echo "  make doctor          Run otranscribe doctor"
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
	@$(VENV)/bin/otranscribe doctor

clean:
	@rm -rf $(VENV) .pytest_cache .otranscribe_cache **/__pycache__