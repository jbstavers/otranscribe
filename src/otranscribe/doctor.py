"""
Diagnostics and environment checks for otranscribe.

This module powers the `otranscribe doctor` command. It checks:
- Python version
- ffmpeg availability
- OpenAI API key (only if needed)
- Optional backend dependencies (local Whisper, faster-whisper)

Design goals:
- No heavy imports unless required
- Actionable "how to fix" output
- Works cross-platform with best-effort hints
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    name: str
    message: str
    fix: str | None = None


def check_python_version(min_major: int = 3, min_minor: int = 9) -> CheckResult:
    major, minor = sys.version_info[:2]
    if (major, minor) < (min_major, min_minor):
        return CheckResult(
            ok=False,
            name="python",
            message=f"Python {major}.{minor} is too old (need {min_major}.{min_minor}+)",
            fix=f"Install Python {min_major}.{min_minor}+ and recreate your venv",
        )
    return CheckResult(ok=True, name="python", message=f"Python {major}.{minor} OK")


def check_ffmpeg() -> CheckResult:
    if shutil.which("ffmpeg") is None:
        return CheckResult(
            ok=False,
            name="ffmpeg",
            message="ffmpeg not found on PATH",
            fix="Install ffmpeg (macOS: brew install ffmpeg | Ubuntu: sudo apt-get install ffmpeg | Windows: choco install ffmpeg)",
        )
    return CheckResult(ok=True, name="ffmpeg", message="ffmpeg found")


def check_openai_key() -> CheckResult:
    if os.getenv("OPENAI_API_KEY"):
        return CheckResult(ok=True, name="OPENAI_API_KEY", message="API key set")
    return CheckResult(
        ok=False,
        name="OPENAI_API_KEY",
        message="API key missing",
        fix='export OPENAI_API_KEY="sk-..." (required only for --engine openai)',
    )


def check_local_whisper_dep() -> CheckResult:
    try:
        import whisper  # type: ignore  # noqa: F401

        return CheckResult(
            ok=True, name="openai-whisper", message="openai-whisper installed"
        )
    except Exception:
        return CheckResult(
            ok=False,
            name="openai-whisper",
            message="openai-whisper not installed",
            fix="pip install otranscribe[local]  (or: pip install -r requirements-local.txt)",
        )


def check_faster_whisper_dep() -> CheckResult:
    try:
        import faster_whisper  # type: ignore  # noqa: F401

        return CheckResult(
            ok=True, name="faster-whisper", message="faster-whisper installed"
        )
    except Exception:
        return CheckResult(
            ok=False,
            name="faster-whisper",
            message="faster-whisper not installed",
            fix="pip install otranscribe[faster] (or: pip install -r requirements-faster.txt)",
        )


def run_checks(engine: str | None = None) -> list[CheckResult]:
    """
    Run checks for a specific engine or for all engines (engine=None).
    Valid engines: openai | local | faster
    """
    checks: list[CheckResult] = [
        check_python_version(),
        check_ffmpeg(),
    ]

    if engine in (None, "openai"):
        checks.append(check_openai_key())
    if engine in (None, "local"):
        checks.append(check_local_whisper_dep())
    if engine in (None, "faster"):
        checks.append(check_faster_whisper_dep())

    return checks


def format_report(engine: str | None = None) -> tuple[bool, list[str]]:
    """
    Returns (overall_ok, lines) for printing in CLI.
    """
    results = run_checks(engine)
    overall_ok = all(r.ok for r in results)

    lines: list[str] = []
    for r in results:
        status = "✓" if r.ok else "✗"
        line = f"{status} {r.name}: {r.message}"
        if (not r.ok) and r.fix:
            line += f" — {r.fix}"
        lines.append(line)

    return overall_ok, lines
