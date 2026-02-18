# Future Features

This document tracks ideas and improvements for `otranscribe`.
Items may move between sections as they get implemented.

## Done

- [x] **Cache / resume** (impact: huge, effort: medium)
  Persist transcription results keyed by input + engine/model parameters so reruns are instant.

- [x] **Local chunking** (impact: huge for long audio, effort: medium)
  Chunk long WAV files for offline engines and merge segments back with correct time offsets.

- [x] **Speaker map + Markdown output** (impact: high, effort: low)
  Allow mapping `Speaker 0` → `Interviewer` etc. and render cleaned output as `.md` with styles.

## Next Up (Recommended)

- [ ] **CI pipeline (GitHub Actions)**
  Run `pytest` + basic install/import checks on every PR to prevent packaging/import regressions.

- [ ] **Packaging + release pipeline**
  Automated versioning + publishing to PyPI (when you decide to release).

- [ ] **Better diarisation locally**
  Optional integration with a diarisation model (e.g., pyannote) to label speakers offline.

## Ideas / Nice-to-haves

- [ ] **Progress + ETA for offline transcription**
  Show progress per chunk/model inference so long runs feel responsive.

- [ ] **More output formats**
  Add `--out-format docx` / `--out-format srt` post-processing styles beyond raw engine formats.

- [ ] **Config file support**
  Load defaults from `.otranscribe.toml` (engine/model/language/render settings).

- [ ] **Speaker naming UX**
  CLI prompts or interactive mode to rename speakers after first diarised run.

- [ ] **Better merge logic for offline chunking**
  Smarter overlap handling (dedupe repeated text near chunk boundaries).

- [ ] **Performance guide**
  A short doc with recommended models/settings per CPU/GPU, plus memory expectations.
