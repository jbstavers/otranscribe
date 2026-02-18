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

import json
from pathlib import Path
from typing import Any, Dict, List, Union

import requests


# The endpoint used for transcription.  This is stable according to
# OpenAI's documentation.  It accepts multipart/form-data with the file
# and parameters.
OPENAI_TRANSCRIPTION_URL = "https://api.openai.com/v1/audio/transcriptions"


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
        Path to a mono, 16 kHz WAV file.  Must exist.
    api_key : str
        The OpenAI API key.  It should not be passed on the
        command line to avoid leaking via shell history; instead set
        the ``OPENAI_API_KEY`` environment variable.
    model : str
        Name of the transcription model to use, e.g.
        ``gpt-4o-transcribe-diarize``.
    language : str
        Language code such as ``pt`` or ``en``.  See the API docs for
        supported values.
    response_format : str
        One of ``json``, ``verbose_json``, ``text``, ``srt``, ``vtt`` or
        ``diarized_json``.  The latter is required for speaker
        diarisation.
    chunking_strategy : str | None, optional
        Strategy for splitting long audio into chunks.  ``auto`` is
        recommended for diarised transcription of long audio (>30s).  If
        ``None`` no chunking_strategy field will be sent.

    Returns
    -------
    Any
        The API response.  For JSON based formats this is a Python
        dict/list, for text formats it is a str.

    Raises
    ------
    RuntimeError
        If the API call fails or returns an unexpected status code.
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    files = {
        "file": (wav_path.name, wav_path.read_bytes(), "audio/wav"),
    }
    data: Dict[str, Union[str, bytes]] = {
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
    if ("application/json" in content_type) or (response_format in {"json", "verbose_json", "diarized_json"}):
        return resp.json()
    return resp.text