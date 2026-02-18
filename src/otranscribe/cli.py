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

    # Allow selection of the transcription engine.  ``openai`` uses the
    # OpenAI API (default).  ``local`` uses a locally installed Whisper
    # model.  The local engine requires the ``whisper`` Python package and
    # does not provide diarisation.
    parser.add_argument(
        "--engine",
        default="openai",
        choices=["openai", "local", "faster"],
        help=(
            "Transcription engine to use.  'openai' (default) calls the OpenAI"
            " speech‑to‑text API.  'local' runs a local Whisper model (requires"
            " the 'whisper' Python package).  'faster' uses the faster‑whisper"
            " backend (requires the 'faster‑whisper' package) for higher speed"
            " on CPU or GPU."
        ),
    )

    # Whisper model size for the local engine.  Ignored when using the
    # OpenAI engine.  Valid values mirror the Whisper model names (tiny,
    # base, small, medium, large).  Defaults to 'medium'.
    parser.add_argument(
        "--whisper-model",
        default="medium",
        help=(
            "Model size for the local Whisper engine (e.g., tiny, base, small,"
            " medium, large).  Ignored when using --engine openai."
        ),
    )

    # Faster‑whisper options.  Ignored unless --engine faster.  The model
    # defines the quality/speed trade off (e.g. tiny, base, small, medium,
    # large, large-v2, etc.).  Device can be 'cpu', 'cuda' or 'auto'.
    parser.add_argument(
        "--faster-model",
        default="base",
        help=(
            "Model size for the faster‑whisper engine (e.g., tiny, base, small,"
            " medium, large).  Ignored unless --engine faster."
        ),
    )
    parser.add_argument(
        "--faster-device",
        default="cpu",
        help=(
            "Device for faster‑whisper (cpu, cuda or auto).  Ignored unless"
            " --engine faster."
        ),
    )
    parser.add_argument(
        "--faster-compute-type",
        default="int8",
        help=(
            "Compute type for faster‑whisper (e.g. fp16, int8, float16)."
            " Ignored unless --engine faster."
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

    # Read the transcription engine and API key.  The API key is only
    # mandatory when using the OpenAI engine.  When running locally
    # (--engine local) or with faster‑whisper (--engine faster) the key
    # may be omitted.
    engine = args.engine
    api_key = os.getenv("OPENAI_API_KEY")
    if engine == "openai" and not api_key:
        print(
            "ERROR: environment variable OPENAI_API_KEY is not set."
            " Set this when using --engine openai.",
            file=sys.stderr,
        )
        sys.exit(2)

    in_path = Path(args.input).expanduser().resolve()
    if not in_path.exists():
        print(f"ERROR: input file not found: {in_path}", file=sys.stderr)
        sys.exit(2)

    # Ensure ffmpeg is available before starting any work.
    ensure_ffmpeg()

    # Determine the API format.  When rendering 'final' and using the
    # OpenAI engine, diarised JSON is required to obtain speaker labels.
    # The local and faster engines cannot perform diarisation; in those
    # cases fall back to basic JSON.
    api_format = args.api_format
    if args.render == "final":
        if engine == "openai":
            api_format = "diarized_json"
        else:
            api_format = "json"

    # Determine the output path.
    if args.out:
        out_path = Path(args.out).expanduser().resolve()
    else:
        out_path = _default_out_path(in_path, args.render, api_format)

    # Convert the input to WAV.
    wav_path = convert_to_wav_16k_mono(
        in_path,
        temp_dir=Path(args.temp_dir).expanduser().resolve() if args.temp_dir else None,
    )

    # Transcribe the audio via the selected engine.
    try:
        if engine == "openai":
            api_result = transcribe_file(
                wav_path=wav_path,
                api_key=api_key,
                model=args.model,
                language=args.language,
                response_format=api_format,
                chunking_strategy=args.chunking,
            )
        elif engine == "local":
            # Local whisper engine.  Import lazily to avoid pulling in the
            # dependency unless needed.  If whisper is not installed, the
            # import will fail and the user will see an informative error.
            try:
                from .local_stt import transcribe_local  # type: ignore
            except Exception as imp_exc:
                raise RuntimeError(
                    "Local engine selected but the 'whisper' package could not be imported."
                    " Install it via 'pip install openai-whisper' or choose a different engine."
                ) from imp_exc
            api_result = transcribe_local(
                wav_path=wav_path,
                language=args.language,
                model=args.whisper_model,
            )
        else:
            # Faster‑whisper engine.  Import lazily to avoid pulling in the
            # dependency unless needed.  If faster_whisper is not installed,
            # the import will fail and the user will see an informative error.
            try:
                from .faster_stt import transcribe_faster  # type: ignore
            except Exception as imp_exc:
                raise RuntimeError(
                    "Faster engine selected but the 'faster-whisper' package could not be imported."
                    " Install it via 'pip install faster-whisper' or choose a different engine."
                ) from imp_exc
            api_result = transcribe_faster(
                wav_path=wav_path,
                model_size=args.faster_model,
                language=args.language,
                device=args.faster_device,
                compute_type=args.faster_compute_type,
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