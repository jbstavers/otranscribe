# Installation

## Prerequisites

Before installing `otranscribe` you need:

- **Python 3.9+** – the code is tested with 3.9 and newer.
- **ffmpeg** – used to extract audio from videos and normalise input. You must install this separately and ensure the `ffmpeg` binary is on your `PATH`.
- **Requests** – installed automatically via package dependencies.
- **OpenAI API key** – only required when using the OpenAI engine.

Optional backends:
- **openai-whisper** – required only if you plan to use the local engine.
- **faster-whisper** – required only if you plan to use the faster engine (depends on [CTranslate2](https://github.com/OpenNMT/CTranslate2); can leverage GPU).

### Installing ffmpeg

`otranscribe` relies on the external `ffmpeg` program. Install via your operating system:

- **macOS**: `brew install ffmpeg`
- **Ubuntu/Debian**: `sudo apt-get install ffmpeg`
- **Windows**: Install via [Chocolatey](https://chocolatey.org/) (`choco install ffmpeg`) or download the static build from [ffmpeg.org](https://ffmpeg.org/) and add the `bin` directory to your `PATH`.

Verify: `ffmpeg -version`

## Install otranscribe

### Option A: From PyPI (core + OpenAI API only)

```bash
# install globally using pipx (recommended)
pipx install otranscribe

# or install into the current environment
pip install otranscribe

# with local Whisper engine
pip install otranscribe[local]

# with faster-whisper engine
pip install otranscribe[faster]

# with both offline engines
pip install otranscribe[local,faster]
```

### Option B: From source (recommended for development)

```bash
git clone <repo-url>
cd otranscribe
python3 -m venv .venv
source .venv/bin/activate  # on Windows: .\.venv\Scripts\Activate.ps1
pip install -U pip
pip install -e .
```

With optional engines:

```bash
pip install -e ".[local]"       # local Whisper
pip install -e ".[faster]"      # faster-whisper
pip install -e ".[dev]"         # development (pytest, linting, etc.)
pip install -e ".[local,faster,dev]"  # all
```

### Option C: Requirements files (source only)

```bash
git clone <repo-url>
cd otranscribe
python3 -m venv .venv
source .venv/bin/activate

pip install -U pip
pip install -r requirements.txt        # core
pip install -r requirements-local.txt  # optional: local engine
pip install -r requirements-faster.txt # optional: faster engine
pip install -e .
```

### Verify installation

```bash
which otranscribe          # or: where otranscribe (Windows)
otranscribe --help
python -c "import otranscribe; print(otranscribe.__file__)"
```

If `otranscribe` is not found:
- Make sure your virtualenv is active: `source .venv/bin/activate`
- Reinstall: `pip install -e .`

## Set your OpenAI API key

When using the OpenAI engine, set the `OPENAI_API_KEY` environment variable:

```bash
export OPENAI_API_KEY="sk-..."
```

On Windows (PowerShell):

```powershell
$env:OPENAI_API_KEY="sk-..."
```

The local and faster engines (`--engine local` and `--engine faster`) do not require this variable.

## Uninstall

### From PyPI/pipx

```bash
pipx uninstall otranscribe
# or
pip uninstall otranscribe
```

### From source

```bash
# deactivate virtualenv
deactivate

# remove the project directory
rm -rf /path/to/otranscribe
```

---

## Development Setup

### Code style (Black + Ruff) and pre-commit

This repository enforces consistent formatting and linting using:

- **Black** for code formatting
- **Ruff** for linting and import sorting
- **pre-commit** to run checks automatically on commits
- **.editorconfig** to align editor defaults (UTF-8, LF, final newline)
- **.gitattributes** to enforce LF line endings

### Install dev dependencies

```bash
pip install -e ".[dev]"
```

### Set up pre-commit hooks

Install hooks to run checks automatically on `git commit`:

```bash
pre-commit install
```

Optional: Also run checks on `git push`:

```bash
pre-commit install --hook-type pre-push
```

To disable hooks later:

```bash
pre-commit uninstall
```

### Run checks manually

Check all files:

```bash
pre-commit run --all-files
```

Run tools directly:

```bash
black .
ruff check --fix .
```

### Quickstart with Make

```bash
make install
make test

# non-blocking diagnostics (prints what is missing)
make doctor

# strict checks per engine
make doctor-openai
make doctor-local
make doctor-faster
```

### Quickstart without Make

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
pytest
otranscribe doctor
```

### Helper scripts

```bash
./scripts/bootstrap.sh
./scripts/test.sh
```

### Windows

Create and activate venv using PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Then:

```bash
pip install -e ".[dev]"
pytest
```

### Before submitting a PR

Ensure all checks pass:

```bash
pre-commit run --all-files
pytest
```

---

## Notes

- **Formatting**: Let Black/Ruff fix issues automatically; don't manually edit formatting
- **Pre-commit blocks**: If hooks block your commit, run the tools above to fix, then commit again
- **Line endings**: The repository enforces LF (Unix-style) line endings. This is handled automatically by pre-commit
- **EditorConfig**: Most modern editors (VS Code, PyCharm, Sublime Text) respect `.editorconfig` to align settings automatically
