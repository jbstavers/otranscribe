"""
Rendering utilities for producing a cleaned transcript with timestamps and
speaker labels.

The primary function exported by this module is
:func:`render_final`, which expects a parsed API result (as returned
by :func:`otranscribe.openai_stt.transcribe_file` with
``response_format='diarized_json'``) and produces a human friendly
transcript.  The transcript groups utterances into buckets of a
configurable duration and inserts a new line whenever the speaker
changes or a bucket boundary is crossed.

Cleaning rules:

* Remove filler words such as "hã", "hum" and their variants.
* Collapse multiple whitespace into a single space and trim leading
  and trailing spaces.
* Remove spaces before punctuation like commas and periods.

These rules are deliberately conservative; the goal is to tidy up the
output without altering meaning.
"""

from __future__ import annotations

import math
import re
from typing import Any, Iterable, List

# Patterns of filler words to remove.  Use word boundaries to avoid
# partial matches.  Feel free to add additional Portuguese fillers here.
_FILLERS = [
    r"\b(hã+|hum+|uh+|eh+|tipo|pronto|ok(ay)?|está bem)\b",
]


def _ts(seconds: float) -> str:
    """Format seconds as HH:MM:SS (zero padded)."""
    s = max(0, int(seconds))
    h = s // 3600
    m = (s % 3600) // 60
    ss = s % 60
    return f"{h:02d}:{m:02d}:{ss:02d}"


def _clean_text(t: str) -> str:
    """Apply conservative cleaning to a segment of transcript text.

    Strips leading/trailing whitespace, collapses multiple spaces, removes
    filler words defined in :data:`_FILLERS`, and eliminates spaces
    before common punctuation.  Returns the cleaned string.
    """
    if not t:
        return ""
    # Collapse whitespace and strip.
    text = re.sub(r"\s+", " ", t).strip()
    # Remove fillers.
    for pat in _FILLERS:
        text = re.sub(pat, "", text, flags=re.IGNORECASE)
    # Collapse whitespace again in case fillers created doubles.
    text = re.sub(r"\s+", " ", text).strip()
    # Remove spaces before punctuation.
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text


def render_final(api_result: Any, *, every_seconds: int = 30) -> str:
    """Render a diarised OpenAI response into a cleaned transcript.

    The API response must be a dict containing a ``segments`` list.  Each
    element of the list should be a dict with at least ``start``,
    ``text`` and ``speaker`` keys.  ``speaker`` values like
    ``SPEAKER_00`` are normalised to ``Speaker 0`` etc.

    The output groups contiguous segments by speaker and into buckets of
    ``every_seconds`` seconds.  A new line starts when either the
    speaker changes or the bucket boundary is crossed.  Each line is
    prefixed with a timestamp in the format ``[HH:MM:SS]``.

    Parameters
    ----------
    api_result: Any
        Parsed JSON result from the API.  Should contain a ``segments``
        key if diarised.
    every_seconds: int, default 30
        Bucket size for timestamp insertion.  Changing this affects
        how often timestamps are emitted.

    Returns
    -------
    str
        A multi‑line transcript.  Each line begins with a timestamp and
        a normalised speaker label followed by cleaned dialogue.
    """
    if not isinstance(api_result, dict):
        # If the API returned plain text or some other type, return it
        # unchanged.
        return str(api_result)

    segments = api_result.get("segments")
    if not isinstance(segments, list) or not segments:
        text = api_result.get("text", "")
        return _clean_text(text) + ("\n" if text else "")

    lines: List[str] = []
    current_bucket: int | None = None
    last_speaker: str | None = None

    for seg in segments:
        try:
            start = float(seg.get("start", 0))
        except Exception:
            start = 0.0
        raw_text = seg.get("text", "")
        cleaned = _clean_text(raw_text)
        if not cleaned:
            continue
        speaker = seg.get("speaker", "Speaker ?")
        # Normalise OpenAI speaker labels (e.g. SPEAKER_00 -> Speaker 0)
        if isinstance(speaker, str) and speaker.upper().startswith("SPEAKER_"):
            try:
                idx = int(speaker.split("_")[1])
                speaker = f"Speaker {idx}"
            except Exception:
                speaker = speaker.replace("SPEAKER_", "Speaker ")
        else:
            # Fallback if unknown type.
            speaker = str(speaker)
        bucket = int(math.floor(start / every_seconds) * every_seconds)
        new_block = (
            current_bucket is None
            or bucket != current_bucket
            or speaker != last_speaker
        )
        if new_block:
            lines.append(f"[{_ts(bucket)}] {speaker}: {cleaned}")
            current_bucket = bucket
            last_speaker = speaker
        else:
            lines[-1] += " " + cleaned

    return "\n".join(lines).rstrip() + "\n"