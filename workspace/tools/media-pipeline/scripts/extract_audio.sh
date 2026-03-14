#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: extract_audio.sh <input-media> [output-wav]" >&2
  exit 1
fi

INPUT="$1"
OUTPUT="${2:-}"

if [ ! -f "$INPUT" ]; then
  echo "Error: input file not found: $INPUT" >&2
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "Error: ffmpeg not found" >&2
  exit 1
fi

if [ -z "$OUTPUT" ]; then
  base="${INPUT%.*}"
  OUTPUT="${base}.wav"
fi

mkdir -p "$(dirname "$OUTPUT")"

ffmpeg -y -i "$INPUT" -vn -acodec pcm_s16le -ar 16000 -ac 1 "$OUTPUT" >/dev/null 2>&1

echo "$OUTPUT"
