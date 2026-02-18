"""
Unit tests for the :mod:`otranscribe.render` module.

These tests exercise the rendering logic to ensure that timestamps,
speaker grouping and cleaning behave as expected.
"""

from __future__ import annotations

import pytest

from otranscribe.render import render_final


def test_render_final_groups_by_bucket_and_speaker() -> None:
    """Segments should group by bucket and speaker correctly."""
    # Construct a fake API result with two speakers and multiple segments.
    api_result = {
        "segments": [
            {"start": 0.0, "text": "Olá, tudo bem?", "speaker": "SPEAKER_00"},
            {"start": 5.0, "text": "Sim, e contigo?", "speaker": "SPEAKER_00"},
            {"start": 35.0, "text": "Estou óptimo.", "speaker": "SPEAKER_01"},
            {"start": 65.0, "text": "Que bom!", "speaker": "SPEAKER_00"},
        ]
    }
    result = render_final(api_result, every_seconds=30)
    lines = result.strip().split("\n")
    assert lines[0].startswith("[00:00:00] Speaker 0: ")
    assert "Olá, tudo bem? Sim, e contigo?" in lines[0]
    assert lines[1].startswith("[00:00:30] Speaker 1: Estou óptimo.")
    assert lines[2].startswith("[00:01:00] Speaker 0: Que bom!")


def test_render_final_cleans_fillers() -> None:
    """Filler words should be removed and whitespace collapsed."""
    api_result = {
        "segments": [
            {"start": 0.0, "text": "hã hã, hum vamos lá", "speaker": "SPEAKER_00"}
        ]
    }
    result = render_final(api_result, every_seconds=30)
    assert "hã" not in result
    assert "hum" not in result
    assert "vamos lá" in result