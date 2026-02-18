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

from .ffmpeg_utils import (
    ensure_ffmpeg,
    convert_to_wav_16k_mono,
    split_wav_into_chunks,
)
from .cache import (
    compute_cache_key,
    load_cached_result,
    save_cached_result,
)
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

# Output formats for the final render.  ``txt`` produces plain text
# (current default) and ``md`` produces Markdown.  Additional formats
# could be added in the future.
SUPPORTED_OUT_FORMATS = {"txt", "md"}

# Markdown styles.  See :func:`otranscribe.render.render_final` for
# details.
SUPPORTED_MD_STYLES = {"simple", "meeting"}


def _default_out_path(input_path: Path, render: str, api_format: str) -> Path:
    """Construct a reasonable default output filename.

    If ``render`` is ``final``, produce a ``.txt`` output; otherwise
    choose an extension based on the API format.  ``json`` and the
    diarised formats share ``.json`` to avoid confusion.
    """
    stem = input_path.stem
    if render == "final":
        # Default final outputs to .txt; callers may override for
        # Markdown or other formats in the CLI.
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
            "Transcribe any audio or video file into text.  The CLI converts "
            "input to WAV automatically, invokes the selected speech engine, "
            "and optionally produces a cleaned transcript with timestamps, "
            "speaker labels, caching and Markdown formatting."
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

    # Format of the final transcript when --render final.  txt (plain
    # text) is the default.  md produces Markdown.
    parser.add_argument(
        "--out-format",
        default="txt",
        choices=sorted(SUPPORTED_OUT_FORMATS),
        help=(
            "Output format for the final render: 'txt' for plain text "
            "(default) or 'md' for Markdown.  Only relevant when --render "
            "is 'final'."
        ),
    )

    # Markdown style for md output.  Ignored unless --out-format md.
    parser.add_argument(
        "--md-style",
        default="simple",
        choices=sorted(SUPPORTED_MD_STYLES),
        help=(
            "Markdown style used when --out-format=md.  'simple' produces a "
            "bullet list of utterances; 'meeting' produces heading‑style "
            "meeting notes."
        ),
    )

    # Speaker map file.  JSON mapping from speaker labels (e.g.
    # "Speaker 0") to human friendly names.
    parser.add_argument(
        "--speaker-map",
        dest="speaker_map",
        help=(
            "Path to a JSON file mapping speaker labels (e.g. 'Speaker 0') to "
            "human friendly names.  Only applies to final renders."
        ),
    )

    # Offline chunk size.  When using local or faster engines, split the
    # audio into chunks of this duration (in seconds) before
    # transcription.  A value of 0 disables chunking.
    parser.add_argument(
        "--chunk-seconds",
        type=int,
        default=0,
        help=(
            "For offline engines, split the WAV into chunks of this many "
            "seconds before transcribing.  Helps with long files.  0 disables "
            "chunking (default)."
        ),
    )

    # Caching options.  By default results are cached in a '.otranscribe_cache'
    # directory under the current working directory.  Use --no-cache to
    # disable caching entirely and --cache-dir to override the directory.
    parser.add_argument(
        "--cache-dir",
        dest="cache_dir",
        help=(
            "Directory in which to store cached transcription results.  "
            "Defaults to '.otranscribe_cache' in the current working "
            "directory."
        ),
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable reading and writing the cache.  Forces a fresh transcription.",
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

    # Determine the API response format.  When rendering a final
    # transcript using the OpenAI engine, diarised JSON is required to
    # obtain speaker labels.  Offline engines cannot provide diarisation.
    api_format = args.api_format
    if args.render == "final":
        if engine == "openai":
            api_format = "diarized_json"
        else:
            api_format = "json"

    # Determine the output file path.  For final renders the extension
    # derives from the out_format (txt or md).  For raw renders fall
    # back to the API format.  If the user supplies --out it takes
    # precedence.
    if args.out:
        out_path = Path(args.out).expanduser().resolve()
    else:
        stem = in_path.stem
        if args.render == "final":
            ext = "md" if args.out_format.lower() == "md" else "txt"
            out_path = Path(f"{stem}.{ext}")
        else:
            # raw output uses API format to pick an extension
            if api_format in {"json", "verbose_json", "diarized_json"}:
                ext = "json"
            else:
                ext = api_format
            out_path = Path(f"{stem}.{ext}")

    # Convert the input to WAV.
    wav_path = convert_to_wav_16k_mono(
        in_path,
        temp_dir=Path(args.temp_dir).expanduser().resolve() if args.temp_dir else None,
    )

    # Load speaker map if provided.  Keys in the map are normalised to
    # match the labels produced by _normalise_speaker_label.
    speaker_map: dict[str, str] | None = None
    if args.speaker_map:
        import json
        try:
            with open(Path(args.speaker_map).expanduser(), "r", encoding="utf-8") as f:
                raw_map = json.load(f)
            if isinstance(raw_map, dict):
                from .render import _normalise_speaker_label  # type: ignore
                speaker_map = {}
                for k, v in raw_map.items():
                    speaker_map[_normalise_speaker_label(k)] = str(v)
        except Exception:
            # ignore errors; fall back to None
            speaker_map = None

    # Determine chunking behaviour.  Only applies to offline engines.
    chunk_seconds: int | None = None
    if engine != "openai" and args.chunk_seconds and args.chunk_seconds > 0:
        chunk_seconds = args.chunk_seconds
    else:
        chunk_seconds = None

    # Set up caching.  Caching is enabled unless --no-cache is given.
    use_cache = not args.no_cache
    cache_dir = Path(args.cache_dir).expanduser().resolve() if args.cache_dir else Path(
        ".otranscribe_cache"
    )

    # Compute cache key if caching is enabled.
    api_result: Any | None = None
    if use_cache:
        try:
            key = compute_cache_key(
                wav_path,
                engine=engine,
                model=args.model if engine == "openai" else (args.whisper_model if engine == "local" else args.faster_model),
                language=args.language,
                api_format=api_format,
                chunk_seconds=chunk_seconds,
            )
            cached = load_cached_result(cache_dir, key)
            if cached is not None:
                api_result = cached
        except Exception:
            api_result = None

    # If no cached result, perform transcription (with optional chunking)
    if api_result is None:
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
            else:
                # Offline engines: optional chunking
                def transcribe_single(wpath: Path) -> dict[str, Any]:
                    if engine == "local":
                        try:
                            from .local_stt import transcribe_local  # type: ignore
                        except Exception as imp_exc:
                            raise RuntimeError(
                                "Local engine selected but the 'whisper' package could not be imported."
                                " Install it via 'pip install openai-whisper' or choose a different engine."
                            ) from imp_exc
                        return transcribe_local(
                            wav_path=wpath,
                            language=args.language,
                            model=args.whisper_model,
                        )
                    else:
                        try:
                            from .faster_stt import transcribe_faster  # type: ignore
                        except Exception as imp_exc:
                            raise RuntimeError(
                                "Faster engine selected but the 'faster-whisper' package could not be imported."
                                " Install it via 'pip install faster-whisper' or choose a different engine."
                            ) from imp_exc
                        return transcribe_faster(
                            wav_path=wpath,
                            model_size=args.faster_model,
                            language=args.language,
                            device=args.faster_device,
                            compute_type=args.faster_compute_type,
                        )

                if chunk_seconds:
                    # Transcribe each chunk and accumulate segments with offsets
                    segments: list[dict[str, Any]] = []
                    offset = 0.0
                    for idx, chunk_path in enumerate(split_wav_into_chunks(wav_path, chunk_seconds, None)):
                        result = transcribe_single(chunk_path)
                        segs = result.get("segments", []) if isinstance(result, dict) else []
                        for seg in segs:
                            # copy to avoid mutating original segment
                            seg_copy = dict(seg)
                            try:
                                seg_copy["start"] = float(seg_copy.get("start", 0)) + offset
                                seg_copy["end"] = float(seg_copy.get("end", 0)) + offset
                            except Exception:
                                pass
                            segments.append(seg_copy)
                        # update offset by chunk_seconds rather than actual duration
                        offset += float(chunk_seconds)
                    # Compose a fake API result
                    api_result = {"segments": segments, "text": " ".join(seg.get("text", "") for seg in segments)}
                else:
                    api_result = transcribe_single(wav_path)
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: failed to transcribe file: {exc}", file=sys.stderr)
            if not args.keep_temp:
                try:
                    wav_path.unlink(missing_ok=True)  # type: ignore[attr-defined]
                except Exception:
                    pass
            sys.exit(1)
        # Save to cache
        if use_cache:
            try:
                save_cached_result(cache_dir, key, api_result)  # type: ignore[has-type]
            except Exception:
                pass

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
            # final: cleaned transcript using the requested format and speaker map
            text = render_final(
                api_result,
                every_seconds=args.every,
                speaker_map=speaker_map,
                out_format=args.out_format,
                md_style=args.md_style,
            )
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