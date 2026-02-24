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
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .cache import (
    compute_cache_key,
    load_cached_result,
    save_cached_result,
)
from .ffmpeg_utils import (
    chunk_duration_for_max_size,
    convert_to_wav_16k_mono,
    ensure_ffmpeg,
    split_audio_into_chunks,
    split_wav_into_chunks,
)
from .openai_stt import transcribe_chunked, transcribe_file
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
    parser = argparse.ArgumentParser(
        prog="otranscribe",
        description=(
            "Transcribe any audio or video file. Converts input to WAV automatically "
            "and optionally produces a cleaned transcript with timestamps and speaker labels."
        ),
    )

    subparsers = parser.add_subparsers(dest="command")

    # ---- doctor subcommand
    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Check environment and dependencies",
        description="Verify ffmpeg, Python version, and optional engine dependencies.",
    )
    doctor_parser.add_argument(
        "--engine",
        choices=["openai", "local", "faster"],
        default=None,
        help="Check only the specified engine (default: check all)",
    )

    # ---- transcribe subcommand (default)
    transcribe_parser = subparsers.add_parser(
        "transcribe",
        help="Transcribe audio/video",
        description="Transcribe a file using OpenAI or offline engines.",
    )

    # Move all your existing arguments onto transcribe_parser
    # (Below is identical to your previous parser.add_argument calls,
    #  just renamed to transcribe_parser.add_argument)

    transcribe_parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="Input file (audio or video). Any ffmpeg-supported format.",
    )
    transcribe_parser.add_argument(
        "-o", "--out", default=None, help="Output path (optional)."
    )
    transcribe_parser.add_argument(
        "--model",
        default="gpt-4o-transcribe-diarize",
        help="OpenAI transcription model.",
    )
    transcribe_parser.add_argument(
        "--language", default="pt", help="Language code, e.g., pt, en, es."
    )

    transcribe_parser.add_argument(
        "--api-format",
        default="diarized_json",
        choices=sorted(SUPPORTED_API_FORMATS),
        help="API response_format. diarized_json required for speaker labels.",
    )
    transcribe_parser.add_argument(
        "--render",
        default="final",
        choices=sorted(SUPPORTED_RENDER_FORMATS),
        help="raw = write engine output as-is; final = cleaned transcript with timestamps + speakers.",
    )
    transcribe_parser.add_argument(
        "--every",
        type=int,
        default=30,
        help="Timestamp bucket seconds for final render (default 30).",
    )
    transcribe_parser.add_argument(
        "--chunking",
        default="auto",
        help="OpenAI chunking_strategy (recommended: auto for long audio).",
    )
    transcribe_parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep temp WAV and intermediate artifacts.",
    )
    transcribe_parser.add_argument(
        "--temp-dir", default=None, help="Optional temp directory to use."
    )

    # Engine selection (keep your existing flags; ensure choices match your repo)
    transcribe_parser.add_argument(
        "--engine",
        default="openai",
        choices=["openai", "local", "faster"],
        help="Transcription engine: openai (API), local (openai-whisper), faster (faster-whisper).",
    )

    # Local engine
    transcribe_parser.add_argument(
        "--whisper-model",
        default="base",
        help="Local Whisper model name (tiny/base/small/medium/large).",
    )

    # Faster engine
    transcribe_parser.add_argument(
        "--faster-model", default="small", help="faster-whisper model size/name."
    )
    transcribe_parser.add_argument(
        "--faster-device",
        default="auto",
        help="Device for faster-whisper (auto/cpu/cuda).",
    )
    transcribe_parser.add_argument(
        "--faster-compute-type",
        default="int8",
        help="Compute type (int8/float16/float32).",
    )

    # Cache controls (if present in your repo already; keep them here)
    transcribe_parser.add_argument(
        "--cache-dir", default=".otranscribe_cache", help="Cache directory for results."
    )
    transcribe_parser.add_argument(
        "--no-cache", action="store_true", help="Disable caching."
    )

    # Chunking for offline engines (if present)
    transcribe_parser.add_argument(
        "--chunk-seconds",
        type=int,
        default=0,
        help="Offline chunk duration in seconds (0 disables).",
    )
    transcribe_parser.add_argument(
        "--chunk-overlap-seconds",
        type=int,
        default=0,
        help="Offline chunk overlap in seconds (0 disables).",
    )

    # Output formatting
    transcribe_parser.add_argument(
        "--speaker-map",
        default=None,
        help='Path to JSON speaker map (e.g. {"Speaker 0":"Interviewer"}).',
    )
    transcribe_parser.add_argument(
        "--out-format",
        choices=["txt", "md"],
        default="txt",
        help="Output format for final render.",
    )
    transcribe_parser.add_argument(
        "--md-style",
        choices=["simple", "meeting"],
        default="simple",
        help="Markdown style when --out-format md.",
    )
    transcribe_parser.add_argument(
        "--speaker-id",
        nargs="?",
        type=int,
        const=120,
        default=None,
        metavar="SECONDS",
        help="Transcribe only the first N seconds (default 120) for quick speaker identification.",
    )

    return parser


def _run_sample_workflow(
    api_result: Any,
    args: argparse.Namespace,
    in_path: Path,
    sample_duration: int,
) -> None:
    """Interactive sample workflow for speaker identification.

    Displays speaker excerpts from the sample transcription, prompts the
    user to label each speaker, writes a speaker map JSON file, and
    optionally kicks off the full transcription.
    """
    from .render import _normalise_speaker_label, _clean_text  # type: ignore

    segments = api_result.get("segments", []) if isinstance(api_result, dict) else []
    if not segments:
        print("No speaker segments found in sample.", file=sys.stderr)
        return

    # Collect excerpts per speaker (up to 3 per speaker)
    speaker_excerpts: dict[str, list[str]] = {}
    for seg in segments:
        speaker_raw = seg.get("speaker", "Speaker ?")
        speaker = _normalise_speaker_label(speaker_raw)
        text = _clean_text(seg.get("text", ""))
        if not text:
            continue
        if speaker not in speaker_excerpts:
            speaker_excerpts[speaker] = []
        speaker_excerpts[speaker].append(text)

    if not speaker_excerpts:
        print("No usable speaker text found in sample.", file=sys.stderr)
        return

    # Display excerpts
    print(f"\n=== Sample Transcription (first {sample_duration} seconds) ===\n")
    speakers_sorted = sorted(speaker_excerpts.keys())
    for speaker in speakers_sorted:
        for excerpt in speaker_excerpts[speaker]:
            print(f'  {speaker}: "{excerpt}"')
        print()

    # Prompt for labels
    speaker_map: dict[str, str] = {}
    for speaker in speakers_sorted:
        try:
            label = input(f"Label for {speaker} (Enter to keep as-is): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if label:
            speaker_map[speaker] = label

    # Write speaker map JSON
    map_path = in_path.parent / f"{in_path.stem}_speakers.json"
    full_map = {}
    for speaker in speakers_sorted:
        full_map[speaker] = speaker_map.get(speaker, speaker)
    map_path.write_text(json.dumps(full_map, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSpeaker map saved to: {map_path}")

    # Ask about full transcription
    try:
        answer = input("\nRun full transcription now with this speaker map? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return

    # Build the command for full transcription
    cmd = ["otranscribe"]
    cmd += ["-i", str(in_path)]
    cmd += ["--speaker-map", str(map_path)]
    cmd += ["--language", args.language]
    cmd += ["--engine", args.engine]
    cmd += ["--model", args.model]
    cmd += ["--every", str(args.every)]
    cmd += ["--render", args.render]
    cmd += ["--out-format", args.out_format]
    if args.out:
        cmd += ["-o", args.out]
    if args.keep_temp:
        cmd += ["--keep-temp"]
    if args.no_cache:
        cmd += ["--no-cache"]

    if answer == "y":
        print(f"\nRunning full transcription...\n")
        subprocess.run(cmd)
    else:
        print(f"\nTo run the full transcription later:\n")
        print("  " + " ".join(cmd))
        print()


def main() -> None:
    """Run the command line interface.

    This function parses arguments, checks for the OpenAI API key,
    performs conversion and transcription, and writes the requested
    output.  Errors are written to stderr and result in a nonzero
    exit status.
    """
    parser = build_parser()

    # Backward compatibility:
    # If the user did not specify a subcommand, inject "transcribe" so
    # `otranscribe -i file.m4v` works as expected.
    argv = sys.argv[1:]
    if argv and argv[0] not in {"doctor", "transcribe", "-h", "--help"}:
        argv = ["transcribe"] + argv

    args = parser.parse_args(argv)
    if args.command is None:
        args.command = "transcribe"

    if args.command == "doctor":
        from .doctor import format_report

        ok, lines = format_report(getattr(args, "engine", None))
        for line in lines:
            print(line)
        raise SystemExit(0 if ok else 1)

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

    # Prepare the audio file for transcription.
    # OpenAI accepts compressed formats directly — skip WAV conversion to
    # avoid inflating file size.  Offline engines still need 16 kHz mono WAV.
    sample_duration = getattr(args, "speaker_id", None)
    if sample_duration is not None:
        print(f"NOTE: --speaker-id mode, transcribing first {sample_duration} seconds only.")
    wav_path: Path | None = None
    if engine == "openai":
        upload_path = in_path
    else:
        wav_path = convert_to_wav_16k_mono(
            in_path,
            temp_dir=Path(args.temp_dir).expanduser().resolve() if args.temp_dir else None,
            duration=sample_duration,
        )
        upload_path = wav_path

    # Load speaker map if provided.  Keys in the map are normalised to
    # match the labels produced by _normalise_speaker_label.
    speaker_map: dict[str, str] | None = None
    if args.speaker_map:
        try:
            with open(Path(args.speaker_map).expanduser(), encoding="utf-8") as f:
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

    # OpenAI file-size check: the API has a 25 MB upload limit.
    # Check the actual upload file (original for OpenAI, WAV for offline).
    openai_chunk_paths: list[Path] | None = None
    openai_chunk_duration: int | None = None
    max_openai_bytes = 20_000_000
    if engine == "openai":
        file_size = upload_path.stat().st_size
        if file_size > max_openai_bytes:
            size_mb = file_size / 1_000_000
            openai_chunk_duration = chunk_duration_for_max_size(
                upload_path, max_bytes=max_openai_bytes
            )
            chunk_minutes = openai_chunk_duration / 60
            num_chunks = -(-file_size // max_openai_bytes)  # ceiling division
            print(
                f"File is {size_mb:.0f} MB (OpenAI limit: 25 MB). "
                f"Will split into {num_chunks} chunks of ~{chunk_minutes:.0f} minutes each."
            )
            answer = input("Proceed with chunking? [Y/n] ").strip().lower()
            if answer and answer not in ("y", "yes"):
                print("Aborted.")
                sys.exit(0)
            openai_chunk_paths = split_audio_into_chunks(
                upload_path, openai_chunk_duration
            )

    # Set up caching.  Caching is enabled unless --no-cache is given.
    use_cache = not args.no_cache
    cache_dir = (
        Path(args.cache_dir).expanduser().resolve()
        if args.cache_dir
        else Path(".otranscribe_cache")
    )

    key: str | None = None  # prevent UnboundLocalError

    # Compute cache key if caching is enabled.
    # For OpenAI chunking, include the chunk duration so that a chunked
    # transcription is cached separately from a non-chunked one.
    effective_chunk_seconds = openai_chunk_duration if openai_chunk_paths else chunk_seconds
    api_result: Any | None = None
    if use_cache:
        try:
            key = compute_cache_key(
                upload_path,
                engine=engine,
                model=(
                    args.model
                    if engine == "openai"
                    else (
                        args.whisper_model if engine == "local" else args.faster_model
                    )
                ),
                language=args.language,
                api_format=api_format,
                chunk_seconds=effective_chunk_seconds,
            )
            cached = load_cached_result(cache_dir, key)
            if cached is not None:
                api_result = cached
        except Exception:
            api_result = None
            key = None

    # If no cached result, perform transcription (with optional chunking)
    if api_result is None:
        try:
            if engine == "openai":
                if openai_chunk_paths:
                    api_result = transcribe_chunked(
                        chunk_paths=openai_chunk_paths,
                        api_key=api_key,  # type: ignore[arg-type]
                        model=args.model,
                        language=args.language,
                        response_format=api_format,
                        chunking_strategy=args.chunking,
                    )
                else:
                    api_result = transcribe_file(
                        wav_path=upload_path,
                        api_key=api_key,  # type: ignore[arg-type]
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
                    overlap = (
                        args.chunk_overlap_seconds
                        if args.chunk_overlap_seconds and args.chunk_overlap_seconds > 0
                        else 0
                    )
                    for _idx, chunk_path in enumerate(
                        split_wav_into_chunks(wav_path, chunk_seconds, overlap)
                    ):
                        result = transcribe_single(chunk_path)
                        segs = (
                            result.get("segments", [])
                            if isinstance(result, dict)
                            else []
                        )
                        for seg in segs:
                            # copy to avoid mutating original segment
                            seg_copy = dict(seg)
                            try:
                                seg_copy["start"] = (
                                    float(seg_copy.get("start", 0)) + offset
                                )
                                seg_copy["end"] = float(seg_copy.get("end", 0)) + offset
                            except Exception:
                                pass
                            segments.append(seg_copy)
                        # update offset by chunk_seconds rather than actual duration
                        offset += float(chunk_seconds)
                    # Compose a fake API result
                    api_result = {
                        "segments": segments,
                        "text": " ".join(seg.get("text", "") for seg in segments),
                    }
                else:
                    api_result = transcribe_single(wav_path)
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: failed to transcribe file: {exc}", file=sys.stderr)
            if not args.keep_temp and wav_path is not None:
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

    # Clean up temp WAV when done.
    def _cleanup_temp() -> None:
        if not args.keep_temp and wav_path is not None:
            try:
                wav_path.unlink(missing_ok=True)  # type: ignore[attr-defined]
            except Exception:
                pass

    # Sample mode: interactive speaker identification workflow.
    if sample_duration is not None:
        try:
            _run_sample_workflow(api_result, args, in_path, sample_duration)
        finally:
            _cleanup_temp()
        sys.exit(0)

    # Write the output.
    try:
        if args.render == "raw":
            # Write raw output depending on type.
            if isinstance(api_result, (dict, list)):
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
        _cleanup_temp()
        # Clean up OpenAI chunk files if any were created.
        if not args.keep_temp and openai_chunk_paths:
            for cp in openai_chunk_paths:
                try:
                    cp.unlink(missing_ok=True)  # type: ignore[attr-defined]
                except Exception:
                    pass

    sys.exit(0)


if __name__ == "__main__":  # pragma: no cover
    main()
