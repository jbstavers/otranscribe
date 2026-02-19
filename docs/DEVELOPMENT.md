# Development

This guide is for contributors and maintainers working from a clone.

## Setup

### macOS/Linux

From the repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -e ".[dev]"
```

Verify:

```bash
which otranscribe
otranscribe --help
python -c "import otranscribe; print(otranscribe.__file__)"
```

### Windows (PowerShell)

Create and activate the venv:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Then:

```bash
python -m pip install -U pip
pip install -e ".[dev]"
pytest
```

## Run tests

```bash
pytest
```

## Formatting and linting

This repo uses:

- **Black** for code formatting
- **Ruff** for linting and safe fixes
- **pre-commit** to run checks locally and in CI
- **.editorconfig** to align editor defaults (UTF-8, LF, final newline)
- **.gitattributes** to enforce LF line endings

### Run all hooks

```bash
pre-commit run --all-files
```

If `pre-commit` is not found, install dev dependencies:

```bash
pip install -e ".[dev]"
```

You can always run pre-commit via Python:

```bash
python -m pre_commit run --all-files
```

### Run tools directly

```bash
black .
ruff check --fix .
```

## Enable pre-commit on every commit (recommended)

Install the commit hook:

```bash
pre-commit install
```

Optional: also run checks on `git push`:

```bash
pre-commit install --hook-type pre-push
```

To disable hooks:

```bash
pre-commit uninstall
```

## Make targets (if available)

```bash
make install
make test

# diagnostics
make doctor
make doctor-openai
make doctor-local
make doctor-faster
```

## Quickstart without Make (macOS/Linux)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -e ".[dev]"
pytest
otranscribe doctor
```

## Helper scripts

```bash
./scripts/bootstrap.sh
./scripts/test.sh
```

## Before submitting a PR

Ensure all checks pass:

```bash
pre-commit run --all-files
pytest
```

Then open a pull request on the project repository. See [CONTRIBUTING.md](./CONTRIBUTING.md) for PR workflow and branch naming.
