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
from collections.abc import Iterable
from typing import Any

# Patterns of filler words to remove.  Use word boundaries to avoid
# partial matches.  Feel free to add additional Portuguese fillers here.
# Patterns of filler words to remove.  Use word boundaries to avoid
# partial matches.  Additional Portuguese fillers (like "um") can be
# appended here.  The list is deliberately conservative; users can
# override cleaning behaviour by adjusting the list at runtime if
# necessary.
_FILLERS = [
    r"\b(hã+|hum+|uh+|eh+|um+|tipo|pronto|ok(ay)?|está bem)\b",
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


def _normalise_speaker_label(label: Any) -> str:
    """Normalise OpenAI diarisation labels to a canonical form.

    The OpenAI API returns speaker labels like ``SPEAKER_00``.  This
    helper converts those into ``Speaker 0``.  For any other string
    values it returns the value unchanged.  Non‑string values are
    stringified.
    """
    # Ensure we have a string representation
    s = str(label)
    if s.upper().startswith("SPEAKER_"):
        try:
            idx = int(s.split("_")[1])
            return f"Speaker {idx}"
        except Exception:
            # Fall back to replacing the prefix
            return s.replace("SPEAKER_", "Speaker ")
    return s


def _apply_speaker_map(label: str, speaker_map: dict[str, str] | None) -> str:
    """Apply a user provided speaker map to a label.

    If ``speaker_map`` is not ``None`` and contains the key ``label``,
    return the mapped value.  Otherwise return ``label`` unchanged.
    """
    if speaker_map and label in speaker_map:
        return speaker_map[label]
    return label


def _render_lines_txt(
    segments: Iterable[dict[str, Any]],
    *,
    every_seconds: int,
    speaker_map: dict[str, str] | None = None,
) -> list[str]:
    """Render diarised segments as plain text lines.

    Segments are grouped into buckets of ``every_seconds`` seconds and
    by speaker.  When either the bucket or speaker changes a new line
    is started.  Each line is prefixed with ``[HH:MM:SS] <speaker>:``.
    """
    lines: list[str] = []
    current_bucket: int | None = None
    last_speaker: str | None = None
    for seg in segments:
        try:
            start = float(seg.get("start", 0))
        except Exception:
            start = 0.0
        text = _clean_text(seg.get("text", ""))
        if not text:
            continue
        speaker_raw = seg.get("speaker", "Speaker ?")
        speaker = _normalise_speaker_label(speaker_raw)
        speaker = _apply_speaker_map(speaker, speaker_map)
        bucket = int(math.floor(start / every_seconds) * every_seconds)
        new_block = (
            current_bucket is None
            or bucket != current_bucket
            or speaker != last_speaker
        )
        if new_block:
            lines.append(f"[{_ts(bucket)}] {speaker}: {text}")
            current_bucket = bucket
            last_speaker = speaker
        else:
            lines[-1] += " " + text
    return lines


def _render_lines_md(
    segments: Iterable[dict[str, Any]],
    *,
    every_seconds: int,
    speaker_map: dict[str, str] | None = None,
    style: str = "simple",
) -> list[str]:
    """Render diarised segments as Markdown lines.

    Two styles are supported:

    - ``simple``: each utterance becomes a bullet point with a bold
      timestamp and speaker name, followed by the cleaned text.
    - ``meeting``: each utterance starts a new heading (level 3) with
      the timestamp and speaker on the same line, followed by the text
      in a new paragraph.  This format is useful for meeting notes
      where each intervention is clearly separated.

    Parameters
    ----------
    segments: Iterable[dict[str, Any]]
        List of diarised segments from the API.
    every_seconds: int
        Bucket duration for grouping.
    speaker_map: Optional[dict[str, str]], optional
        Optional mapping from internal labels to user supplied names.
    style: str, default "simple"
        Rendering style (``simple`` or ``meeting``).
    """
    lines: list[str] = []
    current_bucket: int | None = None
    last_speaker: str | None = None
    for seg in segments:
        try:
            start = float(seg.get("start", 0))
        except Exception:
            start = 0.0
        text = _clean_text(seg.get("text", ""))
        if not text:
            continue
        speaker_raw = seg.get("speaker", "Speaker ?")
        speaker = _normalise_speaker_label(speaker_raw)
        speaker = _apply_speaker_map(speaker, speaker_map)
        bucket = int(math.floor(start / every_seconds) * every_seconds)
        new_block = (
            current_bucket is None
            or bucket != current_bucket
            or speaker != last_speaker
        )
        if new_block:
            if style == "meeting":
                # Heading per utterance
                lines.append(f"### [{_ts(bucket)}] {speaker}")
                lines.append("")
                lines.append(text)
            else:
                # simple bullet list
                lines.append(f"- **[{_ts(bucket)}] {speaker}:** {text}")
            current_bucket = bucket
            last_speaker = speaker
        else:
            # continuation of previous block
            if style == "meeting":
                lines[-1] += " " + text
            else:
                lines[-1] += " " + text
    return lines


def render_final(
    api_result: Any,
    *,
    every_seconds: int = 30,
    speaker_map: dict[str, str] | None = None,
    out_format: str = "txt",
    md_style: str = "simple",
) -> str:
    """Render a diarised transcript into cleaned text or Markdown.

    The input ``api_result`` should be a mapping containing a ``segments``
    list.  Each segment is expected to have ``start``, ``text`` and
    ``speaker`` fields.  The ``speaker`` labels are normalised and may
    be remapped via a user provided mapping.  Utterances are grouped
    into buckets of ``every_seconds`` seconds and broken into new lines
    when the speaker changes or the bucket boundary is crossed.

    Parameters
    ----------
    api_result: Any
        Parsed JSON result from the API or local engine.  If it does
        not contain ``segments`` then the ``text`` field is cleaned
        and returned.
    every_seconds: int, default 30
        Duration of each bucket for timestamping.  Lower values
        produce more frequent timestamps.
    speaker_map: Optional[dict[str, str]], optional
        Mapping from normalised speaker labels (e.g. ``Speaker 0``) to
        user provided names.  Keys must match the labels produced by
        :func:`_normalise_speaker_label`.
    out_format: str, default "txt"
        Output format: ``txt`` returns plain text lines; ``md``
        returns Markdown lines using the style defined by
        ``md_style``.
    md_style: str, default "simple"
        Markdown style used when ``out_format`` is ``md``.  ``simple``
        produces a bullet list; ``meeting`` produces heading‑style
        meeting notes.

    Returns
    -------
    str
        Rendered transcript with a trailing newline.  If there are no
        segments the cleaned ``text`` field is returned.
    """
    # If the API returned plain text or some other type, return it unchanged.
    if not isinstance(api_result, dict):
        return str(api_result)

    segments = api_result.get("segments")
    if not isinstance(segments, list) or not segments:
        text = api_result.get("text", "")
        return _clean_text(text) + ("\n" if text else "")

    # Choose renderer based on output format
    out_format = out_format.lower()
    if out_format == "md":
        lines = _render_lines_md(
            segments,
            every_seconds=every_seconds,
            speaker_map=speaker_map,
            style=md_style,
        )
    else:
        lines = _render_lines_txt(
            segments,
            every_seconds=every_seconds,
            speaker_map=speaker_map,
        )
    return "\n".join(lines).rstrip() + "\n"
