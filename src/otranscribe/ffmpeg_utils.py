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


def convert_to_wav_16k_mono(input_path: Path, *, temp_dir: Path | None = None) -> Path:
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
        str(wav_path),
    ]

    subprocess.run(cmd, check=True)
    return wav_path