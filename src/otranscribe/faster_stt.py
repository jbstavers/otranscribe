"""
Local speech‑to‑text backend using the faster‑whisper package.

This module provides a wrapper around the `faster‑whisper` library, which is a
reimplementation of OpenAI's Whisper model using CTranslate2.  It offers
significant performance improvements compared to the original `openai‑whisper`
implementation by leveraging efficient transformer inference and optional
quantisation【857958726967427†L295-L297】.  GPU support is available when
specified.

The primary function exported here is :func:`transcribe_faster`, which
transcribes a WAV file and returns a dict in the same shape as the
`transcribe_file` and `transcribe_local` functions used by the CLI.

It requires the `faster‑whisper` Python package, which can be installed
separately (e.g. via `pip install faster-whisper`).  If the package is
missing an informative error will be raised.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def transcribe_faster(
    *,
    wav_path: Path,
    model_size: str = "base",
    language: str = "en",
    device: str = "cpu",
    compute_type: str = "int8",
    beam_size: int = 5,
) -> dict[str, Any]:
    """Transcribe a WAV file using the faster‑whisper backend.

    Parameters
    ----------
    wav_path : Path
        Path to a mono, 16 kHz WAV file.  Must exist.
    model_size : str, optional
        The size of the model to use (e.g. 'tiny', 'base', 'small', 'medium', 'large').
        Larger models offer higher accuracy at the cost of speed.  Defaults to 'base'.
    language : str, optional
        Language code for the input audio.  Note that faster‑whisper autodetects
        language if not specified, but setting this can improve accuracy.
    device : str, optional
        Device to run the model on.  Use 'cpu', 'cuda' or 'auto'.  The default
        'cpu' avoids requiring a GPU.  Set to 'cuda' to run on an Nvidia GPU.
    compute_type : str, optional
        Precision / quantisation mode.  Common values include 'int8', 'fp16',
        'float16'.  Lower precision modes (int8) use less memory and can be
        faster at the expense of a small drop in accuracy【857958726967427†L295-L297】.
    beam_size : int, optional
        Beam search size controlling decoding complexity.  The default is 5.

    Returns
    -------
    dict
        A dict containing ``text`` and ``segments`` keys.  Each segment is a
        dict with ``start``, ``end``, ``text`` and ``speaker`` (fixed to
        ``Speaker 0`` since faster‑whisper does not do diarisation).

    Raises
    ------
    RuntimeError
        If the `faster‑whisper` package is not installed or if transcription
        fails for another reason.
    """
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "The 'faster-whisper' package is required for the faster engine but is not installed."
            " Install it via 'pip install faster-whisper' or select a different engine."
        ) from exc

    # Instantiate the model.  WhisperModel will download or load the model from
    # cache on first use.  We pass the device and compute_type to control
    # hardware utilisation and quantisation.  'cpu' device means CPU only.
    try:
        model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Failed to load faster-whisper model '{model_size}': {exc}"
        ) from exc

    # Transcribe the audio.  faster‑whisper returns a generator of segments and
    # an info object.  We collect all segments into a list so we can assign
    # speaker labels and build the full text.
    try:
        segments_gen, info = model.transcribe(
            str(wav_path),
            beam_size=beam_size,
            language=language,
        )
    except Exception as exc:
        raise RuntimeError(f"faster-whisper failed to transcribe: {exc}") from exc

    segments_list: list[dict[str, Any]] = []
    full_text_parts: list[str] = []
    # faster‑whisper's segments generator yields objects with start, end, and text
    for seg in segments_gen:
        try:
            start = float(seg.start)
        except Exception:
            start = 0.0
        try:
            end = float(seg.end)
        except Exception:
            end = 0.0
        text = getattr(seg, "text", "") or ""
        segments_list.append(
            {
                "start": start,
                "end": end,
                "text": text,
                "speaker": "Speaker 0",
            }
        )
        full_text_parts.append(text)

    return {
        "text": "".join(full_text_parts),
        "segments": segments_list,
    }
