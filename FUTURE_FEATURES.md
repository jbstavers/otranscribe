# Future Features for `otranscribe`

This document outlines enhancements and ideas that are not yet
implemented but could be added in future releases.  Feel free to
contribute or discuss any of these on the project issue tracker.

## Diarisation without the OpenAI API

Currently only the OpenAI engine provides speaker labels.  A natural
extension is to integrate a local diarisation model (e.g. via
`pyannote.audio`) so that offline transcriptions can also assign
speaker identities.  This would allow fully offline workflows with
speaker separation, albeit with additional dependencies and higher
resource usage.

## Resume or partial caching of long files

The existing cache stores complete transcriptions keyed by input
options.  Another optimisation is to cache partial results during
chunked offline transcription so that interrupted runs can resume
without repeating work.  This could involve storing per‑chunk
transcriptions and recombining them if the same file is processed
again.

## Alternative Markdown formats

The current Markdown renderer supports a simple bullet list and a
meeting‑style heading format.  Additional styles could be provided,
such as collapsible summaries, tables grouping utterances by speaker,
or templates for popular note‑taking tools.

## Richer post‑processing

Beyond removing simple filler words, some users may want more
sophisticated editing: normalising numbers, correcting common
disfluencies, grouping questions and answers, or generating a summary
section with action items.  These operations should remain optional
and be clearly separated from the faithful transcript.

## Progress reporting and interactive UI

For very long files it can be useful to see progress or receive
intermediate output while transcription is running.  A progress bar
could be printed to the console, or a simple GUI could be offered as
an optional frontend.
