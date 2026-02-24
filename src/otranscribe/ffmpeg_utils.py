"""
Utilities for interacting with the ``ffmpeg`` command line tool.

Two helpers are exposed:

* :func:`ensure_ffmpeg` checks that ``ffmpeg`` is available on the
  system.  If it is not found on the ``PATH`` an informative
  ``SystemExit`` is raised describing how to install it for common
  platforms.  The CLI invokes this early to fail fast.
* :func:`convert_to_wav_16k_mono` converts an arbitrary input file
  (audio or video) into a mono PCM WAV file at 16 kHz.  It writes the
  output into a provided temporary directory and returns the new
  ``Path``.  Conversion is performed using a subprocess call to
  ``ffmpeg`` and will raise ``CalledProcessError`` on failure.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Iterable
from pathlib import Path


def ensure_ffmpeg() -> None:
    """Verify that ``ffmpeg`` is available on the system.

    Checks the current ``PATH`` for an ``ffmpeg`` binary.  If it is not
    found, the function raises ``SystemExit`` with an error message and
    installation instructions.  The CLI catches this and exits with a
    useful message.
    """
    if shutil.which("ffmpeg") is None:
        raise SystemExit(
            "ERROR: ffmpeg not found. Please install it first.\n"
            "macOS: brew install ffmpeg\n"
            "Ubuntu/Debian: sudo apt-get install ffmpeg\n"
            "Windows: choco install ffmpeg or winget install ffmpeg"
        )


def convert_to_wav_16k_mono(
    input_path: Path,
    *,
    temp_dir: Path | None = None,
    duration: int | None = None,
) -> Path:
    """Convert ``input_path`` into a 16 kHz mono PCM WAV file.

    ``ffmpeg`` handles a huge range of input formats.  This helper
    constructs a command that reads the input, disables video, forces
    a single audio channel and 16 kHz sample rate, and writes out a
    WAV file.  The output file is placed in ``temp_dir`` if provided
    or otherwise in a newly created temporary directory.  The caller
    is responsible for cleaning up the file (and directory) when
    finished.

    Parameters
    ----------
    input_path: Path
        The file to convert.  Must exist.
    temp_dir: Path | None, default None
        Optional directory to write the temporary WAV file.  If
        ``None`` a new temporary directory will be created with
        ``tempfile.mkdtemp``.
    duration: int | None, default None
        When set, only convert the first *duration* seconds of
        audio.  Passed to ``ffmpeg`` as ``-t <seconds>``.

    Returns
    -------
    Path
        Path to the generated WAV file.
    """
    workdir = temp_dir or Path(tempfile.mkdtemp(prefix="otranscribe-"))
    workdir.mkdir(parents=True, exist_ok=True)
    wav_path = workdir / "audio.wav"

    # Build the ffmpeg command.  We suppress output except for errors
    # (``-loglevel error``) and overwrite the output if it exists
    # (``-y``).  The audio codec ``pcm_s16le`` produces a raw PCM WAV
    # file which is accepted by OpenAI STT.
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
    ]
    if duration is not None:
        cmd.extend(["-t", str(duration)])
    cmd.append(str(wav_path))

    subprocess.run(cmd, check=True)
    return wav_path


def wav_duration_seconds(wav_path: Path) -> float:
    """Return the duration of a WAV file in seconds.

    This helper opens the WAV using the built‑in :mod:`wave` module and
    calculates the duration as ``frames / frame_rate``.  It will raise
    if the file cannot be read.
    """
    import contextlib
    import wave

    with contextlib.closing(wave.open(str(wav_path), "rb")) as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        return frames / float(rate)


def wav_bytes_per_second(wav_path: Path) -> int:
    """Return the byte rate of a WAV file (channels * sample_width * frame_rate)."""
    import contextlib
    import wave

    with contextlib.closing(wave.open(str(wav_path), "rb")) as wf:
        return wf.getnchannels() * wf.getsampwidth() * wf.getframerate()


def audio_duration_seconds(path: Path) -> float:
    """Return the duration of any audio/video file in seconds via ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-show_entries",
        "format=duration",
        "-of",
        "csv=p=0",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def trim_audio(
    input_path: Path,
    duration: int,
    temp_dir: Path | None = None,
) -> Path:
    """Extract the first ``duration`` seconds of audio, keeping the original format.

    Returns the path to the trimmed file.
    """
    workdir = temp_dir or Path(tempfile.mkdtemp(prefix="otranscribe-trim-"))
    workdir.mkdir(parents=True, exist_ok=True)
    ext = input_path.suffix
    out_path = workdir / f"trimmed{ext}"
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_path),
        "-t",
        str(duration),
        "-c",
        "copy",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    return out_path


def split_audio_into_chunks(
    input_path: Path,
    chunk_seconds: int,
    temp_dir: Path | None = None,
) -> list[Path]:
    """Split any audio file into chunks using ffmpeg segment muxer (no re-encoding).

    The output extension matches the input so the format is preserved.
    Returns a list of chunk file paths in order.
    """
    ext = input_path.suffix  # e.g. ".m4a"
    workdir = temp_dir or Path(tempfile.mkdtemp(prefix="otranscribe-chunks-"))
    workdir.mkdir(parents=True, exist_ok=True)
    pattern = str(workdir / f"chunk_%04d{ext}")

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_path),
        "-f",
        "segment",
        "-segment_time",
        str(chunk_seconds),
        "-c",
        "copy",
        "-reset_timestamps",
        "1",
        pattern,
    ]
    subprocess.run(cmd, check=True)

    # Collect output files in sorted order
    chunks = sorted(workdir.glob(f"chunk_*{ext}"))
    if not chunks:
        raise RuntimeError(f"ffmpeg segment produced no output files in {workdir}")
    return chunks


def chunk_duration_for_max_size(
    audio_path: Path, max_bytes: int = 20_000_000
) -> int:
    """Calculate chunk duration in seconds that fits within ``max_bytes``.

    Works with any audio format by computing bytes/sec from the file's
    actual size and duration.  Falls back to WAV byte-rate calculation
    if the file is a WAV.
    """
    file_size = audio_path.stat().st_size
    duration = audio_duration_seconds(audio_path)
    if duration <= 0:
        raise ValueError(f"Audio file has zero or negative duration: {audio_path}")
    bytes_per_sec = file_size / duration
    chunk_dur = int(max_bytes / bytes_per_sec)
    if chunk_dur < 1:
        raise ValueError(
            f"Byte rate ({bytes_per_sec:.0f} B/s) is too high to fit even 1 second "
            f"in {max_bytes} bytes"
        )
    # OpenAI also enforces a max duration of 1400s per request.
    # Cap at 1300s to leave margin.
    max_duration = 1300
    if chunk_dur > max_duration:
        chunk_dur = max_duration
    return chunk_dur


def split_wav_into_chunks(
    wav_path: Path,
    chunk_seconds: int,
    temp_dir: Path | None = None,
) -> Iterable[Path]:
    """Yield paths to chunked WAV files of approximately ``chunk_seconds`` seconds.

    This helper reads the input WAV and writes successive chunks to a
    temporary directory.  Each chunk preserves the original sample rate,
    channel count and sample width.  The final chunk may be shorter
    than ``chunk_seconds`` if the audio does not divide evenly.  Chunks
    are named ``chunk_XXXX.wav`` where XXXX is a zero‑padded index.

    Parameters
    ----------
    wav_path: Path
        Path to the input WAV file.
    chunk_seconds: int
        Desired chunk duration in seconds.  Must be positive.
    temp_dir: Path | None, optional
        Directory to write chunk files into.  If omitted, a new
        temporary directory is created.  Callers may remove the
        directory when done.

    Yields
    ------
    Path
        Paths to the chunk files in order.
    """
    import contextlib
    import tempfile
    import wave

    if chunk_seconds <= 0:
        raise ValueError("chunk_seconds must be a positive integer")
    # Determine output directory
    if temp_dir is not None:
        workdir = Path(temp_dir).expanduser().resolve()
    else:
        workdir = Path(tempfile.mkdtemp(prefix="otranscribe-chunks-"))
    workdir.mkdir(parents=True, exist_ok=True)
    with contextlib.closing(wave.open(str(wav_path), "rb")) as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        frames_per_chunk = int(chunk_seconds * framerate)
        chunk_index = 0
        while True:
            frames = wf.readframes(frames_per_chunk)
            if not frames:
                break
            chunk_path = workdir / f"chunk_{chunk_index:04d}.wav"
            with contextlib.closing(wave.open(str(chunk_path), "wb")) as cf:
                cf.setnchannels(n_channels)
                cf.setsampwidth(sampwidth)
                cf.setframerate(framerate)
                cf.writeframes(frames)
            yield chunk_path
            chunk_index += 1
