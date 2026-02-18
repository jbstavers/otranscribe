# src/otranscribe/cache.py
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def compute_cache_key(
    wav_path: Path,
    *,
    engine: str,
    model: str,
    language: str,
    api_format: str,
    chunk_seconds: int | None = None,
) -> str:
    h = hashlib.sha256()
    h.update(wav_path.read_bytes())
    h.update(engine.encode())
    h.update(model.encode())
    h.update(language.encode())
    h.update(api_format.encode())
    h.update(str(chunk_seconds or 0).encode())
    return h.hexdigest()


def load_cached_result(cache_dir: Path, key: str) -> Any | None:
    path = cache_dir / f"{key}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_cached_result(cache_dir: Path, key: str, result: Any) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{key}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")