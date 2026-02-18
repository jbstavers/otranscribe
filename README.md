# otranscribe

`otranscribe` is a tiny command line interface that wraps the
[OpenAI speech‑to‑text API](https://developers.openai.com/api/reference/resources/audio/subresources/transcriptions)
to transcribe arbitrary audio or video files.  It handles the boilerplate
so you can run a single command to extract audio, transcribe it and
optionally render a cleaned transcript with timestamps and speaker
labels.

## Features

- **Any input format** – as long as `ffmpeg` can read it, it can be
  transcribed.
- **Diarisation support** – by default it uses the
  `gpt-4o-transcribe-diarize` model and requests `diarized_json`
  output so that speakers are labelled.
- **Clean rendering** – remove filler words, collapse whitespace and
  insert timestamps every N seconds and on speaker change.
- **Raw API output** – choose `--render raw` to write the exact API
  response (JSON, text, SRT, VTT, etc.).
- **Minimal dependencies** – uses `requests` instead of the heavy
  `openai` client.

## Installation

You need Python 3.9+ and `ffmpeg` installed.  Install the package via
`pipx` (recommended) or `pip`:

```bash
# make sure ffmpeg is installed first
# macOS: brew install ffmpeg
# Ubuntu/Debian: sudo apt‑get install ffmpeg

# install globally using pipx
pipx install otranscribe

# or install into the current environment via pip
pip install otranscribe
```

Set your OpenAI API key in the environment before running.  For
example, in bash:

```bash
export OPENAI_API_KEY="sk‑..."
```

## Usage

The `otranscribe` command accepts an input file and optional flags to
control the model, language, API response format and rendering.  The
default behaviour transcribes the file using diarisation, renders a
clean transcript and writes it to `<input>.txt`.

```bash
otranscribe -i input.m4v

# custom output name
otranscribe -i interview.mp3 -o interview.md

# raw diarised JSON for post‑processing
otranscribe -i meeting.wav --render raw --api-format diarized_json -o meeting.json

# output SRT subtitles (no speaker labels)
otranscribe -i video.mp4 --render raw --api-format srt -o video.srt

# change the timestamp bucket to 15 seconds in the final render
otranscribe -i call.m4a --every 15
```

## Development

This repository includes a minimal test suite using pytest.  After
cloning run:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
pytest
```

Contributions are welcome.  Please open issues or pull requests on the
project repository.

## License

Released under the terms of the MIT license.  See [LICENSE](LICENSE)
for details.