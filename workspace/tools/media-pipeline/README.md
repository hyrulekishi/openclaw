# Media Pipeline

Local media/text translation pipeline with optional transcription and local refinement.

## Main scripts

- `config/default.yaml`
- `requirements.txt`
- `scripts/doctor.sh`
- `scripts/extract_audio.sh`
- `scripts/fetch_media.py`
- `scripts/transcribe.py`
- `scripts/normalize_input.py`
- `scripts/translate_segments.py`
- `scripts/emit_outputs.py`
- `scripts/compose_subtitle_video.py`
- `scripts/run_translation.py`

## Current model profiles

- `fast`: `medium`
- `balanced`: `large-v3-turbo`
- `best`: `large-v3`
- `default_profile`: `balanced`

## Current pipeline split

### 1) Audio / video -> transcript

Use `scripts/transcribe.py`.

Recommended usage:
- English: start with `balanced`
- Chinese/Japanese: prefer `balanced` (`large-v3-turbo`)
- Harder or important multilingual cases: use `best` (`large-v3`)

### 2) Text / transcript -> translation outputs

Use `scripts/run_translation.py`.

This runner does:
- normalize input
- translate segments
- optional local second-pass refinement
- emit final text / subtitle outputs
- optionally compose a subtitled video when given a source video

Base translation is treated as foundational:
- if Google translation fails, the run exits quickly
- default base translation retries: `2`
- default base translation max chars per batch: `1500`
- base translation batches are grouped by total source characters, not fixed segment count
- refinement is optional and may be skipped, but base translation is not

## Default output retention

The pipeline now keeps only minimal deliverables by default.

### Default mode

Text-like inputs:
- `translated.json`
- `translated.txt`

Timed transcript inputs:
- `translated.json`
- `translated.txt`
- `subtitles.zh.srt` (when timestamps exist)

### `--debug` mode

Additional artifacts are preserved only in debug mode:
- `normalized.json`
- `translated.partial.json`
- `bilingual.txt`
- `transcript.txt`
- `meta.json`

Notes:
- `normalized.json` is temporary by default when using `scripts/run_translation.py`
- old `translated.partial.json` is cleaned up automatically after successful non-debug runs
- old `bilingual.txt` is removed in non-debug output emission

## Refinement behavior

Local refinement is enabled by default in `scripts/run_translation.py`.

- default endpoint: `http://127.0.0.1:1235`
- default refine max chars per batch: `2200` (combined source + base translation)
- default refine retries per chunk: `2`
- legacy refine chunk size hint: `8`
- local model readiness wait: `10s`
- per refine request timeout: `40s`
- refine uses line-based output parsing (`REFINE::<id>::...`) instead of JSON arrays
- obviously noisy segments can be skipped from refine automatically
- default behavior on timeout / unavailable local model: skip refinement and keep base translation
- strict failure mode: `--refine-strict`
- disable refinement explicitly: `--no-refine`

Translation/refinement result fields in `translated.json`:
- `translate_status`
- `translate_error`
- `translate_elapsed_ms`
- `translate_max_chars_used`
- `refine_requested`
- `refine_applied`
- `refine_status`
- `refine_error`
- `refine_elapsed_ms`
- `refine_chunk_size_used`
- `refine_max_chars_used`
- `refine_skipped_noisy`
- `refine_partial_missing`

Current `refine_status` values:
- `not_requested`
- `requested`
- `applied`
- `no_change`
- `not_ready`
- `timeout`
- `failed`

## Examples

### Translate a markdown/text file

```bash
python3 scripts/run_translation.py \
  --input /home/user/.openclaw/workspace/SOUL.md \
  --target-lang zh \
  --out-dir output/soul-final
```

### Translate without local refine

```bash
python3 scripts/run_translation.py \
  --input /home/user/.openclaw/workspace/SOUL.md \
  --target-lang zh \
  --no-refine \
  --out-dir output/soul-no-refine
```

### Keep intermediate artifacts for debugging

```bash
python3 scripts/run_translation.py \
  --input /home/user/.openclaw/workspace/SOUL.md \
  --target-lang zh \
  --debug \
  --out-dir output/soul-debug
```

### Compose a subtitled video during translation run

```bash
python3 scripts/run_translation.py \
  --input output/test-audio/transcript.json \
  --type transcript \
  --target-lang zh-CN \
  --out-dir output/test-video-subbed \
  --compose-video \
  --video-input /path/to/source.mp4 \
  --compose-mode burn
```

### Compose from an existing video + SRT directly

Burned subtitles:

```bash
python3 scripts/compose_subtitle_video.py \
  --video /path/to/source.mp4 \
  --srt output/test-video-subbed/subtitles.zh.srt \
  --output output/test-video-subbed/subtitled.burned.mp4 \
  --mode burn \
  --overwrite
```

Soft subtitles:

```bash
python3 scripts/compose_subtitle_video.py \
  --video /path/to/source.mp4 \
  --srt output/test-video-subbed/subtitles.zh.srt \
  --output output/test-video-subbed/subtitled.softsub.mp4 \
  --mode soft \
  --overwrite
```

### Transcribe local audio

```bash
python3 scripts/transcribe.py \
  /path/to/audio.mp3 \
  --profile balanced \
  --language zh \
  --output-dir output/test-audio
```

## Validation summary

Environment validation so far:
- WSL2 + RTX 3080 Laptop GPU detected
- CUDA path usable by `faster-whisper`
- `yt-dlp`, `ffmpeg`, `ctranslate2`, `faster-whisper` all working

What is working:
- local audio transcription
- URL -> download -> transcription for Bilibili and YouTube
- normalize -> translate -> emit flow for text inputs
- optional local qwen second-pass refinement with timeout guards
- minimal output retention by default

Known gaps:
- translation + subtitle alignment is still basic
- large Telegram media downloads may still be unstable depending on provider fetch behavior
