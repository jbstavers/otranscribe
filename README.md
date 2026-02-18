# otranscribe

`otranscribe` is a tiny command line interface for turning any audio or
video into text. It primarily wraps the
[OpenAI speech-to-text API](https://developers.openai.com/api/reference/resources/audio/subresources/transcriptions),
but also includes two **offline** backends so you can avoid network
calls and API costs entirely. The CLI handles all of the boilerplate:
it extracts audio from arbitrary input, normalises it, runs the
transcription on your chosen engine and optionally renders a cleaned
transcript with timestamps and speaker labels.

## Features

- **Any input format** – as long as `ffmpeg` can read it, it can be
  transcribed.
- **Diarisation support** – by default it uses the
  `gpt-4o-transcribe-diarize` model and requests `diarized_json`
  output so that speakers are labelled. When you don't need
  diarisation or want to avoid API costs, you can select the local
  Whisper engine.
- **Clean rendering** – remove filler words, collapse whitespace and
  insert timestamps every N seconds and on speaker change.
- **Raw output** – choose `--render raw` to write the exact response
  from the engine (JSON, text, SRT, VTT, etc.).
- **Choice of engine** – use the OpenAI API (`--engine openai`) for
  high-quality diarised transcripts or choose one of the offline
  backends when you want to work without an internet connection:

  * **Local Whisper** (`--engine local`) – runs the reference
    [openai-whisper](https://github.com/openai/whisper) model on your
    machine. This backend produces accurate transcriptions but can
    be relatively slow on CPU and does not assign speaker labels.

  * **faster-whisper** (`--engine faster`) – uses the
    [faster-whisper](https://github.com/guillaumekln/faster-whisper)
    reimplementation based on CTranslate2. It is up to four times faster
    than the original open source Whisper implementation and uses less
    memory, with optional quantisation and GPU acceleration for even
    greater speed. Since diarisation is not available locally, the
    engine assigns all words to a single speaker (`Speaker 0`).
- **Minimal dependencies** – uses `requests` instead of the heavy
  `openai` client when talking to the API. The local engine only
  imports Whisper if you choose `--engine local`.
  The faster engine pulls in the `faster-whisper` package only when
  selected.

## Installation

Before you can run `otranscribe` you need a few prerequisites:

- **Python 3.9+** – the code is tested with 3.9 and newer.
- **ffmpeg** – used to extract audio from videos and normalise input. You must install
  this separately and ensure the `ffmpeg` binary is on your `PATH`. See OS-specific
  notes below.
- **Requests** – installed automatically via the package dependencies.
- **OpenAI API key** – only required when using the OpenAI engine.
- **openai-whisper** – required only if you plan to use the local engine.
- **faster-whisper** – required only if you plan to use the faster engine. This
  backend depends on [CTranslate2](https://github.com/OpenNMT/CTranslate2) and can
  leverage a GPU if available. Follow the upstream installation instructions on
  macOS, Linux or Windows. On Linux, for example, you can install via
  `pip install faster-whisper` and optionally `pip install ctranslate2` with
  CUDA support.

### Installing ffmpeg

`otranscribe` relies on the external `ffmpeg` program. Typical installation
methods by operating system:

- **macOS**: install via [Homebrew](https://brew.sh/) with `brew install ffmpeg`.
- **Ubuntu/Debian**: use your package manager: `sudo apt-get install ffmpeg`.
- **Windows**: you can install via [Chocolatey](https://chocolatey.org/) with `choco install ffmpeg`, or
  download the official static build from [ffmpeg.org](https://ffmpeg.org/) and add the `bin` directory
  to your `PATH` environment variable.

### Installing the package

You can install `otranscribe` either from a published release (PyPI) or
directly from a clone.

#### Option A: install from PyPI (when published)

Use `pipx` (recommended) or `pip` to install the CLI after the prerequisites are met.
`otranscribe` exposes extras for its optional backends so you can pull in
only the dependencies you need:

```bash
# install globally using pipx (core only: uses OpenAI API)
pipx install otranscribe

# or install into the current environment via pip
pip install otranscribe

# enable the local Whisper engine
pip install otranscribe[local]

# enable the faster-whisper engine
pip install otranscribe[faster]

# install both offline engines together
pip install otranscribe[local,faster]
```

#### Option B: install locally from a clone (recommended for development)

```bash
git clone <repo-url>
cd otranscribe
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip

# install the CLI in editable mode
pip install -e .
```

Verify the install:

```bash
which otranscribe
otranscribe --help
python -c "import otranscribe; print(otranscribe.__file__)"
```

If you see `zsh: command not found: otranscribe`, you probably forgot to
activate the virtualenv:

```bash
source .venv/bin/activate
```

##### Optional extras from a clone

```bash
# local Whisper engine
pip install -e ".[local]"

# faster-whisper engine
pip install -e ".[faster]"

# dev dependencies (pytest, etc.)
pip install -e ".[dev]"
```

#### Alternative: requirements files (clone-only)

If you prefer installing dependencies via requirements files:

```bash
git clone <repo-url>
cd otranscribe
python3 -m venv .venv
source .venv/bin/activate

# core dependencies (API only)
pip install -r requirements.txt

# optional: install openai-whisper for the local engine
pip install -r requirements-local.txt

# optional: install faster-whisper for the faster engine
pip install -r requirements-faster.txt

# install the package itself
pip install -e .
```

### Setting your API key

When using the OpenAI engine you must set the `OPENAI_API_KEY` environment
variable so the CLI can authenticate with the API:

```bash
export OPENAI_API_KEY="sk-..."
```

The local and faster engines (`--engine local` and `--engine faster`) do
not use the API and therefore do not require this variable. When
working offline you can omit `OPENAI_API_KEY` entirely.

## Usage

The `otranscribe` command accepts an input file and optional flags to
control the model, language, engine, response format and rendering. The
default behaviour uses the OpenAI engine with diarisation, renders a
clean transcript and writes it to `<input>.txt`.

```bash
otranscribe -i input.m4v

# use the local Whisper engine (requires `openai-whisper`)
otranscribe -i interview.mp3 --engine local --whisper-model medium

# use the faster-whisper engine (requires `faster-whisper`)
otranscribe -i interview.mp3 --engine faster --faster-model small --faster-device auto --faster-compute-type int8

# custom output name
otranscribe -i interview.mp3 -o interview.md

# raw diarised JSON for post-processing
otranscribe -i meeting.wav --render raw --api-format diarized_json -o meeting.json

# output SRT subtitles (no speaker labels)
otranscribe -i video.mp4 --render raw --api-format srt -o video.srt

# change the timestamp bucket to 15 seconds in the final render
otranscribe -i call.m4a --every 15
```

## Development

This repository includes a minimal test suite using pytest. After
cloning run:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
pytest
```

## Troubleshooting

Run:

```bash
otranscribe doctor
otranscribe doctor --engine openai
otranscribe doctor --engine local
otranscribe doctor --engine faster
```

Contributions are welcome.  Please open issues or pull requests on the
project repository.

## License

Released under the terms of the MIT license. See [LICENSE](LICENSE)
for details.
