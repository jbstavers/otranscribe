from __future__ import annotations

from otranscribe.doctor import check_ffmpeg, check_openai_key, check_python_version


def test_check_python_version_ok():
    res = check_python_version(3, 8)
    assert res.ok


def test_check_openai_key_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    res = check_openai_key()
    assert not res.ok
    assert "missing" in res.message.lower()


def test_check_openai_key_present(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    res = check_openai_key()
    assert res.ok


def test_check_ffmpeg_missing(monkeypatch):
    import shutil

    monkeypatch.setattr(shutil, "which", lambda _: None)
    res = check_ffmpeg()
    assert not res.ok


def test_check_ffmpeg_present(monkeypatch):
    import shutil

    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/ffmpeg")
    res = check_ffmpeg()
    assert res.ok