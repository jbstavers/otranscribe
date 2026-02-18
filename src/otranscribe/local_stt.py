"""
Local speech‑to‑text backend using the Whisper model.

This module implements a thin wrapper around the open source Whisper
transcription model provided by the ``openai-whisper`` package.  It
provides a function :func:`transcribe_local` with a similar API to
``otranscribe.openai_stt.transcribe_file``.  The returned dict
contains a ``text`` field with the full transcript and a ``segments``
list.  Since the open source Whisper models do not perform speaker
diarisation, all segments are assigned a single speaker label.

To use this backend you must install the ``openai-whisper`` package
(``pip install openai-whisper``).  If the package is missing, an
informative error is raised.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def transcribe_local(*, wav_path: Path, language: str, model: str) -> dict[str, Any]:
    """Transcribe a WAV file using a local Whisper model.

    Parameters
    ----------
    wav_path : Path
        Path to a mono, 16 kHz WAV file.  Must exist.
    language : str
        Language code such as ``pt`` or ``en``.  Whisper will attempt
        to use this hint for transcription.  Note that Whisper's
        language codes are case sensitive.
    model : str
        Name of the Whisper model to use.  Valid values include
        ``tiny``, ``base``, ``small``, ``medium``, ``large``.  The
        ``medium`` model is a good default for balanced performance.

    Returns
    -------
    dict
        A dict containing ``text`` with the full transcription and
        ``segments`` as a list of dicts.  Each segment has ``start``,
        ``end``, ``text`` and ``speaker`` keys.  Since the local
        backend does not have speaker diarisation, all segments use
        ``Speaker 0``.

    Raises
    ------
    RuntimeError
        If the ``whisper`` package is not installed or fails to
        transcribe the audio.
    """
    try:
        import whisper  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "The 'whisper' package is required for local transcription but is"
            " not installed.  Install it via 'pip install openai-whisper'"
        ) from exc

    # Load the specified model.  Whisper caches models under ~/.cache.
    try:
        whisper_model = whisper.load_model(model)
    except Exception as exc:
        raise RuntimeError(f"Failed to load Whisper model '{model}': {exc}") from exc

    # Perform the transcription.  We disable timestamps and segments
    # separately because we want segment boundaries for later rendering.
    try:
        result: dict[str, Any] = whisper_model.transcribe(
            str(wav_path), language=language, verbose=False
        )
    except Exception as exc:
        raise RuntimeError(f"Whisper failed to transcribe: {exc}") from exc

    # Whisper returns a dict with a 'segments' list.  Each segment is
    # already a dict containing 'start', 'end' and 'text'.  Add a
    # default speaker label to each segment to satisfy downstream
    # rendering code.  We use 'Speaker 0' since diarisation is not
    # available.
    segments = result.get("segments", [])
    if isinstance(segments, list):
        for seg in segments:
            if isinstance(seg, dict):
                seg["speaker"] = "Speaker 0"

    return result
