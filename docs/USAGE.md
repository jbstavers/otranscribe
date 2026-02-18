# Usage

The `otranscribe` command accepts an input file and optional flags to control the model, language, engine, response format and rendering. The default behaviour uses the OpenAI engine with diarisation, renders a clean transcript and writes it to `<input>.txt`.

## Basic usage

```bash
otranscribe -i input.m4v
otranscribe -i interview.mp3
otranscribe -i meeting.wav
```

Output is written to `<input>.txt` by default.

## Choosing an engine

### OpenAI (default, requires API key)

High-quality diarised transcripts with speaker labels. Requires `OPENAI_API_KEY` environment variable.

```bash
otranscribe -i interview.mp3
otranscribe -i interview.mp3 --engine openai
```

### Local Whisper (offline, requires `openai-whisper`)

Runs on your machine. No API calls, no costs. No speaker labels; assigns all words to `Speaker 0`.

```bash
# default model (base)
otranscribe -i interview.mp3 --engine local

# use larger/smaller models
otranscribe -i interview.mp3 --engine local --whisper-model tiny
otranscribe -i interview.mp3 --engine local --whisper-model small
otranscribe -i interview.mp3 --engine local --whisper-model medium
otranscribe -i interview.mp3 --engine local --whisper-model large
```

### faster-whisper (offline, faster, requires `faster-whisper`)

CTranslate2-based reimplementation. Up to 4x faster with lower memory usage. Supports GPU acceleration and quantisation. No speaker labels.

```bash
# default settings
otranscribe -i interview.mp3 --engine faster

# with model selection and device/compute options
otranscribe -i interview.mp3 --engine faster --faster-model small
otranscribe -i interview.mp3 --engine faster --faster-model medium --faster-device auto --faster-compute-type int8

# GPU acceleration (CUDA)
otranscribe -i interview.mp3 --engine faster --faster-device cuda --faster-compute-type float16
```

## Output formats

### Clean transcript (default)

Removes filler words, collapses whitespace, inserts timestamps and speaker labels:

```bash
otranscribe -i meeting.wav
# writes: meeting.wav.txt
```

### Custom output file

```bash
otranscribe -i interview.mp3 -o transcript.txt
otranscribe -i interview.mp3 -o transcript.md
```

### Raw engine output

Write the exact response from the transcription engine:

```bash
# JSON with diarisation info
otranscribe -i meeting.wav --render raw --api-format diarized_json -o meeting.json

# SRT subtitles
otranscribe -i video.mp4 --render raw --api-format srt -o video.srt

# VTT subtitles
otranscribe -i video.mp4 --render raw --api-format vtt -o video.vtt

# Plain text
otranscribe -i video.mp4 --render raw --api-format text -o video.txt
```

## Customization

### Timestamp bucket (clean transcript only)

Insert timestamps every N seconds:

```bash
# default: every 5 seconds
otranscribe -i call.m4a

# every 15 seconds
otranscribe -i call.m4a --every 15

# every 30 seconds
otranscribe -i call.m4a --every 30
```

Timestamps also insert automatically on speaker change.

### Language

Specify language for better accuracy (OpenAI and local Whisper):

```bash
# English
otranscribe -i interview.mp3 --language en

# Portuguese
otranscribe -i interview.mp3 --language pt

# French
otranscribe -i interview.mp3 --language fr
```

Omit `--language` to auto-detect.

## Real-world examples

### Interview transcript with timestamps every 10 seconds

```bash
otranscribe -i interview.wav --every 10 -o interview.txt
```

### Meeting notes (offline, no API costs)

```bash
otranscribe -i meeting.m4a --engine local --whisper-model small -o meeting-notes.txt
```

### Fast transcription with GPU

```bash
otranscribe -i long-video.mp4 --engine faster --faster-device cuda --faster-compute-type float16
```

### Export to subtitles (SRT)

```bash
otranscribe -i video.mp4 --render raw --api-format srt -o video.srt
```

### Portuguese speech with diarisation

```bash
otranscribe -i podcast.mp3 --language pt --render raw --api-format diarized_json -o podcast.json
```

### Multiple files

```bash
for file in *.mp3; do
  otranscribe -i "$file"
done
```

## Getting help

```bash
otranscribe --help
```

Shows all available flags and options.
