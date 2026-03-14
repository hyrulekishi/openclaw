# Media Pipeline (Phase 1)

Local transcription layer for audio/video -> transcript.

Current phase:
- `config/default.yaml`
- `requirements.txt`
- `scripts/doctor.sh`
- `scripts/extract_audio.sh`
- `scripts/transcribe.py`
- `scripts/fetch_media.py`

## Current model profiles

- `fast`: `medium`
- `balanced`: `large-v3-turbo`
- `best`: `large-v3`
- `default_profile`: `balanced`

## Validation summary (2026-03-14)

Environment validation:
- WSL2 + RTX 3080 Laptop GPU detected
- CUDA path usable by `faster-whisper`
- `yt-dlp`, `ffmpeg`, `ctranslate2`, `faster-whisper` all working

What worked:
- Telegram inbound audio can land in `~/.openclaw/media/inbound/` when media fetch succeeds
- Local audio transcription works end-to-end
- URL -> download -> transcription works for Bilibili and YouTube
- English transcription with `balanced` is usable
- Japanese transcription improves significantly with `best` (`large-v3`)
- Chinese Bilibili speech improves significantly with `balanced = large-v3-turbo`

What did not work well:
- Earlier `balanced = distil-large-v3` was not reliable enough for Chinese/Japanese video speech
- Large Telegram media downloads are still unstable due to OpenClaw Telegram media fetch issues
- Translation + subtitle alignment has not been formalized yet; only transcription is considered complete for Phase 1

## Phase 1 conclusion

Phase 1 local transcription is considered **working**.

Recommended usage:
- English: start with `balanced`
- Chinese/Japanese: prefer `balanced` (`large-v3-turbo`)
- Harder or important multilingual cases: use `best` (`large-v3`)

## Next phase (not implemented yet)

- translation
- subtitle alignment / SRT generation
- optional cleanup / temp file lifecycle
- optional TTS pipeline
