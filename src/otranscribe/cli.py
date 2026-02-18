"""
CLI entry point for the otranscribe package.

The ``otranscribe`` command wraps several steps into a single interface:

* Convert an arbitrary audio or video file into a 16 kHz mono WAV
  using ``ffmpeg``.  Any container format supported by ffmpeg can be
  used as input.  The resulting WAV is stored in a temporary
  directory unless ``--keep-temp`` is set.
* Call the OpenAI Speech‑to‑Text API to transcribe the audio.  By
  default the CLI uses the ``gpt-4o-transcribe-diarize`` model and
  requests diarised JSON so that speaker labels and timestamps are
  available.
* Optionally render the diarised JSON into a cleaned transcript with
  timestamps every N seconds and on speaker changes.  The cleaning
  removes common filler words and extraneous whitespace but does not
  invent content.

Use the ``--help`` flag to see all available options.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .ffmpeg_utils import ensure_ffmpeg, convert_to_wav_16k_mono
from .openai_stt import transcribe_file
from .render import render_final

# Supported response formats documented by OpenAI.  See
# https://developers.openai.com/api/reference/resources/audio/subresources/transcriptions#create-a-transcription
SUPPORTED_API_FORMATS = {
    "json",
    "text",
    "srt",
    "verbose_json",
    "vtt",
    "diarized_json",
}

# Render modes: ``raw`` writes the API response directly (for
# ``json``, ``verbose_json`` and ``diarized_json`` it writes JSON; for
# ``text``, ``srt`` and ``vtt`` it writes the string).  ``final``
# produces a cleaned transcript with timestamps and speaker labels.
SUPPORTED_RENDER_FORMATS = {"raw", "final"}


def _default_out_path(input_path: Path, render: str, api_format: str) -> Path:
    """Construct a reasonable default output filename.

    If ``render`` is ``final``, produce a ``.txt`` output; otherwise
    choose an extension based on the API format.  ``json`` and the
    diarised formats share ``.json`` to avoid confusion.
    """
    stem = input_path.stem
    if render == "final":
        return Path(f"{stem}.txt")
    # raw output
    if api_format in {"json", "verbose_json", "diarized_json"}:
        ext = "json"
    else:
        ext = api_format
    return Path(f"{stem}.{ext}")


def build_parser() -> argparse.ArgumentParser:
    """Create and return an argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog="otranscribe",
        description=(
            "Transcribe any audio or video file via OpenAI STT.  Converts"
            " input to WAV automatically and optionally produces a cleaned"
            " transcript with timestamps and speaker labels."
        ),
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="Input file (audio or video). Any format supported by ffmpeg.",
    )
    parser.add_argument(
        "-o",
        "--out",
        help="Output file path (optional). Defaults depend on render/API format.",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-transcribe-diarize",
        help="OpenAI transcription model. The default enables diarisation.",
    )
    parser.add_argument(
        "--language",
        default="pt",
        help=(
            "Language code for the input (e.g., pt, en, es).  See OpenAI"
            " documentation for supported languages."
        ),
    )
    parser.add_argument(
        "--api-format",
        default="diarized_json",
        choices=sorted(SUPPORTED_API_FORMATS),
        help=(
            "API response_format.  'diarized_json' is required for speaker"
            " labels.  Other options include json, text, srt, verbose_json,"
            " vtt."
        ),
    )
    parser.add_argument(
        "--render",
        default="final",
        choices=sorted(SUPPORTED_RENDER_FORMATS),
        help=(
            "Render mode: 'final' produces a cleaned transcript with"
            " timestamps and speakers; 'raw' writes the API response as"
            " returned."
        ),
    )
    parser.add_argument(
        "--every",
        type=int,
        default=30,
        help="Timestamp bucket size in seconds for final render (default 30).",
    )
    parser.add_argument(
        "--chunking",
        default="auto",
        help=(
            "chunking_strategy passed to the API.  'auto' is recommended"
            " for long audio files and for diarisation."
        ),
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep temporary WAV and API response files for debugging.",
    )
    parser.add_argument(
        "--temp-dir",
        help=(
            "Optional directory to store temporary files.  If not provided"
            " a new temporary directory will be used."
        ),
    )
    return parser


def main() -> None:
    """Run the command line interface.

    This function parses arguments, checks for the OpenAI API key,
    performs conversion and transcription, and writes the requested
    output.  Errors are written to stderr and result in a nonzero
    exit status.
    """
    parser = build_parser()
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print(
            "ERROR: environment variable OPENAI_API_KEY is not set.",
            file=sys.stderr,
        )
        sys.exit(2)

    in_path = Path(args.input).expanduser().resolve()
    if not in_path.exists():
        print(f"ERROR: input file not found: {in_path}", file=sys.stderr)
        sys.exit(2)

    # Ensure ffmpeg is available before starting any work.
    ensure_ffmpeg()

    # Determine the API format: if final render, force diarised JSON.
    api_format = args.api_format
    if args.render == "final":
        api_format = "diarized_json"

    # Determine the output path.
    if args.out:
        out_path = Path(args.out).expanduser().resolve()
    else:
        out_path = _default_out_path(in_path, args.render, api_format)

    # Convert the input to WAV.
    wav_path = convert_to_wav_16k_mono(in_path, temp_dir=Path(args.temp_dir).expanduser().resolve() if args.temp_dir else None)

    # Call the OpenAI API.
    try:
        api_result = transcribe_file(
            wav_path=wav_path,
            api_key=api_key,
            model=args.model,
            language=args.language,
            response_format=api_format,
            chunking_strategy=args.chunking,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: failed to transcribe file: {exc}", file=sys.stderr)
        if not args.keep_temp:
            try:
                wav_path.unlink(missing_ok=True)  # type: ignore[attr-defined]
            except Exception:
                pass
        sys.exit(1)

    # Write the output.
    try:
        if args.render == "raw":
            # Write raw output depending on type.
            if isinstance(api_result, (dict, list)):
                import json
                out_path.write_text(
                    json.dumps(api_result, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            else:
                out_path.write_text(str(api_result), encoding="utf-8")
        else:
            # final: cleaned transcript
            text = render_final(api_result, every_seconds=args.every)
            out_path.write_text(text, encoding="utf-8")
        print(f"OK -> {out_path}")
    finally:
        if not args.keep_temp:
            # Remove the temporary WAV if we created it in a temp dir.
            try:
                wav_path.unlink(missing_ok=True)  # type: ignore[attr-defined]
            except Exception:
                pass

    sys.exit(0)


if __name__ == "__main__":  # pragma: no cover
    main()