"""Tests for ffmpeg_utils helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from otranscribe.ffmpeg_utils import convert_to_wav_16k_mono


@patch("otranscribe.ffmpeg_utils.subprocess.run")
def test_convert_without_duration(mock_run, tmp_path: Path) -> None:
    """When duration is None, -t should NOT appear in the command."""
    fake_input = tmp_path / "input.mp4"
    fake_input.touch()

    convert_to_wav_16k_mono(fake_input, temp_dir=tmp_path)

    cmd = mock_run.call_args[0][0]
    assert "-t" not in cmd


@patch("otranscribe.ffmpeg_utils.subprocess.run")
def test_convert_with_duration(mock_run, tmp_path: Path) -> None:
    """When duration is set, -t <seconds> should appear before the output path."""
    fake_input = tmp_path / "input.mp4"
    fake_input.touch()

    convert_to_wav_16k_mono(fake_input, temp_dir=tmp_path, duration=60)

    cmd = mock_run.call_args[0][0]
    t_index = cmd.index("-t")
    assert cmd[t_index + 1] == "60"
    # -t should come before the output path (last element)
    assert t_index < len(cmd) - 1
