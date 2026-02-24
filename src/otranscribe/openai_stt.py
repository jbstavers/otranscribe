"""
Wrapper for OpenAI's speech‑to‑text API.

This module exposes a single function, :func:`transcribe_file`, which
takes a WAV file on disk, calls the OpenAI transcription endpoint and
returns the parsed result.  It intentionally avoids pulling in the
official ``openai`` client as a dependency to keep the package lean.

The API endpoint and behaviour are documented at:
https://developers.openai.com/api/reference/resources/audio/subresources/transcriptions

Speaker diarisation requires using a model with ``-diarize`` suffix and
setting ``response_format=diarized_json``.  Long audio (>30 seconds)
should set ``chunking_strategy=auto`` to allow the API to chunk the
input appropriately.  See the OpenAI docs for full details.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import requests

# The endpoint used for transcription.  This is stable according to
# OpenAI's documentation.  It accepts multipart/form-data with the file
# and parameters.
OPENAI_TRANSCRIPTION_URL = "https://api.openai.com/v1/audio/transcriptions"


_MIME_BY_EXT: dict[str, str] = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".webm": "audio/webm",
}


def _mime_for_path(path: Path) -> str:
    """Return an appropriate MIME type for an audio file based on its extension."""
    return _MIME_BY_EXT.get(path.suffix.lower(), "application/octet-stream")


def transcribe_file(
    *,
    wav_path: Path,
    api_key: str,
    model: str,
    language: str,
    response_format: str,
    chunking_strategy: str | None = None,
) -> Any:
    """Call the OpenAI Speech‑to‑Text API and return the parsed response.

    Parameters
    ----------
    wav_path : Path
        Path to an audio file.  Accepts any format supported by OpenAI
        (wav, mp3, m4a, mp4, ogg, flac, webm).
    api_key : str
        The OpenAI API key.
    model : str
        Name of the transcription model to use.
    language : str
        Language code such as ``pt`` or ``en``.
    response_format : str
        One of ``json``, ``verbose_json``, ``text``, ``srt``, ``vtt`` or
        ``diarized_json``.
    chunking_strategy : str | None, optional
        Strategy for splitting long audio into chunks.  ``auto`` is
        recommended for diarised transcription of long audio (>30s).

    Returns
    -------
    Any
        The API response.

    Raises
    ------
    RuntimeError
        If the API call fails or returns an unexpected status code.
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    mime_type = _mime_for_path(wav_path)
    files = {
        "file": (wav_path.name, wav_path.read_bytes(), mime_type),
    }
    data: dict[str, str | bytes] = {
        "model": model,
        "language": language,
        "response_format": response_format,
    }
    if chunking_strategy:
        data["chunking_strategy"] = chunking_strategy

    # Post the request.  We set a high timeout because long audio can
    # take some time to process.  We rely on requests raising for
    # network errors.
    resp = requests.post(
        OPENAI_TRANSCRIPTION_URL,
        headers=headers,
        files=files,
        data=data,
        timeout=600,
    )

    if resp.status_code >= 300:
        raise RuntimeError(f"OpenAI API error {resp.status_code}: {resp.text}")

    # Determine whether to parse JSON.  The API returns JSON when the
    # response_format is one of the JSON types, otherwise plain text.
    content_type = resp.headers.get("content-type", "")
    if ("application/json" in content_type) or (
        response_format in {"json", "verbose_json", "diarized_json"}
    ):
        return resp.json()
    return resp.text


def transcribe_chunked(
    *,
    chunk_paths: Sequence[Path],
    api_key: str,
    model: str,
    language: str,
    response_format: str,
    chunking_strategy: str | None = None,
) -> dict[str, Any]:
    """Transcribe multiple audio chunks and stitch results together.

    Each chunk is uploaded individually via :func:`transcribe_file`.
    Segment timestamps are offset by the cumulative duration of all
    preceding chunks so that the merged result has continuous timing.

    Returns a single dict with ``text`` and ``segments`` keys, matching
    the shape of a normal ``transcribe_file()`` response.
    """
    from .ffmpeg_utils import audio_duration_seconds

    all_segments: list[dict[str, Any]] = []
    all_text_parts: list[str] = []
    offset = 0.0
    total = len(chunk_paths)

    for idx, chunk_path in enumerate(chunk_paths, 1):
        print(f"Uploading chunk {idx}/{total}...")
        result = transcribe_file(
            wav_path=chunk_path,
            api_key=api_key,
            model=model,
            language=language,
            response_format=response_format,
            chunking_strategy=chunking_strategy,
        )

        if isinstance(result, dict):
            text = result.get("text", "")
            segments = result.get("segments", [])
        else:
            text = str(result)
            segments = []

        all_text_parts.append(text)

        for seg in segments:
            seg_copy = dict(seg)
            try:
                seg_copy["start"] = float(seg_copy.get("start", 0)) + offset
                seg_copy["end"] = float(seg_copy.get("end", 0)) + offset
            except (TypeError, ValueError):
                pass
            all_segments.append(seg_copy)

        offset += audio_duration_seconds(chunk_path)

    return {
        "text": " ".join(all_text_parts),
        "segments": all_segments,
    }
